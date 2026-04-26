"""
PenDonn Network Enumeration Module
Handles network scanning and vulnerability assessment
"""

import os
import time
import subprocess
import threading
import logging
import json
import socket
from datetime import datetime
from typing import Dict, List, Optional
import nmap
import signal
from .interface_manager import resolve_interfaces
from .safety import (
    SSHGuard,
    SafetyConfig,
    SafetyViolation,
    find_dhcpcd_pids_by_iface,
    find_supplicant_pids_by_iface,
)
from .secure_io import (
    encode_wpa_supplicant_psk,
    encode_wpa_supplicant_ssid,
    sanitize_iface_name,
    secure_temp_config,
)

logger = logging.getLogger(__name__)


class NetworkEnumerator:
    """Network enumeration and vulnerability scanning"""
    
    def __init__(self, config: Dict, database, plugin_manager, wifi_scanner=None):
        """Initialize network enumerator
        
        Args:
            config: Configuration dict
            database: Database instance
            plugin_manager: Plugin manager instance
            wifi_scanner: WiFi scanner instance for interface coordination (optional)
        """
        self.config = config
        self.db = database
        self.plugin_manager = plugin_manager
        self.wifi_scanner = wifi_scanner  # For coordinating interface usage
        
        self.enabled = config['enumeration']['enabled']
        self.auto_scan = config['enumeration']['auto_scan_on_crack']
        timing = config['enumeration']['nmap_timing']
        self.nmap_timing = timing if timing.startswith('-') else f'-{timing}'
        self.port_range = config['enumeration']['port_scan_range']
        self.scan_timeout = config['enumeration']['scan_timeout']
        
        # Resolve interfaces by MAC address (handles USB adapter name swapping)
        # Use monitor interface for enumeration - it switches from monitor to managed mode
        # Attacks will pause during enumeration (same interface used for scanning)
        interfaces = resolve_interfaces(config)
        self.enumeration_interface = interfaces['monitor']  # Use monitor interface (Realtek 8812AU - supports both modes)
        self.management_interface = interfaces['management']

        # SSH-lockout guard. Used before any operation that could touch the
        # management iface (kill its supplicant, switch its mode, etc.).
        self._ssh_guard = SSHGuard(
            SafetyConfig.from_dict(config.get('safety')), interfaces,
        )
        
        self.running = False
        self.active_scans = {}  # scan_id -> scan_info
        self.scanned_networks = set()  # Track which networks have been scanned
        
        logger.info(f"Enumeration will use {self.enumeration_interface} (monitor interface - supports both modes). Attacks will pause during enumeration.")
        
        # Initialize nmap only if available
        try:
            self.nm = nmap.PortScanner()
            logger.info("Network Enumerator initialized with nmap")
        except Exception as e:
            logger.warning(f"nmap not available: {e}")
            logger.warning("Network enumeration will be disabled")
            self.nm = None
            self.enabled = False
    
    def start(self):
        """Start enumeration service"""
        if not self.enabled:
            logger.info("Network enumeration is disabled")
            return
        
        logger.info("Starting network enumeration service...")
        self.running = True
        
        # Start scan monitor
        monitor = threading.Thread(target=self._scan_monitor, daemon=True)
        monitor.start()
        
        logger.info("Network enumeration service started")
    
    def stop(self):
        """Stop enumeration service"""
        logger.info("Stopping network enumeration service...")
        self.running = False
        self.active_scans.clear()
        logger.info("Network enumeration service stopped")
    
    def _scan_monitor(self):
        """Monitor for networks ready to scan"""
        scanned_networks = set()  # Track networks we've already started scanning
        
        while self.running:
            try:
                if self.auto_scan:
                    # Get cracked passwords
                    cracked = self.db.get_cracked_passwords()
                    
                    for entry in cracked:
                        bssid = entry['bssid']
                        
                        # Skip if we already started a scan for this network
                        if bssid in scanned_networks:
                            continue
                        
                        # Check if already scanned in database
                        existing_scans = self.db.get_scans(network_id=None)
                        already_scanned = any(
                            s['ssid'] == entry['ssid'] and s['status'] in ('completed', 'running')
                            for s in existing_scans
                        )
                        
                        if not already_scanned:
                            # Mark as started to prevent duplicates
                            scanned_networks.add(bssid)
                            
                            # Start enumeration
                            self.enumerate_network(
                                entry['ssid'],
                                entry['bssid'],
                                entry['password']
                            )
                
                time.sleep(30)
            
            except Exception as e:
                logger.error(f"Scan monitor error: {e}", exc_info=True)
                time.sleep(10)
    
    def enumerate_network(self, ssid: str, bssid: str, password: str):
        """Start network enumeration"""
        try:
            logger.info(f"Starting enumeration of {ssid}")
            
            # Get network ID
            networks = self.db.get_networks()
            network_id = next((n['id'] for n in networks if n['bssid'] == bssid), None)
            
            if not network_id:
                logger.warning(f"Network not found in database: {bssid}")
                return
            
            # Create scan entry
            scan_id = self.db.add_scan(network_id, ssid, 'full_enumeration')
            
            # Start scan in separate thread
            scan_thread = threading.Thread(
                target=self._perform_enumeration,
                args=(scan_id, ssid, bssid, password),
                daemon=True
            )
            scan_thread.start()
            
            self.active_scans[scan_id] = {
                'ssid': ssid,
                'bssid': bssid,
                'start_time': time.time(),
                'thread': scan_thread
            }
        
        except Exception as e:
            logger.error(f"Error starting enumeration: {e}")
    
    def _perform_enumeration(self, scan_id: int, ssid: str, bssid: str, password: str):
        """Perform full network enumeration"""
        try:
            logger.info(f"Performing enumeration for {ssid} (scan_id: {scan_id})")
            
            # REMOVED SAFETY CHECK: We're using wlan1 (attack_interface) for enumeration,
            # NOT the management interface (wlan2), so it's safe to enumerate any network
            # The enumeration interface will switch to managed mode temporarily while management stays up
            
            vulnerabilities_found = 0
            results = {
                'ssid': ssid,
                'bssid': bssid,
                'phases': {}
            }
            
            # Phase 1: Connect to network
            logger.info(f"Phase 1: Connecting to {ssid}...")
            connection_success, error_msg = self._connect_to_network(ssid, password)
            
            if not connection_success:
                logger.error(f"Failed to connect to {ssid}: {error_msg}")
                results['phases']['connection'] = {'status': 'failed', 'error': error_msg}
                self.db.update_scan(scan_id, 'failed', results, 0)
                return
            
            results['phases']['connection'] = {'status': 'success'}
            
            # Phase 2: Network discovery
            logger.info(f"Phase 2: Discovering hosts on {ssid}...")
            hosts = self._discover_hosts()
            results['phases']['discovery'] = {
                'status': 'completed',
                'hosts_found': len(hosts)
            }
            
            # Phase 3: Port scanning
            logger.info(f"Phase 3: Port scanning {len(hosts)} hosts...")
            scan_results = []
            
            try:
                for i, host in enumerate(hosts, 1):
                    logger.info(f"Scanning host {i}/{len(hosts)}: {host}")
                    host_scan = self._scan_host(host)
                    scan_results.append(host_scan)
                    
                    # Check for common vulnerabilities
                    vulns = self._check_vulnerabilities(scan_id, host, host_scan)
                    vulnerabilities_found += len(vulns)
                    logger.info(f"Host {host}: Found {len(host_scan.get('ports', []))} open ports, {len(vulns)} vulnerabilities")
            
                results['phases']['port_scan'] = {
                    'status': 'completed',
                    'hosts_scanned': len(scan_results),
                    'results': scan_results
                }
            except Exception as e:
                logger.error(f"Port scan error: {e}", exc_info=True)
                results['phases']['port_scan'] = {
                    'status': 'failed',
                    'error': str(e),
                    'hosts_scanned': len(scan_results)
                }
            
            # Phase 4: Run plugins
            logger.info(f"Phase 4: Running vulnerability plugins...")
            try:
                plugin_results = self._run_plugins(scan_id, hosts, scan_results)
                results['phases']['plugins'] = plugin_results
                vulnerabilities_found += plugin_results.get('vulnerabilities_found', 0)
                logger.info(f"Plugins found {plugin_results.get('vulnerabilities_found', 0)} additional vulnerabilities")
            except Exception as e:
                logger.error(f"Plugin execution error: {e}", exc_info=True)
                results['phases']['plugins'] = {
                    'status': 'failed',
                    'error': str(e)
                }
            
            # Update scan with results
            self.db.update_scan(scan_id, 'completed', results, vulnerabilities_found)
            logger.info(f"✓ Enumeration completed for {ssid}. Found {vulnerabilities_found} vulnerabilities, {len(hosts)} hosts")
            
            # Disconnect from network
            self._disconnect_from_network()
        
        except Exception as e:
            logger.error(f"Enumeration error for scan {scan_id}: {e}", exc_info=True)
            error_results = results.copy()
            error_results['error'] = str(e)
            error_results['error_type'] = type(e).__name__
            self.db.update_scan(scan_id, 'failed', error_results, 0)
        
        finally:
            if scan_id in self.active_scans:
                del self.active_scans[scan_id]
    
    def _connect_to_network(self, ssid: str, password: str) -> tuple:
        """Connect to target network using enumeration interface (wlan2)
        
        Returns:
            tuple: (success: bool, error_message: str)
        """
        try:
            # Pause attacks to borrow wlan2
            if self.wifi_scanner:
                logger.info("Pausing attacks to use wlan2 for enumeration")
                self.wifi_scanner.pause_for_enumeration()
            
            interface = self.enumeration_interface
            logger.info(f"Switching {interface} from monitor to managed mode")
            
            # Switch wlan2 from monitor to managed mode
            subprocess.run(['ip', 'link', 'set', interface, 'down'], check=True)
            subprocess.run(['iw', interface, 'set', 'type', 'managed'], check=True)
            subprocess.run(['ip', 'link', 'set', interface, 'up'], check=True)
            time.sleep(2)
            
            # Build WPA supplicant config in a 0600 file inside the secure
            # per-process temp dir (was world-readable /tmp/wpa_supplicant_pendonn.conf
            # with the PSK in cleartext — anyone on the box could grab it).
            #
            # Use the hex form for the SSID (sidesteps quote/escape pitfalls
            # for SSIDs containing quotes or non-ASCII bytes) and the proper
            # quoted/escaped form for the passphrase. Both helpers raise
            # ValueError on invalid input rather than silently producing a
            # broken config.
            safe_iface = sanitize_iface_name(interface)
            try:
                ssid_value = encode_wpa_supplicant_ssid(ssid)
                psk_value = encode_wpa_supplicant_psk(password)
            except ValueError as e:
                logger.error("Cannot build wpa_supplicant config: %s", e)
                return (False, f"invalid SSID/PSK for wpa_supplicant: {e}")

            wpa_conf = (
                "network={\n"
                f"    ssid={ssid_value}\n"
                f"    psk={psk_value}\n"
                "    key_mgmt=WPA-PSK\n"
                "}\n"
            )
            conf_file = secure_temp_config("wpa_supplicant")
            with open(conf_file, "w") as f:
                f.write(wpa_conf)
            
            # Kill wpa_supplicant for THIS interface only.
            #
            # Old code did `pgrep -f 'wpa_supplicant.*<iface>'` + `kill <pid>`.
            # That substring match could (and the audit confirmed it does)
            # match the system-wide wpa_supplicant on the management iface
            # — killing it severs SSH. Now we walk /proc and parse `-i <iface>`
            # from each cmdline, then run the resulting PIDs through
            # SSHGuard.assert_safe_to_kill_supplicant which filters out
            # anything on the management iface unless armed_override is set.
            try:
                pids_by_iface = find_supplicant_pids_by_iface()
                pids_to_kill = self._ssh_guard.assert_safe_to_kill_supplicant(
                    {interface: pids_by_iface.get(interface, [])}
                )
                for pid in pids_to_kill:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError) as e:
                        logger.warning(f"Could not SIGTERM wpa_supplicant pid {pid}: {e}")
                if pids_to_kill:
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"Could not kill existing wpa_supplicant for {interface}: {e}")
            
            # Start wpa_supplicant on enumeration interface
            logger.info(f"Starting wpa_supplicant on {safe_iface}")
            subprocess.Popen([
                'wpa_supplicant',
                '-B',  # Background
                '-i', safe_iface,
                '-c', conf_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            time.sleep(5)
            
            # Get IP address via DHCP (try dhcpcd first, then dhclient)
            logger.info(f"Requesting IP address on {interface}")
            dhcp_success = False
            
            # Check for dhcpcd (Raspberry Pi OS)
            if subprocess.run(['which', 'dhcpcd'], capture_output=True).returncode == 0:
                # Kill any existing dhcpcd for this interface ONLY.
                # Same anti-pgrep-substring fix as for wpa_supplicant: walk
                # /proc and identify per-iface dhcpcd by its argv. The
                # system-wide dhcpcd daemon (no -i / no positional iface)
                # is not in find_dhcpcd_pids_by_iface() output, so it can
                # never be selected here.
                try:
                    pids_by_iface = find_dhcpcd_pids_by_iface()
                    pids_to_kill = self._ssh_guard.assert_safe_to_kill_supplicant(
                        {interface: pids_by_iface.get(interface, [])}
                    )
                    for pid in pids_to_kill:
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except (ProcessLookupError, PermissionError) as e:
                            logger.warning(f"Could not SIGTERM dhcpcd pid {pid}: {e}")
                    if pids_to_kill:
                        time.sleep(1)
                        logger.info(f"Killed existing dhcpcd for {interface}")
                except Exception as e:
                    logger.warning(f"Could not kill existing dhcpcd: {e}")
                
                # Use dhcpcd in one-shot mode to avoid interfering with management interface
                # -n = one-shot (don't fork/daemonize)
                # -4 = IPv4 only
                # -w = wait for IP
                logger.info(f"Running dhcpcd in one-shot mode for {interface} only")
                result = subprocess.run(['dhcpcd', '-n', '-4', '-w', interface], 
                                      capture_output=True, timeout=30)
                dhcp_success = result.returncode == 0
            # Fallback to dhclient
            elif subprocess.run(['which', 'dhclient'], capture_output=True).returncode == 0:
                subprocess.run(['dhclient', '-r', interface], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                result = subprocess.run(['dhclient', interface], 
                                      capture_output=True, timeout=30)
                dhcp_success = result.returncode == 0
            else:
                error_msg = "Neither dhcpcd nor dhclient found"
                logger.error(error_msg)
                return (False, error_msg)
            
            time.sleep(3)
            
            # Verify connection
            result = subprocess.run(['ip', 'addr', 'show', interface], 
                                  capture_output=True, text=True)
            
            if 'inet ' in result.stdout:
                logger.info(f"Successfully connected to {ssid} on {interface}")
                return (True, "")
            else:
                error_msg = f"Failed to obtain IP on {interface}"
                logger.error(error_msg)
                return (False, error_msg)
        
        except subprocess.TimeoutExpired:
            error_msg = f"DHCP timeout on {interface}"
            logger.error(error_msg)
            return (False, error_msg)
        except FileNotFoundError as e:
            error_msg = f"Required tool not found: {e}"
            logger.error(error_msg)
            return (False, error_msg)
        except Exception as e:
            error_msg = f"Connection error: {e}"
            logger.error(error_msg)
            return (False, error_msg)
    
    def _disconnect_from_network(self):
        """Disconnect from network and restore monitor mode on enumeration interface"""
        interface = self.enumeration_interface
        
        try:
            logger.info(f"Disconnecting from network on {interface}")
            
            # Kill wpa_supplicant for this interface only — same SSHGuard-mediated
            # path as in _connect_to_network. See that comment for rationale.
            try:
                pids_by_iface = find_supplicant_pids_by_iface()
                pids_to_kill = self._ssh_guard.assert_safe_to_kill_supplicant(
                    {interface: pids_by_iface.get(interface, [])}
                )
                for pid in pids_to_kill:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except (ProcessLookupError, PermissionError) as e:
                        logger.warning(f"Could not SIGTERM wpa_supplicant pid {pid}: {e}")
                if pids_to_kill:
                    time.sleep(1)
            except Exception as e:
                logger.warning(f"Could not kill wpa_supplicant for {interface}: {e}")
            
            # Release DHCP (try dhcpcd first, then dhclient)
            if subprocess.run(['which', 'dhcpcd'], capture_output=True).returncode == 0:
                subprocess.run(['dhcpcd', '-k', interface], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif subprocess.run(['which', 'dhclient'], capture_output=True).returncode == 0:
                subprocess.run(['dhclient', '-r', interface], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except Exception as e:
            logger.error(f"Error during disconnection: {e}")
        
        finally:
            # CRITICAL: Always restore monitor mode and resume attacks
            try:
                logger.info(f"Restoring {interface} to monitor mode")
                subprocess.run(['ip', 'link', 'set', interface, 'down'], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['iw', interface, 'set', 'monitor', 'control'], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['ip', 'link', 'set', interface, 'up'], 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
                
                # Resume attacks
                if self.wifi_scanner:
                    logger.info("Resuming attacks")
                    self.wifi_scanner.resume_from_enumeration()
                    
                logger.info(f"Successfully restored {interface} to monitor mode")
                
            except Exception as e:
                logger.critical(f"FAILED to restore {interface} to monitor mode: {e}")
                logger.critical("Manual intervention required: iw wlan2 set monitor control")
                # Try emergency restore
                try:
                    subprocess.run(['ifconfig', interface, 'down'], check=False)
                    subprocess.run(['iwconfig', interface, 'mode', 'monitor'], check=False)
                    subprocess.run(['ifconfig', interface, 'up'], check=False)
                    logger.warning("Emergency restore attempted with ifconfig/iwconfig")
                except:
                    pass
    
    def _discover_hosts(self) -> List[str]:
        """Discover active hosts on network"""
        try:
            # Use enumeration interface (wlan2) not management interface
            interface = self.enumeration_interface
            result = subprocess.run(['ip', 'addr', 'show', interface], 
                                  capture_output=True, text=True)
            
            # Extract IP address
            import re
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', result.stdout)
            if not ip_match:
                logger.error(f"Could not determine network range from {interface}")
                return []
            
            network = ip_match.group(1)
            
            # Ping scan for host discovery
            logger.info(f"Scanning network: {network} on {interface}")
            self.nm.scan(hosts=network, arguments=f'-sn {self.nmap_timing}')
            
            hosts = []
            for host in self.nm.all_hosts():
                if self.nm[host].state() == 'up':
                    hosts.append(host)
                    hostname = ''
                    if 'hostnames' in self.nm[host] and self.nm[host]['hostnames']:
                        hostname = self.nm[host]['hostnames'][0].get('name', '')
                    logger.info(f"  ↳ {host} {hostname if hostname else '(no hostname)'}")
            
            logger.info(f"✓ Discovered {len(hosts)} active hosts")
            return hosts
        
        except Exception as e:
            logger.error(f"Host discovery error: {e}", exc_info=True)
            return []
    
    def _scan_host(self, host: str) -> Dict:
        """Scan a single host"""
        try:
            logger.info(f"Scanning host: {host}")
            
            # Port scan
            self.nm.scan(
                hosts=host,
                arguments=f'-p {self.port_range} -sV {self.nmap_timing}'
            )
            
            host_info = {
                'ip': host,
                'hostname': '',
                'ports': [],
                'os': ''
            }
            
            if host in self.nm.all_hosts():
                # Get hostname
                if 'hostnames' in self.nm[host]:
                    hostnames = self.nm[host]['hostnames']
                    if hostnames:
                        host_info['hostname'] = hostnames[0].get('name', '')
                
                # Get OS info
                if 'osmatch' in self.nm[host]:
                    os_matches = self.nm[host]['osmatch']
                    if os_matches:
                        host_info['os'] = os_matches[0].get('name', '')
                
                # Get open ports
                if 'tcp' in self.nm[host]:
                    for port, port_info in self.nm[host]['tcp'].items():
                        if port_info['state'] == 'open':
                            host_info['ports'].append({
                                'port': port,
                                'service': port_info.get('name', ''),
                                'version': port_info.get('version', ''),
                                'product': port_info.get('product', '')
                            })
            
            return host_info
        
        except Exception as e:
            logger.error(f"Host scan error for {host}: {e}")
            return {'ip': host, 'error': str(e)}
    
    def _check_vulnerabilities(self, scan_id: int, host: str, host_scan: Dict) -> List[Dict]:
        """Check for common vulnerabilities"""
        vulnerabilities = []
        
        try:
            # Check for common vulnerable services/ports
            vulnerable_services = {
                21: {'name': 'FTP', 'severity': 'medium', 'desc': 'FTP service exposed'},
                23: {'name': 'Telnet', 'severity': 'high', 'desc': 'Unencrypted Telnet service'},
                445: {'name': 'SMB', 'severity': 'medium', 'desc': 'SMB service (check for SMBv1)'},
                3389: {'name': 'RDP', 'severity': 'medium', 'desc': 'RDP service exposed'},
                5900: {'name': 'VNC', 'severity': 'medium', 'desc': 'VNC service exposed'},
                8080: {'name': 'HTTP-Proxy', 'severity': 'low', 'desc': 'HTTP proxy/web service'},
            }
            
            for port_info in host_scan.get('ports', []):
                port = port_info['port']
                service = port_info['service']
                
                if port in vulnerable_services:
                    vuln = vulnerable_services[port]
                    
                    vuln_id = self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=port,
                        service=service,
                        vuln_type=vuln['name'],
                        severity=vuln['severity'],
                        description=vuln['desc'],
                        plugin_name='builtin'
                    )
                    
                    vulnerabilities.append({
                        'id': vuln_id,
                        'host': host,
                        'port': port,
                        'type': vuln['name']
                    })
            
            # Check for anonymous FTP
            if any(p['port'] == 21 for p in host_scan.get('ports', [])):
                if self._check_anonymous_ftp(host):
                    vuln_id = self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=21,
                        service='ftp',
                        vuln_type='Anonymous FTP',
                        severity='high',
                        description='FTP allows anonymous login',
                        plugin_name='builtin'
                    )
                    vulnerabilities.append({
                        'id': vuln_id,
                        'host': host,
                        'port': 21,
                        'type': 'Anonymous FTP'
                    })
        
        except Exception as e:
            logger.error(f"Vulnerability check error: {e}")
        
        return vulnerabilities
    
    def _check_anonymous_ftp(self, host: str) -> bool:
        """Check for anonymous FTP access"""
        try:
            import ftplib
            ftp = ftplib.FTP(timeout=10)
            ftp.connect(host, 21)
            ftp.login('anonymous', 'anonymous@')
            ftp.quit()
            return True
        except:
            return False
    
    def _run_plugins(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Run vulnerability scanner plugins"""
        plugin_results = {
            'status': 'completed',  # Set default status
            'plugins_run': [],
            'vulnerabilities_found': 0
        }
        
        try:
            if self.plugin_manager:
                plugins = self.plugin_manager.get_enabled_plugins()
                
                for plugin in plugins:
                    try:
                        logger.info(f"Running plugin: {plugin.name}")
                        
                        result = plugin.run(scan_id, hosts, scan_results)
                        
                        plugin_results['plugins_run'].append({
                            'name': plugin.name,
                            'status': 'completed',
                            'vulnerabilities': result.get('vulnerabilities', 0)
                        })
                        
                        plugin_results['vulnerabilities_found'] += result.get('vulnerabilities', 0)
                    
                    except Exception as e:
                        logger.error(f"Plugin {plugin.name} error: {e}")
                        plugin_results['plugins_run'].append({
                            'name': plugin.name,
                            'status': 'failed',
                            'error': str(e)
                        })
        
        except Exception as e:
            logger.error(f"Plugin execution error: {e}")
        
        return plugin_results
    
    def get_status(self) -> Dict:
        """Get enumerator status"""
        return {
            'running': self.running,
            'active_scans': len(self.active_scans),
            'scans': [
                {
                    'scan_id': sid,
                    'ssid': info['ssid'],
                    'elapsed_time': int(time.time() - info['start_time'])
                }
                for sid, info in self.active_scans.items()
            ]
        }
