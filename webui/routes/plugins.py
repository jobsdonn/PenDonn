"""Plugins management page.

Lists all plugins found on disk (by scanning the plugins/ directory), shows
their manifest metadata and enabled/disabled state, and allows toggling each
plugin without touching plugin.json source files.

The enabled/disabled override is stored in `config.json.local` under
  plugins.disabled_names: ["Plugin Display Name", ...]

so a redeploy never resets operator choices.  The plugin_manager also reads
this list at startup (Priority 1 fix); the daemon needs a restart for changes
to take effect, but the webui shows the persisted state immediately.
"""

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Form, Request

from core.config_loader import _atomic_write_local, local_overlay_path
from webui.auth import require_login

router = APIRouter()


def _all_plugins(plugins_dir: str) -> List[Dict[str, Any]]:
    """Return a list of plugin descriptors from the plugins/ directory.

    Each item has keys: dir_name, name, version, description, author,
    load_error (or None), manifest_enabled, and config_disabled.
    The caller crosses `config_disabled` against `disabled_names` from config.
    """
    plugins = []
    if not os.path.isdir(plugins_dir):
        return plugins

    for entry in sorted(os.listdir(plugins_dir)):
        plugin_path = os.path.join(plugins_dir, entry)
        if not os.path.isdir(plugin_path):
            continue
        manifest_path = os.path.join(plugin_path, "plugin.json")
        if not os.path.isfile(manifest_path):
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            plugins.append({
                "dir_name": entry,
                "name": manifest.get("name", entry),
                "version": manifest.get("version", "?"),
                "description": manifest.get("description", ""),
                "author": manifest.get("author", ""),
                "manifest_enabled": bool(manifest.get("enabled", True)),
                "load_error": None,
            })
        except (OSError, json.JSONDecodeError) as e:
            plugins.append({
                "dir_name": entry,
                "name": entry,
                "version": "?",
                "description": "",
                "author": "",
                "manifest_enabled": False,
                "load_error": str(e),
            })

    return plugins


def _plugins_context(request: Request) -> Dict[str, Any]:
    cfg = request.app.state.config
    plugins_dir = os.path.join(
        os.path.dirname(request.app.state.config_path),
        "..",
        (cfg.get("plugins") or {}).get("directory", "plugins"),
    )
    plugins_dir = os.path.normpath(plugins_dir)
    disabled_names = list((cfg.get("plugins") or {}).get("disabled_names") or [])
    plugins_global_enabled = bool((cfg.get("plugins") or {}).get("enabled", True))

    raw = _all_plugins(plugins_dir)
    for p in raw:
        p["operator_disabled"] = p["name"] in disabled_names
        p["effective_enabled"] = (
            plugins_global_enabled
            and p["manifest_enabled"]
            and not p["operator_disabled"]
            and not p["load_error"]
        )
    return {
        "plugins": raw,
        "plugins_global_enabled": plugins_global_enabled,
        "plugins_dir": plugins_dir,
    }


@router.get("/plugins")
def plugins_page(request: Request, username: str = Depends(require_login)):
    ctx = _plugins_context(request)
    ctx["username"] = username
    ctx["active_nav"] = "plugins"
    return request.app.state.templates.TemplateResponse(
        request, "plugins.html", ctx,
    )


@router.post("/partials/plugins/{dir_name}/toggle")
def plugin_toggle(
    dir_name: str,
    request: Request,
    enable: str = Form(""),
    username: str = Depends(require_login),
):
    """Enable or disable a plugin by name.

    Writes the updated `disabled_names` list to config.json.local and
    reflects the change in the live in-memory config so the page re-renders
    correctly without a restart.
    """
    cfg = request.app.state.config
    plugins_dir = os.path.join(
        os.path.dirname(request.app.state.config_path),
        "..",
        (cfg.get("plugins") or {}).get("directory", "plugins"),
    )
    plugins_dir = os.path.normpath(plugins_dir)

    # Resolve the plugin's display name from its manifest (we store display
    # names in disabled_names, not dir names, for readability).
    manifest_path = os.path.join(plugins_dir, dir_name, "plugin.json")
    if not os.path.isfile(manifest_path):
        # Unknown plugin dir — no-op but don't 400 (could be a race with deploy)
        ctx = _plugins_context(request)
        return request.app.state.templates.TemplateResponse(
            request, "partials/plugins_list.html", ctx,
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        plugin_name = manifest.get("name", dir_name)
    except (OSError, json.JSONDecodeError):
        plugin_name = dir_name

    want_enabled = (enable or "").lower() in ("1", "true", "on", "yes")
    disabled_names = list((cfg.get("plugins") or {}).get("disabled_names") or [])

    if want_enabled:
        if plugin_name in disabled_names:
            disabled_names.remove(plugin_name)
    else:
        if plugin_name not in disabled_names:
            disabled_names.append(plugin_name)

    # Persist to overlay.
    overlay_path = local_overlay_path(request.app.state.config_path)
    overlay: Dict[str, Any] = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
        except (OSError, json.JSONDecodeError):
            overlay = {}
    overlay.setdefault("plugins", {})["disabled_names"] = disabled_names
    _atomic_write_local(overlay_path, overlay)

    # Mirror to live config.
    cfg.setdefault("plugins", {})["disabled_names"] = disabled_names

    request.app.state.db.add_audit_log(
        action="plugin.toggle",
        actor=username,
        target=plugin_name,
        details={"enabled": want_enabled},
        source_ip=request.client.host if request.client else None,
    )

    ctx = _plugins_context(request)
    return request.app.state.templates.TemplateResponse(
        request, "partials/plugins_list.html", ctx,
    )
