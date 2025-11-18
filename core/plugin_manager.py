"""
PenDonn Plugin System
Dynamic plugin loader for vulnerability scanners
"""

import os
import json
import importlib.util
import logging
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class PluginBase(ABC):
    """Base class for all PenDonn plugins"""
    
    def __init__(self, config: Dict):
        """Initialize plugin with configuration"""
        self.config = config
        self.name = config.get('name', 'Unknown Plugin')
        self.version = config.get('version', '1.0.0')
        self.description = config.get('description', '')
        self.author = config.get('author', '')
        self.enabled = config.get('enabled', True)
    
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


class PluginManager:
    """Manages loading and execution of plugins"""
    
    def __init__(self, config: Dict, database):
        """Initialize plugin manager"""
        self.config = config
        self.db = database
        
        self.enabled = config['plugins']['enabled']
        self.plugin_dir = config['plugins']['directory']
        self.auto_load = config['plugins']['auto_load']
        
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
            
            # Check if enabled
            if not plugin_config.get('enabled', True):
                logger.info(f"Plugin {plugin_config.get('name', 'unknown')} is disabled")
                return
            
            # Load plugin module
            module_file = plugin_config.get('module', 'plugin.py')
            module_path = os.path.join(plugin_path, module_file)
            
            if not os.path.exists(module_path):
                logger.error(f"Plugin module not found: {module_path}")
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
            
            # Get plugin class
            plugin_class_name = plugin_config.get('class', 'Plugin')
            
            if not hasattr(module, plugin_class_name):
                logger.error(f"Plugin class '{plugin_class_name}' not found in {module_path}")
                return
            
            plugin_class = getattr(module, plugin_class_name)
            
            # Instantiate plugin
            plugin_instance = plugin_class(plugin_config)
            plugin_instance.db = self.db  # Provide database access
            
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
