"""Filesystem and subprocess-input safety helpers.

Two recurring hazards in PenDonn:

  1. Writing config files (hostapd, dnsmasq, wpa_supplicant) to /tmp with
     default umask — they end up world-readable and contain plaintext PSKs
     or interface details. Any other user on the box can grab them.
  2. Embedding user/network-controlled strings (SSIDs above all) into
     line-based config files without validation. A crafted SSID containing
     a newline can inject arbitrary hostapd directives.

This module provides:

  - secure_temp_config(): create a 0600-mode temp file in a per-process
    pendonn-only directory, return its path.
  - cleanup_secure_temp_dir(): remove the per-process directory on shutdown.
  - sanitize_hostapd_value(): reject newlines/nulls and length-violating
    values before they reach hostapd/dnsmasq config.
  - encode_wpa_supplicant_ssid() / encode_wpa_supplicant_psk(): emit the
    safe `key=hex` form of wpa_supplicant config lines instead of the
    quote-escaping `key="..."` form, which sidesteps quote/backslash issues.
  - sanitize_iface_name(): defensive check that an iface name is a plausible
    Linux iface (alphanumeric + a few delimiters), used as belt-and-braces
    even though iface names normally come from local config.
"""

import logging
import os
import re
import shutil
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secure temp directory (one per process, 0700, lazily created)
# ---------------------------------------------------------------------------

_secure_dir: Optional[str] = None
_secure_dir_lock = threading.Lock()


def _get_secure_temp_dir() -> str:
    """Return path to a 0700 temp directory unique to this process.

    Created lazily on first call, reused for the lifetime of the process.
    Tests and `cleanup_secure_temp_dir()` reset it.
    """
    global _secure_dir
    with _secure_dir_lock:
        if _secure_dir and os.path.isdir(_secure_dir):
            return _secure_dir
        # mkdtemp respects mode via the OS umask, so chmod explicitly afterward.
        path = tempfile.mkdtemp(prefix=f"pendonn-{os.getpid()}-")
        try:
            os.chmod(path, 0o700)
        except OSError as e:
            logger.warning("Could not chmod secure temp dir %s: %s", path, e)
        _secure_dir = path
        return path


def secure_temp_config(prefix: str, suffix: str = ".conf") -> str:
    """Create a 0600 temp file inside the secure dir; return its path.

    The file is created empty. Caller writes content via a normal open()
    afterward (the file already has the right mode, so no race window
    between create and chmod).
    """
    secure_dir = _get_secure_temp_dir()
    fd, path = tempfile.mkstemp(prefix=f"{prefix}_", suffix=suffix, dir=secure_dir)
    try:
        os.fchmod(fd, 0o600)
    except (AttributeError, OSError) as e:
        # fchmod is POSIX; on Windows dev hosts it may be missing. The dir
        # is already 0700 so containment is fine — log and continue.
        logger.debug("fchmod not available on %s: %s", path, e)
    finally:
        os.close(fd)
    return path


def cleanup_secure_temp_dir() -> None:
    """Remove the per-process secure temp dir. Safe to call repeatedly."""
    global _secure_dir
    with _secure_dir_lock:
        if _secure_dir and os.path.isdir(_secure_dir):
            try:
                shutil.rmtree(_secure_dir, ignore_errors=True)
            except OSError as e:
                logger.warning("Could not remove %s: %s", _secure_dir, e)
        _secure_dir = None


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

# Linux iface names: <= 15 chars, no slash, no whitespace, no NUL.
# Be conservative and only allow alnum + .-_:
_IFACE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,15}$")


def sanitize_iface_name(name: str) -> str:
    """Return `name` if it looks like a valid Linux iface; raise ValueError otherwise."""
    if not isinstance(name, str) or not _IFACE_RE.match(name):
        raise ValueError(f"invalid interface name: {name!r}")
    return name


def sanitize_hostapd_value(
    value: str, *, max_len: int = 32, field: str = "value", allow_empty: bool = False
) -> str:
    """Validate a value before embedding in line-based hostapd/dnsmasq config.

    Rejects: non-str, newline (\\n or \\r), NUL byte, over-length strings.

    Args:
        max_len: Maximum byte length when UTF-8 encoded. Default 32 = the
            802.11 SSID limit.
        field: Label included in the error message, for caller-side context.
        allow_empty: By default empty strings are rejected (probably a bug).
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be str, got {type(value).__name__}")
    if not value and not allow_empty:
        raise ValueError(f"{field} is empty")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{field} contains newline or NUL — would inject into config")
    encoded = value.encode("utf-8", errors="strict")
    if len(encoded) > max_len:
        raise ValueError(
            f"{field} too long ({len(encoded)} bytes, max {max_len})"
        )
    return value


def encode_wpa_supplicant_ssid(ssid: str) -> str:
    """Return the wpa_supplicant config line value for an SSID.

    Uses the unquoted hex form (e.g. `ssid=4d795773` for "MyWs") which
    bypasses all the quote/backslash escaping pitfalls of the quoted form.
    Caller writes `f"    ssid={encode_wpa_supplicant_ssid(s)}\\n"`.

    802.11 SSIDs are 0–32 bytes of arbitrary octets; we enforce that here
    so we don't write a config wpa_supplicant will reject anyway.
    """
    if not isinstance(ssid, str):
        raise ValueError(f"ssid must be str, got {type(ssid).__name__}")
    encoded = ssid.encode("utf-8", errors="strict")
    if len(encoded) > 32:
        raise ValueError(f"ssid too long ({len(encoded)} bytes, max 32)")
    if len(encoded) == 0:
        raise ValueError("ssid is empty")
    return encoded.hex()


def encode_wpa_supplicant_psk(psk: str) -> str:
    """Return the wpa_supplicant config value for a WPA-PSK passphrase.

    WPA passphrases are 8–63 ASCII characters. We accept that range and
    return the quoted form (the only valid form for an ASCII passphrase
    that isn't a 64-char hex PSK). Backslash and double-quote are escaped.

    A 64-char hex string is also acceptable as a literal raw PSK and is
    written without quotes — handled here for completeness.
    """
    if not isinstance(psk, str):
        raise ValueError(f"psk must be str, got {type(psk).__name__}")
    # 64-hex-char raw PSK: pass through unquoted
    if len(psk) == 64 and all(c in "0123456789abcdefABCDEF" for c in psk):
        return psk
    if not (8 <= len(psk) <= 63):
        raise ValueError(f"WPA passphrase must be 8-63 chars; got {len(psk)}")
    if "\n" in psk or "\r" in psk or "\x00" in psk:
        raise ValueError("WPA passphrase contains newline or NUL")
    escaped = psk.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
