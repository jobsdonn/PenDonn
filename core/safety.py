"""
PenDonn Safety Module

Hard guard against the #1 operational hazard: locking the operator out of
SSH by accidentally putting the management WiFi interface into monitor mode,
killing wpa_supplicant on the wrong interface, or otherwise disrupting the
network path that the operator is connected over.

Nothing in PenDonn that touches a WiFi interface should run without first
asking SSHGuard.assert_safe_to_modify(iface). The check is cheap; the cost
of getting it wrong is "drive to the Pi to recover."

Design notes:
  - Read-only checks here (no subprocess that mutates state).
  - All state derived from /proc, /sys, env vars, and `ip`/`who` reads.
  - On non-Linux (Windows dev), checks degrade to "no SSH detected, no
    management iface inferable" rather than crashing — so unit tests pass.
  - Operator can explicitly arm an override via SafetyConfig.armed_override
    when they genuinely want to put the management iface in monitor mode
    (e.g. RPi Zero 2 W single_interface_mode). Default is OFF.
"""

import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SafetyViolation(Exception):
    """Raised when an operation would violate the safety contract.

    Catching this is allowed but discouraged — usually it means the operator
    needs to fix config or arm an explicit override, not that the code should
    proceed anyway.
    """


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class SafetyConfig:
    """Operator-facing safety knobs. Defaults are intentionally strict.

    Fields map 1:1 to the `safety:` section of config.json.
    """
    enabled: bool = True
    # If True, refuse to put any iface in monitor mode while a live SSH
    # session is detected on the same iface.
    block_monitor_on_ssh_iface: bool = True
    # If True, refuse to ever put the management iface in monitor mode,
    # regardless of SSH state.
    block_monitor_on_management: bool = True
    # If True, refuse to kill wpa_supplicant when its only PID is bound to
    # the management iface (would sever SSH if SSH rides over WiFi).
    block_kill_management_supplicant: bool = True
    # Operator-set override. When True, ALL of the above guards are bypassed.
    # Intended for the RPi Zero 2 W single_interface_mode case where the
    # operator knowingly accepts SSH loss.
    armed_override: bool = False
    # Allowlist of interface names that are explicitly safe to modify even
    # if other heuristics flag them. Empty = no allowlist.
    explicit_safe_ifaces: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Optional[Dict]) -> "SafetyConfig":
        if not d:
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# SSH session detection
# ---------------------------------------------------------------------------

def detect_ssh_session() -> Optional[Dict[str, str]]:
    """Return info about the calling user's SSH session, or None.

    Order of checks (cheapest first):
      1. SSH_CLIENT / SSH_CONNECTION env vars (set by sshd in user shells)
      2. `who` output (works for any logged-in pty)
      3. /proc/<ppid>/cmdline contains 'sshd' (works when run from a script
         spawned by sshd)
    """
    # Env-var check
    ssh_conn = os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT")
    if ssh_conn:
        # SSH_CONNECTION format: "client_ip client_port server_ip server_port"
        parts = ssh_conn.split()
        return {
            "source": "env",
            "client_ip": parts[0] if parts else "",
            "server_ip": parts[2] if len(parts) >= 3 else "",
        }

    # who check (Linux/macOS only)
    if platform.system() != "Linux":
        return None

    try:
        result = subprocess.run(
            ["who"], capture_output=True, text=True, timeout=2, check=False
        )
        for line in result.stdout.splitlines():
            # Lines look like: "linus  pts/0  2026-04-25 20:00 (192.168.1.42)"
            m = re.search(r"\(([0-9a-fA-F:.]+)\)", line)
            if m:
                return {"source": "who", "client_ip": m.group(1), "server_ip": ""}
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass

    # ppid check
    try:
        ppid = os.getppid()
        with open(f"/proc/{ppid}/cmdline", "rb") as f:
            cmdline = f.read().replace(b"\x00", b" ").decode(errors="ignore")
        if "sshd" in cmdline:
            return {"source": "ppid", "client_ip": "", "server_ip": ""}
    except (FileNotFoundError, PermissionError, OSError):
        pass

    return None


