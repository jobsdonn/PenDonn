"""
PenDonn Mock WiFi Monitor Module
Simulates WiFi scanning and handshake capture for testing/development
"""

import os
import time
import threading
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MockWiFiMonitor:
    """Mock WiFi monitoring for development/testing"""
    
    def __init__(self, config: Dict, database):
        """Initialize mock WiFi monitor"""
        self.config = config
        self.db = database
        
        self.whitelist_ssids = set(config['whitelist']['ssids'])
        self.running = False
        self.current_channel = 1
        
        # Mock network data
        self.mock_networks = [
            {"ssid": "HomeNetwork", "bssid": "AA:BB:CC:DD:EE:01", "channel": 6, "encryption": "WPA2", "signal": -45},
            {"ssid": "CoffeeShop_WiFi", "bssid": "AA:BB:CC:DD:EE:02", "channel": 1, "encryption": "WPA2", "signal": -60},
            {"ssid": "Office_Guest", "bssid": "AA:BB:CC:DD:EE:03", "channel": 11, "encryption": "WPA2", "signal": -70},
            {"ssid": "Neighbor_2.4G", "bssid": "AA:BB:CC:DD:EE:04", "channel": 3, "encryption": "WPA2", "signal": -75},
            {"ssid": "TestNetwork", "bssid": "AA:BB:CC:DD:EE:05", "channel": 9, "encryption": "WPA2", "signal": -55},
            {"ssid": "", "bssid": "AA:BB:CC:DD:EE:06", "channel": 6, "encryption": "WPA2", "signal": -80},  # Hidden
        ]
        
        self.networks = {}
        self.handshake_dir = "./handshakes"
        os.makedirs(self.handshake_dir, exist_ok=True)
        
        logger.info("Mock WiFi Monitor initialized (DEBUG MODE)")
    
    def start(self):
        """Start mock WiFi monitoring"""
        logger.info("Starting mock WiFi monitor (simulating hardware)...")
        
        self.running = True
        
        # Start mock discovery thread
        discovery_thread = threading.Thread(target=self._mock_discovery, daemon=True)
        discovery_thread.start()
        
        # Start mock handshake capture
        handshake_thread = threading.Thread(target=self._mock_handshake_capture, daemon=True)
        handshake_thread.start()
        
        logger.info("Mock WiFi monitor started")
    
    def stop(self):
        """Stop mock WiFi monitoring"""
        logger.info("Stopping mock WiFi monitor...")
        self.running = False
        logger.info("Mock WiFi monitor stopped")
    
    def _mock_discovery(self):
        """Simulate network discovery"""
        logger.info("Mock network discovery started")
        
        # Discover networks gradually
        for network in self.mock_networks:
            if not self.running:
                break
            
            time.sleep(random.uniform(2, 5))  # Random discovery intervals
            
            ssid = network['ssid']
            bssid = network['bssid']
            
            # Skip whitelisted networks
            if ssid in self.whitelist_ssids:
                logger.debug(f"Skipping whitelisted network: {ssid}")
                continue
            
            # Simulate signal variations
            signal_strength = network['signal'] + random.randint(-5, 5)
            
            # Add to discovered networks
            self.networks[bssid] = {
                'ssid': ssid if ssid else f"Hidden_{bssid[-5:]}",
                'bssid': bssid,
                'channel': network['channel'],
                'encryption': network['encryption'],
                'signal_strength': signal_strength,
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat()
            }
            
            # Add to database
            self.db.add_network(
                ssid=self.networks[bssid]['ssid'],
                bssid=bssid,
                channel=network['channel'],
                encryption=network['encryption'],
                signal_strength=signal_strength
            )
            
            logger.info(f"Mock: Discovered network - SSID: {self.networks[bssid]['ssid']}, "
                       f"BSSID: {bssid}, Channel: {network['channel']}, "
                       f"Signal: {signal_strength} dBm")
        
        # Continue updating signal strengths
        while self.running:
            time.sleep(10)
            for bssid, network in self.networks.items():
                # Simulate signal strength changes
                network['signal_strength'] += random.randint(-3, 3)
                network['signal_strength'] = max(-90, min(-30, network['signal_strength']))
                network['last_seen'] = datetime.now().isoformat()
    
    def _mock_handshake_capture(self):
        """Simulate handshake capture"""
        logger.info("Mock handshake capture started")
        
        time.sleep(10)  # Wait for some networks to be discovered
        
        captured = set()
        
        while self.running:
            time.sleep(random.uniform(15, 30))  # Random handshake captures
            
            available_networks = [bssid for bssid in self.networks.keys() if bssid not in captured]
            
            if not available_networks:
                continue
            
            # Randomly capture a handshake
            bssid = random.choice(available_networks)
            network = self.networks[bssid]
            
            # Simulate handshake capture (60% success rate)
            if random.random() < 0.6:
                handshake_file = os.path.join(self.handshake_dir, f"{bssid.replace(':', '-')}.cap")
                
                # Create mock handshake file
                with open(handshake_file, 'wb') as f:
                    f.write(b'MOCK_HANDSHAKE_DATA_' + bssid.encode())
                
                # Add to database
                self.db.add_handshake(
                    network_id=self.db.get_network_id(bssid),
                    ssid=network['ssid'],
                    bssid=bssid,
                    handshake_file=handshake_file
                )
                
                captured.add(bssid)
                
                logger.info(f"Mock: Captured handshake - SSID: {network['ssid']}, BSSID: {bssid}")
            else:
                logger.debug(f"Mock: Handshake capture failed for {network['ssid']}")
    
    def get_statistics(self) -> Dict:
        """Get mock statistics"""
        return {
            'networks_discovered': len(self.networks),
            'current_channel': self.current_channel,
            'running': self.running
        }
