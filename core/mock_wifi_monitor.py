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
        
        # Mock network data - realistic WiFi networks with varied characteristics
        self.mock_networks = [
            # Home networks (common SSID patterns)
            {"ssid": "NETGEAR42", "bssid": "AA:BB:CC:DD:EE:01", "channel": 6, "encryption": "WPA2", "signal": -45},
            {"ssid": "TP-Link_5F3A", "bssid": "AA:BB:CC:DD:EE:02", "channel": 1, "encryption": "WPA2", "signal": -60},
            {"ssid": "Linksys00234", "bssid": "AA:BB:CC:DD:EE:03", "channel": 11, "encryption": "WPA2", "signal": -70},
            {"ssid": "ASUS_Guest", "bssid": "AA:BB:CC:DD:EE:04", "channel": 3, "encryption": "WPA2", "signal": -75},
            {"ssid": "MyHome2024", "bssid": "AA:BB:CC:DD:EE:05", "channel": 9, "encryption": "WPA2", "signal": -55},
            
            # Coffee shop / public
            {"ssid": "Starbucks WiFi", "bssid": "AA:BB:CC:DD:EE:06", "channel": 6, "encryption": "WPA2", "signal": -50},
            {"ssid": "CoffeeShop_Guest", "bssid": "AA:BB:CC:DD:EE:07", "channel": 11, "encryption": "WPA2", "signal": -65},
            
            # Office networks
            {"ssid": "Office_Corp", "bssid": "AA:BB:CC:DD:EE:08", "channel": 1, "encryption": "WPA2", "signal": -70},
            {"ssid": "CompanyGuest", "bssid": "AA:BB:CC:DD:EE:09", "channel": 6, "encryption": "WPA2", "signal": -68},
            
            # Weak security / easy targets
            {"ssid": "SmartHome", "bssid": "AA:BB:CC:DD:EE:10", "channel": 4, "encryption": "WPA2", "signal": -52},
            {"ssid": "WiFi-2.4G", "bssid": "AA:BB:CC:DD:EE:11", "channel": 7, "encryption": "WPA2", "signal": -58},
            
            # Hidden network
            {"ssid": "", "bssid": "AA:BB:CC:DD:EE:12", "channel": 6, "encryption": "WPA2", "signal": -80},
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
        """Simulate network discovery with realistic timing"""
        logger.info("Mock network discovery started (simulating gradual detection)")
        
        # Discover networks gradually (more realistic)
        for network in self.mock_networks:
            if not self.running:
                break
            
            time.sleep(random.uniform(1, 3))  # Faster discovery - networks appear quickly
            
            ssid = network['ssid']
            bssid = network['bssid']
            
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
            
            # Set whitelist flag (True if in whitelist, False otherwise)
            if self.whitelist_ssids:
                is_whitelisted = ssid in self.whitelist_ssids
                self.db.set_whitelist(bssid, is_whitelisted)
            
            logger.info(f"Mock: Discovered network - SSID: {self.networks[bssid]['ssid']}, "
                       f"BSSID: {bssid}, Channel: {network['channel']}, "
                       f"Signal: {signal_strength} dBm")
        
        # Continue updating signal strengths (realistic signal fluctuation)
        while self.running:
            time.sleep(5)  # Update every 5s (matching improved scan timing)
            for bssid, network in self.networks.items():
                # Simulate signal strength changes
                network['signal_strength'] += random.randint(-3, 3)
                network['signal_strength'] = max(-90, min(-30, network['signal_strength']))
                network['last_seen'] = datetime.now().isoformat()
    
    def _mock_handshake_capture(self):
        """Simulate handshake capture with improved timing (matching real improvements)"""
        logger.info("Mock handshake capture started (simulating improved 5s checks + double deauth)")
        
        time.sleep(5)  # Wait for initial networks to be discovered (was 10s)
        
        captured = set()
        
        while self.running:
            # Simulate improved timing: check every 5-10 seconds instead of 15-30
            time.sleep(random.uniform(5, 10))
            
            available_networks = [bssid for bssid in self.networks.keys() if bssid not in captured]
            
            if not available_networks:
                continue
            
            # Randomly select a network to capture
            bssid = random.choice(available_networks)
            network = self.networks[bssid]
            
            # Only attack if no whitelist or network is in whitelist
            if self.whitelist_ssids and network['ssid'] not in self.whitelist_ssids:
                logger.debug(f"Mock: Skipping {network['ssid']} - not in whitelist")
                captured.add(bssid)  # Mark as processed to avoid checking again
                continue
            
            # Improved success rate (80% with double deauth) - was 60%
            if random.random() < 0.8:
                handshake_file = os.path.join(self.handshake_dir, f"{bssid.replace(':', '-')}.cap")
                
                # Create realistic mock handshake file with proper structure
                # This simulates a real pcap file with WPA2 handshake
                handshake_data = self._create_mock_pcap(bssid, network['ssid'])
                
                with open(handshake_file, 'wb') as f:
                    f.write(handshake_data)
                
                # Get network ID from database
                network_entry = self.db.get_network_by_bssid(bssid)
                if not network_entry:
                    logger.error(f"Mock: Network not found in database for BSSID: {bssid}")
                    continue
                
                # Add to database
                self.db.add_handshake(
                    network_id=network_entry['id'],
                    ssid=network['ssid'],
                    bssid=bssid,
                    file_path=handshake_file
                )
                
                captured.add(bssid)
                
                logger.info(f"Mock: ✓ Captured handshake - SSID: {network['ssid']}, BSSID: {bssid} "
                           f"(improved timing + double deauth)")
            else:
                logger.debug(f"Mock: ✗ Handshake capture failed for {network['ssid']} (will retry)")
    
    def _create_mock_pcap(self, bssid: str, ssid: str) -> bytes:
        """Create a realistic mock pcap file with WPA2 handshake data"""
        # Simplified pcap header + frame data
        # This creates a file that's large enough to pass size checks (>1KB)
        pcap_header = b'\xd4\xc3\xb2\xa1\x02\x00\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\x00\x00\x01\x00\x00\x00'
        
        # Mock packet data - simulate EAPOL frames (WPA handshake)
        mock_packet = b'\x00' * 256  # Packet placeholder
        mock_eapol = b'\x88\x8e' + b'\x00' * 128  # EAPOL type + data
        
        # Build realistic-sized capture file
        capture_data = pcap_header
        for i in range(4):  # 4-way handshake
            capture_data += mock_packet + mock_eapol
        
        # Add network identifiers
        capture_data += f"SSID:{ssid}|BSSID:{bssid}".encode()
        
        # Pad to ensure >1KB (cracker checks file size)
        while len(capture_data) < 1536:
            capture_data += b'\x00'
        
        return capture_data
    
    def get_statistics(self) -> Dict:
        """Get mock statistics"""
        return {
            'networks_discovered': len(self.networks),
            'current_channel': self.current_channel,
            'running': self.running
        }
