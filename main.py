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
from core.interface_manager import resolve_interfaces
from core.safety import preflight_check, SafetyConfig

# Configure logging with unbuffered output to prevent log stalling
log_dir = "./logs"
os.makedirs(log_dir, exist_ok=True)

# Force unbuffered stdout to prevent logging issues when display is running
if hasattr(sys.stdout, 'fileno'):
    try:
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)  # Line buffering
    except (AttributeError, OSError):
        pass  # Ignore if stdout can't be reopened (e.g., in some environments)

# Create stream handler with explicit flushing
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'pendonn.log')),
        stream_handler
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

        # SSH-lockout preflight. Run BEFORE we instantiate any module so
        # we don't accidentally start a scanner that's about to flip the
        # SSH iface into monitor mode. On fatal errors, exit cleanly with
        # a clear message — operator must fix config or arm override.
        interfaces = resolve_interfaces(self.config)
        preflight = preflight_check(self.config, interfaces)
        for line in preflight.info:
            logger.info("preflight: %s", line)
        for line in preflight.warnings:
            logger.warning("preflight: %s", line)
        for line in preflight.fatal_errors:
            logger.error("preflight: %s", line)
        if not preflight.ok:
            logger.error("=" * 60)
            logger.error("PREFLIGHT FAILED — refusing to start to prevent SSH lockout.")
            logger.error("Fix config issues above, or set safety.armed_override=true")
            logger.error("if you genuinely accept the lockout risk (see docs/SAFETY.md).")
            logger.error("=" * 60)
            sys.exit(2)

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
        self.enumerator = NetworkEnumerator(self.config, self.db, self.plugin_manager, self.wifi_monitor)
        
        # Initialize display (with protection against crashes)
        if self.config['display']['enabled']:
            logger.info("Initializing display...")
            try:
                from core.display import Display
                self.display = Display(self.config, self.db)
                logger.info("Display initialization complete")
            except Exception as e:
                logger.error(f"CRITICAL: Display initialization failed: {e}", exc_info=True)
                logger.warning("Continuing without display to prevent system crash")
                logger.warning("To troubleshoot: Set display.enabled=false in config and investigate logs")
                self.display = None
        else:
            logger.info("Display disabled in config")
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
        
        # Close database connections
        if self.db:
            self.db.close_all()
        
        logger.info("PenDonn stopped")
        sys.stdout.flush()  # Final flush
    
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
            
            # Force flush after status update
            sys.stdout.flush()
        
        except Exception as e:
            logger.error(f"Status update error: {e}", exc_info=True)
    
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
        
        # If start() returns (which it shouldn't for a daemon), log it
        logger.error("CRITICAL: Main daemon loop exited unexpectedly")
        logger.error("Service should be running continuously. Check for errors above.")
        
        # Keep process alive to allow restart by systemd
        logger.info("Waiting for systemd restart...")
        time.sleep(30)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
