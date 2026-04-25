"""Config loader with `.local` overlay and persistent secret generation.

Two responsibilities:

  1. `load_config(path)` reads the tracked config (e.g. config.json) and
     deep-merges any sibling `<path>.local` file on top (gitignored). This
     lets operators override fields per-host (Pi-specific tuning, real
     SSIDs, the web secret_key, the basic_auth password hash) without
     committing them.

  2. `ensure_persistent_secret(config, config_path)` ensures a usable
     `web.secret_key` exists. If the merged config has an empty/placeholder
     value, generate one via `secrets.token_hex(32)`, write it to the
     `.local` file with chmod 0600, and mutate the in-memory config to
     reflect it. Idempotent — second call is a no-op.

Both callers (main.py daemon and web/app.py) use the same loader so the
two processes see identical effective config.
"""

import copy
import json
import logging
import os
import secrets
import stat
from typing import Any, Dict

logger = logging.getLogger(__name__)

PLACEHOLDER_SECRETS = frozenset({
    "",
    "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION",
    "CHANGE_THIS",
})


def _strip_doc_keys(value: Any) -> Any:
    """Recursively drop `_`-prefixed keys from nested dicts (in-place safe)."""
    if isinstance(value, dict):
        return {
            k: _strip_doc_keys(v)
            for k, v in value.items()
            if not (isinstance(k, str) and k.startswith("_"))
        }
    if isinstance(value, list):
        return [_strip_doc_keys(v) for v in value]
    return value


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge `overlay` onto a copy of `base`.

    For nested dicts we recurse; for any other type the overlay value
    replaces the base value entirely. Returns a new dict — neither input
    is mutated. Keys starting with `_` (documentation-only) are dropped
    from the merged output (at every nesting level) to keep the runtime
    config tidy.
    """
    out = copy.deepcopy(base)
    for key, overlay_val in overlay.items():
        if isinstance(key, str) and key.startswith("_"):
            continue
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(overlay_val, dict)
        ):
            out[key] = _deep_merge(out[key], overlay_val)
        else:
            out[key] = copy.deepcopy(overlay_val)
    return _strip_doc_keys(out)


def local_overlay_path(config_path: str) -> str:
    """Return the conventional `.local` overlay path for a config file."""
    return f"{config_path}.local"


def load_config(config_path: str) -> Dict[str, Any]:
    """Load config from `config_path`, then merge `<path>.local` on top.

    The `.local` file is optional. Documentation-only keys (those starting
    with `_`) are stripped from the returned dict.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        base = json.load(f)
    overlay_path = local_overlay_path(config_path)
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
            logger.info("Loaded local overlay from %s", overlay_path)
            return _deep_merge(base, overlay)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(
                "Failed to load %s: %s — continuing with tracked config only",
                overlay_path, e,
            )
    return _deep_merge(base, {})  # strips _-keys


def _atomic_write_local(overlay_path: str, payload: Dict[str, Any]) -> None:
    """Write `payload` to `overlay_path` with mode 0600, atomically.

    "Atomic" = write to tempfile in same dir, fsync, then rename. Prevents
    a half-written file from being read by a concurrent process if we crash.
    """
    tmp_path = f"{overlay_path}.tmp"
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # fsync may fail on tmpfs / unusual FS; not fatal
        os.replace(tmp_path, overlay_path)
        # On systems where mode wasn't honored at open time (umask quirks,
        # Windows), fix it explicitly afterward.
        try:
            os.chmod(overlay_path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def ensure_persistent_secret(config: Dict[str, Any], config_path: str) -> str:
    """Make sure `config['web']['secret_key']` is usable; persist to .local.

    If the merged config already has a non-placeholder secret, return it.
    Otherwise generate one with `secrets.token_hex(32)`, write it to the
    `.local` overlay (creating or merging), update `config` in place, and
    return the new secret.

    Returns the resolved secret. Caller passes it to `app.config['SECRET_KEY']`.
    """
    web_section = config.setdefault("web", {})
    current = web_section.get("secret_key") or ""
    if current and current not in PLACEHOLDER_SECRETS:
        return current

    new_secret = secrets.token_hex(32)
    overlay_path = local_overlay_path(config_path)

    # Read existing .local (if any) so we don't clobber other operator-set
    # overrides like basic_auth credentials or per-host tuning.
    overlay: Dict[str, Any] = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "Existing %s could not be parsed (%s) — will overwrite.",
                overlay_path, e,
            )
            overlay = {}

    overlay.setdefault("web", {})["secret_key"] = new_secret
    _atomic_write_local(overlay_path, overlay)
    web_section["secret_key"] = new_secret
    logger.warning(
        "Generated persistent web.secret_key and wrote it to %s (mode 0600). "
        "Keep this file out of version control (.gitignore already covers it).",
        overlay_path,
    )
    return new_secret
