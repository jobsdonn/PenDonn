#!/usr/bin/env python3
"""
PenDonn Main Daemon
Orchestrates all modules
"""

import os
import sys
import json
import signal
import logging
import time
from datetime import datetime

from core.database import Database
from core.plugin_manager import PluginManager
from core.enumerator import NetworkEnumerator
from core.cracker import PasswordCracker

# Configure logging
log_dir = "./logs"
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'pendonn.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class PenDonn:
    """Main PenDonn system"""
    
    def __init__(self, config_path: str = './config/config.json'):
        """Initialize PenDonn system"""
        logger.info("=" * 60)
        logger.info("PenDonn - Automated Penetration Testing System")
        logger.info("=" * 60)
        
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        logger.info(f"PenDonn v{self.config['system']['version']}")
        
        # Initialize database
        logger.info("Initializing database...")
        self.db = Database(self.config['database']['path'])
        
        # Initialize plugin manager
        logger.info("Initializing plugin manager...")
        self.plugin_manager = PluginManager(self.config, self.db)
        self.plugin_manager.load_plugins()
        
        # Initialize WiFi scanner
        logger.info("Initializing WiFi scanner...")
        from core.wifi_scanner import WiFiScanner
        self.wifi_monitor = WiFiScanner(self.config, self.db)
        
        logger.info("Initializing password cracker...")
        self.cracker = PasswordCracker(self.config, self.db, self.wifi_monitor)
        
        logger.info("Initializing network enumerator...")
        self.enumerator = NetworkEnumerator(self.config, self.db, self.plugin_manager)
        
        # Initialize display
        if self.config['display']['enabled']:
            logger.info("Initializing display...")
            from core.display import Display
            self.display = Display(self.config, self.db)
        else:
            self.display = None
        
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("PenDonn initialized successfully")
    
    def start(self):
        """Start all modules"""
        logger.info("Starting PenDonn...")
        
        self.running = True
        
        # Start modules
        self.wifi_monitor.start()
        self.cracker.start()
        self.enumerator.start()
        
        if self.display:
            self.display.start()
        
        logger.info("PenDonn started successfully")
        logger.info("System is now operational")
        
        # Main loop
        try:
            while self.running:
                self._status_update()
                time.sleep(30)
        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        
        finally:
            self.stop()
    
    def stop(self):
        """Stop all modules"""
        logger.info("Stopping PenDonn...")
        
        self.running = False
        
        # Stop modules
        if self.wifi_monitor:
            self.wifi_monitor.stop()
        
        if self.cracker:
            self.cracker.stop()
        
        if self.enumerator:
            self.enumerator.stop()
        
        if self.display:
            self.display.stop()
        
        # Close database
        if self.db:
            self.db.close()
        
        logger.info("PenDonn stopped")
    
    def _status_update(self):
        """Log periodic status update"""
        try:
            stats = self.db.get_statistics()
            
            logger.info("=" * 60)
            logger.info("STATUS UPDATE")
            logger.info(f"Networks Discovered: {stats['networks_discovered']}")
            logger.info(f"Handshakes Captured: {stats['handshakes_captured']}")
            logger.info(f"Passwords Cracked: {stats['passwords_cracked']}")
            logger.info(f"Scans Completed: {stats['scans_completed']}")
            logger.info(f"Vulnerabilities Found: {stats['vulnerabilities_found']}")
            logger.info(f"  - Critical: {stats['critical_vulnerabilities']}")
            logger.info("=" * 60)
        
        except Exception as e:
            logger.error(f"Status update error: {e}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}")
        self.running = False


def main():
    """Main entry point"""
    # Parse command line arguments
    config_file = 'config.json'
    if len(sys.argv) > 1:
        if sys.argv[1] == '--debug':
            config_file = 'config.debug.json'
            print("\n🐛 DEBUG MODE ENABLED - Using debug configuration\n")
    
    # Check if running as root (skip in debug mode)
    config_path = os.path.join(os.path.dirname(__file__), 'config', config_file)
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    debug_mode = config.get('debug', {}).get('enabled', False)
    
    if not debug_mode and os.name != 'nt':  # Only check on Unix systems, not Windows
        if os.geteuid() != 0:
            print("ERROR: PenDonn must be run as root")
            print("Please run with sudo or as root user")
            sys.exit(1)
    
    # Legal warning
    print("\n" + "=" * 60)
    print("LEGAL WARNING")
    print("=" * 60)
    print("This tool is for AUTHORIZED penetration testing only.")
    print("Unauthorized access to computer networks is illegal.")
    print("Use at your own risk.")
    print("=" * 60 + "\n")
    
    # Initialize and start
    try:
        pendonn = PenDonn(config_path)
        pendonn.start()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
