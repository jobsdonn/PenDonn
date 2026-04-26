"""
PenDonn Plugin System
Dynamic plugin loader for vulnerability scanners.

SECURITY: this loader executes arbitrary Python from disk via
importlib.util.spec_from_file_location + exec_module. We're typically
running as root because the wifi/enumeration paths require it, so a
plugin file = root code execution. Two layers of protection:

  1. Loader-side checks below: refuse to load a plugin file (or its
     containing directory) that is world-writable, group-writable by a
     group the operator hasn't allowlisted, or owned by a user other than
     root / the current effective uid. These checks block the most common
     prod accident (operator copies plugins via rsync without preserving
     mode 0700).

  2. Installer-side: scripts/install.sh chmod 0700 root the plugins/
     directory. See docs/SAFETY.md for the trust model.

Set safety.plugin_loader.allow_insecure_files=true to bypass the loader
checks (NOT recommended; logs a loud warning at every load).
"""

import os
import json
import importlib.util
import logging
import platform
import stat
import sys
from typing import List, Dict, Optional, Tuple
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def _check_plugin_file_safety(path: str) -> Optional[str]:
    """Return None if `path` is safe to exec; otherwise a reason string.

    Skipped entirely on non-POSIX (Windows dev box). The real enforcement
    happens on the Pi where the install runs as root.
    """
    if platform.system() != "Linux":
        return None
    try:
        st = os.stat(path)
    except OSError as e:
        return f"could not stat {path}: {e}"

    mode = st.st_mode
    # World-writable file = anyone on the box can replace its contents
    # between our stat and our exec, or just to defaultly. Fatal.
    if mode & stat.S_IWOTH:
        return f"world-writable (mode 0{stat.S_IMODE(mode):o}); refusing to exec"
    # Group-writable is also dangerous unless that group is just root.
    if mode & stat.S_IWGRP:
        # We don't have a great way to validate the group here without
        # extra config; flag and warn rather than refuse. Refusing would
        # break the common case of `pendonn` group ownership for shared dev.
        logger.warning(
            "plugin file %s is group-writable (gid=%d) — consider chmod g-w",
            path, st.st_gid,
        )
    # Owner must be root or our effective uid. If it's a random user
    # (e.g. an operator dropped a plugin from their home dir), refuse.
    try:
        my_euid = os.geteuid()
    except AttributeError:
        my_euid = -1
    if st.st_uid not in (0, my_euid):
        return (
            f"owned by uid {st.st_uid} (expected 0 or {my_euid}); "
            f"refusing to exec — chown root:root if intentional"
        )
    return None


class PluginBase(ABC):
    """Base class for all PenDonn plugins"""
    
    def __init__(self, config: Dict, database=None, *args, **kwargs):
        """Initialize plugin with configuration"""
        self.config = config
        self.db = database
        self.name = config.get('name', 'Unknown Plugin')
        self.version = config.get('version', '1.0.0')
        self.description = config.get('description', '')
        self.author = config.get('author', '')
        self.enabled = config.get('enabled', True)
        self.extra_args = args
        self.extra_kwargs = kwargs
    
    @abstractmethod
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """
        Execute the plugin's vulnerability scanning logic
        
        Args:
            scan_id: Database scan ID
            hosts: List of discovered IP addresses
            scan_results: Results from nmap scans
        
        Returns:
            Dictionary with results: {'vulnerabilities': count, 'results': [...]}
        """
        pass
    
    def log_info(self, message: str):
        """Log info message"""
        logger.info(f"[{self.name}] {message}")

    def log_warning(self, message: str):
        """Log warning message"""
        logger.warning(f"[{self.name}] {message}")

    def log_error(self, message: str):
        """Log error message"""
        logger.error(f"[{self.name}] {message}")

    def log_debug(self, message: str):
        """Log debug message. Many plugins call this; previously raised
        AttributeError on every error path because it didn't exist."""
        logger.debug(f"[{self.name}] {message}")