# ---------------------------------------------------------------------------
# Interface state inspection (read-only)
# ---------------------------------------------------------------------------

def get_iface_route_for_ip(target_ip: str) -> Optional[str]:
    """Return the iface that the OS would use to reach `target_ip`, or None.

    Used to figure out which iface the SSH client traffic actually rides over.
    On Linux, parses `ip route get <ip>` output.
    """
    if not target_ip or platform.system() != "Linux":
        return None
    try:
        result = subprocess.run(
            ["ip", "route", "get", target_ip],
            capture_output=True, text=True, timeout=2, check=False,
        )
        # Output like: "192.168.1.42 via 192.168.1.1 dev wlan0 src 192.168.1.50 ..."
        m = re.search(r"\bdev\s+(\S+)", result.stdout)
        if m:
            return m.group(1)
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return None


def get_iface_mode(iface: str) -> Optional[str]:
    """Return the current 802.11 mode of `iface` ('managed', 'monitor', ...) or None."""
    if platform.system() != "Linux":
        return None
    try:
        result = subprocess.run(
            ["iw", "dev", iface, "info"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        m = re.search(r"\btype\s+(\S+)", result.stdout)
        if m:
            return m.group(1).lower()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return None


def iface_has_ip(iface: str) -> bool:
    """Return True if `iface` currently has any inet address assigned."""
    if platform.system() != "Linux":
        return False
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", "dev", iface],
            capture_output=True, text=True, timeout=2, check=False,
        )
        return "inet " in result.stdout
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return False


def find_supplicant_pids_by_iface() -> Dict[str, List[int]]:
    """Walk /proc and return {iface: [pid, ...]} for running wpa_supplicant."""
    return _find_iface_pids_for_program("wpa_supplicant")


def find_dhcpcd_pids_by_iface() -> Dict[str, List[int]]:
    """Walk /proc and return {iface: [pid, ...]} for running dhcpcd.

    dhcpcd's iface name is the LAST positional arg (after any flags).
    Empty dict if no iface arg (system-wide daemon mode) — those should
    NEVER be killed by enumerator code; only per-iface invocations.
    """
    out: Dict[str, List[int]] = {}
    proc_root = "/proc"
    if platform.system() != "Linux" or not os.path.isdir(proc_root):
        return out
    for entry in os.listdir(proc_root):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\x00") if a]
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if not argv:
            continue
        if os.path.basename(argv[0]) != "dhcpcd":
            continue
        # Last non-flag positional arg = iface (if any).
        positionals = [a for a in argv[1:] if not a.startswith("-")]
        if positionals:
            out.setdefault(positionals[-1], []).append(pid)
    return out


def _find_iface_pids_for_program(program: str) -> Dict[str, List[int]]:
    """Helper for find_supplicant_pids_by_iface.

    Replaces the audit's `pgrep -f '<prog>.*<iface>'` pattern, which is a
    substring match on the full command line and can wrongly match e.g.
    `wpa_supplicant --help wlan0` from a user's shell history. We parse
    /proc/<pid>/cmdline directly and look for the actual `-i <iface>` arg.
    """
    out: Dict[str, List[int]] = {}
    proc_root = "/proc"
    if platform.system() != "Linux" or not os.path.isdir(proc_root):
        return out

    for entry in os.listdir(proc_root):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().split(b"\x00")
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if not argv or not argv[0]:
            continue
        prog = os.path.basename(argv[0].decode(errors="replace"))
        if prog != program:
            continue
        # Parse `-i <iface>` from argv (or `-iwlan0` short form).
        iface = None
        for i, raw in enumerate(argv):
            arg = raw.decode(errors="replace")
            if arg == "-i" and i + 1 < len(argv):
                iface = argv[i + 1].decode(errors="replace")
                break
            if arg.startswith("-i") and len(arg) > 2:
                iface = arg[2:]
                break
        if iface:
            out.setdefault(iface, []).append(pid)
    return out


# ---------------------------------------------------------------------------
# SSHGuard — the hard gate
# ---------------------------------------------------------------------------

class SSHGuard:
    """Hard gate against operations that could lock out the operator.

    Typical usage:

        guard = SSHGuard(safety_config, interfaces)
        guard.assert_safe_to_modify('wlan0')   # raises SafetyViolation if unsafe
        # ... safe to set monitor mode now
    """

    def __init__(
        self,
        safety_config: SafetyConfig,
        interfaces: Dict[str, str],
        *,
        ssh_session: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            safety_config: Parsed `safety:` config section.
            interfaces: Output of interface_manager.resolve_interfaces() —
                {'monitor': 'wlan0', 'attack': 'wlan1', 'management': 'wlan2'}.
                Any value may be None if MAC resolution failed.
            ssh_session: Pre-computed result of detect_ssh_session() — pass
                explicitly in tests; defaults to live detection.
        """
        self.cfg = safety_config
        self.interfaces = {k: v for k, v in interfaces.items() if v}
        self._ssh_session = (
            ssh_session if ssh_session is not None else detect_ssh_session()
        )

    # -- public predicates --------------------------------------------------

    @property
    def ssh_active(self) -> bool:
        return self._ssh_session is not None

    @property
    def management_iface(self) -> Optional[str]:
        return self.interfaces.get("management")

    def ssh_iface(self) -> Optional[str]:
        """Best guess at which iface SSH traffic rides over. None if unknown."""
        if not self._ssh_session:
            return None
        client_ip = self._ssh_session.get("client_ip")
        if client_ip:
            return get_iface_route_for_ip(client_ip)
        return None

    def is_management(self, iface: str) -> bool:
        return self.management_iface is not None and iface == self.management_iface

    def is_explicitly_safe(self, iface: str) -> bool:
        return iface in set(self.cfg.explicit_safe_ifaces)

    # -- the gate ----------------------------------------------------------

    def assert_safe_to_modify(self, iface: str, operation: str = "monitor mode") -> None:
        """Raise SafetyViolation if modifying `iface` would risk lockout.

        Args:
            iface: Interface name about to be reconfigured.
            operation: Free-text description of what's about to happen,
                included in the exception message and log.
        """
        if not self.cfg.enabled:
            logger.debug("Safety disabled in config; allowing %s on %s", operation, iface)
            return

        if self.cfg.armed_override:
            logger.warning(
                "Safety override ARMED — allowing %s on %s. Operator accepted lockout risk.",
                operation, iface,
            )
            return

        if self.is_explicitly_safe(iface):
            logger.debug("Iface %s in explicit_safe_ifaces; allowing %s", iface, operation)
            return

        # Hard rule 1: never touch the management iface.
        if self.cfg.block_monitor_on_management and self.is_management(iface):
            self._raise(
                iface, operation,
                f"{iface} is the configured management interface "
                f"(safety.block_monitor_on_management=true). "
                f"To proceed, either change the config or set safety.armed_override=true."
            )

        # Hard rule 2: never touch the iface SSH is riding over.
        if self.cfg.block_monitor_on_ssh_iface and self.ssh_active:
            ssh_iface = self.ssh_iface()
            if ssh_iface and ssh_iface == iface:
                self._raise(
                    iface, operation,
                    f"active SSH session is currently riding over {iface} "
                    f"(client {self._ssh_session.get('client_ip', 'unknown')}). "
                    f"Modifying it would disconnect you. "
                    f"To proceed, SSH in over a different interface or set safety.armed_override=true."
                )

    def assert_safe_to_kill_supplicant(self, pids_by_iface: Dict[str, List[int]]) -> List[int]:
        """Filter a set of wpa_supplicant PIDs to only those safe to kill.

        Replacement for the pgrep-and-kill pattern in enumerator.py that can
        kill the global supplicant on the management iface.

        Args:
            pids_by_iface: {iface_name: [pid, ...]} — caller pre-resolves which
                supplicant PID belongs to which iface (e.g. by parsing
                /proc/<pid>/cmdline for `-i <iface>`).

        Returns:
            Subset of PIDs that are safe to terminate.
        """
        if not self.cfg.enabled or self.cfg.armed_override:
            return [pid for pids in pids_by_iface.values() for pid in pids]

        safe = []
        for iface, pids in pids_by_iface.items():
            if self.cfg.block_kill_management_supplicant and self.is_management(iface):
                logger.warning(
                    "Refusing to kill wpa_supplicant on management iface %s (PIDs: %s)",
                    iface, pids,
                )
                continue
            safe.extend(pids)
        return safe

    # -- internal -----------------------------------------------------------

    def _raise(self, iface: str, operation: str, reason: str) -> None:
        msg = f"SAFETY: refusing to {operation} on {iface} — {reason}"
        logger.error(msg)
        raise SafetyViolation(msg)


# ---------------------------------------------------------------------------
# Preflight — run once before main daemon starts
# ---------------------------------------------------------------------------

@dataclass
class PreflightResult:
    ok: bool
    fatal_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


def preflight_check(
    config: Dict,
    interfaces: Dict[str, str],
    *,
    ssh_session: Optional[Dict[str, str]] = None,
) -> PreflightResult:
    """Run all safety checks before the main daemon does anything mutable.

    Returns PreflightResult; caller decides whether to abort on fatal errors.
    main.py should refuse to call .start() on any module if .ok is False
    and armed_override is not set.
    """
    safety_cfg = SafetyConfig.from_dict(config.get("safety"))
    result = PreflightResult(ok=True)

    if not safety_cfg.enabled:
        result.warnings.append(
            "safety.enabled=false — all SSH-lockout protections are disabled."
        )

    if safety_cfg.armed_override:
        result.warnings.append(
            "safety.armed_override=true — you have accepted SSH lockout risk."
        )

    sess = ssh_session if ssh_session is not None else detect_ssh_session()
    if sess:
        result.info.append(
            f"SSH session detected (source={sess.get('source')}, "
            f"client={sess.get('client_ip', 'unknown')})."
        )

    # Check 1: configured interfaces must all resolve to distinct names
    monitor = interfaces.get("monitor")
    attack = interfaces.get("attack")
    management = interfaces.get("management")

    resolved_pairs = [(k, v) for k, v in interfaces.items() if v]
    seen: Dict[str, str] = {}
    for role, name in resolved_pairs:
        if name in seen:
            msg = (
                f"Interface {name} is assigned to BOTH '{seen[name]}' and "
                f"'{role}' roles. This is the single_interface_mode footgun "
                f"and WILL break things if you didn't mean it."
            )
            if safety_cfg.armed_override:
                result.warnings.append(msg)
            else:
                result.fatal_errors.append(msg)
                result.ok = False
        seen[name] = role

    # Check 2: if SSH is active and we can identify the iface it rides over,
    # it must NOT be the same as the configured monitor/attack iface.
    if sess and safety_cfg.block_monitor_on_ssh_iface:
        ssh_iface = None
        client_ip = sess.get("client_ip")
        if client_ip:
            ssh_iface = get_iface_route_for_ip(client_ip)
        if ssh_iface:
            result.info.append(f"SSH traffic rides over {ssh_iface}.")
            for role in ("monitor", "attack"):
                role_iface = interfaces.get(role)
                if role_iface and role_iface == ssh_iface:
                    msg = (
                        f"Configured {role}_interface ({role_iface}) is the "
                        f"same iface SSH is riding over. Starting will sever SSH."
                    )
                    if safety_cfg.armed_override:
                        result.warnings.append(msg)
                    else:
                        result.fatal_errors.append(msg)
                        result.ok = False

    # Check 3: management iface (if defined) must currently have an IP and be
    # in managed mode. If it doesn't, the operator is already in a bad state
    # and we should report it loudly before doing anything that makes it worse.
    if management:
        if not iface_has_ip(management):
            result.warnings.append(
                f"Management interface {management} has no IPv4 address. "
                f"You may already be on the way to lockout."
            )
        mode = get_iface_mode(management)
        if mode and mode != "managed":
            msg = (
                f"Management interface {management} is currently in "
                f"'{mode}' mode (expected 'managed'). Recovery watchdog "
                f"should restore this on its next tick."
            )
            if safety_cfg.armed_override:
                result.warnings.append(msg)
            else:
                result.fatal_errors.append(msg)
                result.ok = False

    return result
