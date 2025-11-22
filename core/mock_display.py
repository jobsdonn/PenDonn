"""
PenDonn Mock Display Module
Simulates Waveshare display output to console for testing/development
"""

import os
import time
import threading
import logging
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class MockDisplay:
    """Mock display handler for development/testing"""
    
    def __init__(self, config: Dict, database):
        """Initialize mock display"""
        self.config = config
        self.db = database
        
        self.enabled = config['display']['enabled']
        self.refresh_interval = config['display']['refresh_interval']
        
        self.running = False
        self.update_thread = None
        
        logger.info("Mock Display initialized (DEBUG MODE)")
    
    def start(self):
        """Start mock display updates"""
        if not self.enabled:
            logger.info("Mock display is disabled")
            return
        
        logger.info("Starting mock display updates (console output)...")
        self.running = True
        
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
        logger.info("Mock display updates started")
    
    def stop(self):
        """Stop mock display updates"""
        if not self.enabled:
            return
        
        logger.info("Stopping mock display updates...")
        self.running = False
        
        if self.update_thread:
            self.update_thread.join(timeout=5)
        
        logger.info("Mock display stopped")
    
    def _update_loop(self):
        """Mock display update loop"""
        while self.running:
            try:
                self._render_display()
                time.sleep(self.refresh_interval)
            except Exception as e:
                logger.error(f"Mock display update error: {e}")
    
    def _render_display(self):
        """Render mock display to console"""
        try:
            # Get statistics
            stats = self.db.get_statistics()
            
            # Create console display
            display_text = f"""
╔════════════════════════════════════════════════════════╗
║              PenDonn - Mock Display Output              ║
╠════════════════════════════════════════════════════════╣
║ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          ║
║                                                          ║
║ Networks Discovered:     {str(stats.get('total_networks', 0)).ljust(4)}                       ║
║ Handshakes Captured:     {str(stats.get('total_handshakes', 0)).ljust(4)}                       ║
║ Passwords Cracked:       {str(stats.get('cracked_passwords', 0)).ljust(4)}                       ║
║ Active Scans:            {str(stats.get('active_scans', 0)).ljust(4)}                       ║
║ Vulnerabilities Found:   {str(stats.get('total_vulnerabilities', 0)).ljust(4)}                       ║
║                                                          ║
║ Status: RUNNING (DEBUG MODE)                            ║
╚════════════════════════════════════════════════════════╝
"""
            
            # Clear console and print (optional - comment out if too noisy)
            # os.system('cls' if os.name == 'nt' else 'clear')
            logger.debug(display_text)
            
        except Exception as e:
            logger.error(f"Mock display render error: {e}")
    
    def update_status(self, status: str):
        """Update status message"""
        logger.info(f"Mock Display Status: {status}")