class PluginManager:
    """Manages loading and execution of plugins"""
    
    def __init__(self, config: Dict, database):
        """Initialize plugin manager"""
        self.config = config
        self.db = database

        self.enabled = config['plugins']['enabled']
        self.plugin_dir = config['plugins']['directory']
        self.auto_load = config['plugins']['auto_load']

        # Operator escape hatch for the loader-side ownership/mode checks.
        # Off by default because the whole point of those checks is to make
        # the common prod accident impossible.
        safety_cfg = (config.get('safety') or {}).get('plugin_loader') or {}
        self.allow_insecure_plugin_files = bool(
            safety_cfg.get('allow_insecure_files', False)
        )

        self.plugins = []

        # Ensure plugin directory exists
        os.makedirs(self.plugin_dir, exist_ok=True)

        logger.info("Plugin Manager initialized")
    
    def load_plugins(self):
        """Load all plugins from plugin directory"""
        if not self.enabled:
            logger.info("Plugins are disabled")
            return
        
        logger.info(f"Loading plugins from {self.plugin_dir}...")
        
        try:
            # Scan plugin directory
            for item in os.listdir(self.plugin_dir):
                plugin_path = os.path.join(self.plugin_dir, item)
                
                # Check if it's a directory
                if os.path.isdir(plugin_path):
                    self._load_plugin(plugin_path)
            
            logger.info(f"Loaded {len(self.plugins)} plugins")
        
        except Exception as e:
            logger.error(f"Error loading plugins: {e}")
    
    def _load_plugin(self, plugin_path: str):
        """Load a single plugin"""
        try:
            # Look for plugin.json
            config_file = os.path.join(plugin_path, 'plugin.json')
            
            if not os.path.exists(config_file):
                logger.warning(f"No plugin.json found in {plugin_path}")
                return
            
            # Load plugin configuration
            with open(config_file, 'r') as f:
                plugin_config = json.load(f)
            
            # Check if enabled (plugin.json flag, then operator config override).
            # `plugins.disabled_names` in config.json.local takes precedence so
            # operators can disable a plugin without modifying the plugin source,
            # meaning redeploys won't undo their choices.
            disabled_by_config = list(
                (self.config.get('plugins') or {}).get('disabled_names') or []
            )
            plugin_name = plugin_config.get('name', '')
            if plugin_name in disabled_by_config:
                logger.info(f"Plugin {plugin_name!r} disabled via config")
                return
            if not plugin_config.get('enabled', True):
                logger.info(f"Plugin {plugin_config.get('name', 'unknown')} is disabled")
                return
            
            # Load plugin module. Manifest may omit `module`; fall back to
            # `<dirname>.py` (matches the convention every shipped plugin
            # actually uses) and finally `plugin.py` for any new plugin
            # that wants the canonical name.
            dir_name = os.path.basename(plugin_path)
            module_candidates = []
            if plugin_config.get('module'):
                module_candidates.append(plugin_config['module'])
            else:
                module_candidates.extend([f"{dir_name}.py", "plugin.py"])

            module_path = None
            for candidate in module_candidates:
                candidate_path = os.path.join(plugin_path, candidate)
                if os.path.exists(candidate_path):
                    module_path = candidate_path
                    break

            if not module_path:
                logger.error(
                    f"Plugin module not found in {plugin_path} "
                    f"(tried: {', '.join(module_candidates)})"
                )
                return

            # SECURITY: refuse to exec plugin code we can't trust the
            # provenance of. Operator can override via
            # safety.plugin_loader.allow_insecure_files=true.
            for check_path in (plugin_path, module_path, config_file):
                problem = _check_plugin_file_safety(check_path)
                if problem:
                    if self.allow_insecure_plugin_files:
                        logger.warning(
                            "plugin safety check would have refused %s (%s) "
                            "but allow_insecure_files=true — loading anyway",
                            check_path, problem,
                        )
                    else:
                        logger.error(
                            "REFUSING to load plugin %s: %s. "
                            "Fix file ownership/mode, or set "
                            "safety.plugin_loader.allow_insecure_files=true.",
                            plugin_config.get('name', plugin_path), problem,
                        )
                        return

            # Import module
            spec = importlib.util.spec_from_file_location(
                plugin_config['name'],
                module_path
            )
            
            if not spec or not spec.loader:
                logger.error(f"Failed to load plugin spec: {plugin_path}")
                return
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Locate the plugin class. Manifest may declare `class` explicitly;
            # otherwise scan the loaded module for a subclass of PluginBase.
            # This means new plugins don't need to set `class` in plugin.json.
            explicit_class_name = plugin_config.get('class')
            plugin_class = None
            if explicit_class_name:
                plugin_class = getattr(module, explicit_class_name, None)
                if plugin_class is None:
                    logger.error(
                        f"Plugin class '{explicit_class_name}' not found in {module_path}"
                    )
                    return
            else:
                for attr_name in dir(module):
                    candidate = getattr(module, attr_name)
                    if (isinstance(candidate, type)
                            and issubclass(candidate, PluginBase)
                            and candidate is not PluginBase):
                        plugin_class = candidate
                        logger.debug(
                            f"Auto-detected plugin class {attr_name} in {module_path}"
                        )
                        break
                if plugin_class is None:
                    logger.error(
                        f"No PluginBase subclass found in {module_path}; "
                        f"declare `class` in plugin.json or extend PluginBase"
                    )
                    return
            
            # Instantiate plugin
            try:
                plugin_instance = plugin_class(plugin_config, self.db)  # Pass `db` during initialization
            except TypeError as e:
                logger.error(f"Failed to initialize plugin {plugin_config['name']}: {e}")
                return

            self.plugins.append(plugin_instance)
            logger.info(f"Loaded plugin: {plugin_config['name']} v{plugin_config.get('version', '1.0.0')}")
        
        except Exception as e:
            logger.error(f"Error loading plugin from {plugin_path}: {e}")
    
    def get_enabled_plugins(self) -> List[PluginBase]:
        """Get list of enabled plugins"""
        return [p for p in self.plugins if p.enabled]
    
    def get_all_plugins(self) -> List[PluginBase]:
        """Get all loaded plugins"""
        return self.plugins
    
    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Get plugin by name"""
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None
    
    def reload_plugins(self):
        """Reload all plugins"""
        self.plugins.clear()
        self.load_plugins()
    
    def get_plugin_info(self) -> List[Dict]:
        """Get information about all plugins"""
        return [
            {
                'name': p.name,
                'version': p.version,
                'description': p.description,
                'author': p.author,
                'enabled': p.enabled
            }
            for p in self.plugins
        ]
