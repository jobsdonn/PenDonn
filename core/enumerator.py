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

logger = logging.getLogger(__name__)


class NetworkEnumerator:
    """Network enumeration and vulnerability scanning"""
    
    def __init__(self, config: Dict, database, plugin_manager):
        """Initialize network enumerator"""
        self.config = config
        self.db = database
        self.plugin_manager = plugin_manager
        
        self.enabled = config['enumeration']['enabled']
        self.auto_scan = config['enumeration']['auto_scan_on_crack']
        self.nmap_timing = config['enumeration']['nmap_timing']
        self.port_range = config['enumeration']['port_scan_range']
        self.scan_timeout = config['enumeration']['scan_timeout']
        
        self.running = False
        self.active_scans = {}  # scan_id -> scan_info
        
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
        while self.running:
            try:
                if self.auto_scan:
                    # Get cracked passwords
                    cracked = self.db.get_cracked_passwords()
                    
                    for entry in cracked:
                        # Check if already scanned
                        existing_scans = self.db.get_scans(network_id=None)
                        already_scanned = any(
                            s['ssid'] == entry['ssid'] and s['status'] == 'completed'
                            for s in existing_scans
                        )
                        
                        if not already_scanned:
                            # Start enumeration
                            self.enumerate_network(
                                entry['ssid'],
                                entry['bssid'],
                                entry['password']
                            )
                
                time.sleep(30)
            
            except Exception as e:
                logger.error(f"Scan monitor error: {e}")
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
            
            vulnerabilities_found = 0
            results = {
                'ssid': ssid,
                'bssid': bssid,
                'phases': {}
            }
            
            # Phase 1: Connect to network
            logger.info(f"Phase 1: Connecting to {ssid}...")
            connection_success = self._connect_to_network(ssid, password)
            
            if not connection_success:
                logger.error(f"Failed to connect to {ssid}")
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
            
            for host in hosts:
                host_scan = self._scan_host(host)
                scan_results.append(host_scan)
                
                # Check for common vulnerabilities
                vulns = self._check_vulnerabilities(scan_id, host, host_scan)
                vulnerabilities_found += len(vulns)
            
            results['phases']['port_scan'] = {
                'status': 'completed',
                'hosts_scanned': len(scan_results),
                'results': scan_results
            }
            
            # Phase 4: Run plugins
            logger.info(f"Phase 4: Running vulnerability plugins...")
            plugin_results = self._run_plugins(scan_id, hosts, scan_results)
            results['phases']['plugins'] = plugin_results
            vulnerabilities_found += plugin_results.get('vulnerabilities_found', 0)
            
            # Update scan with results
            self.db.update_scan(scan_id, 'completed', results, vulnerabilities_found)
            logger.info(f"Enumeration completed for {ssid}. Found {vulnerabilities_found} vulnerabilities.")
            
            # Disconnect from network
            self._disconnect_from_network()
        
        except Exception as e:
            logger.error(f"Enumeration error for scan {scan_id}: {e}")
            self.db.update_scan(scan_id, 'failed', {'error': str(e)}, 0)
        
        finally:
            if scan_id in self.active_scans:
                del self.active_scans[scan_id]
    
    def _connect_to_network(self, ssid: str, password: str) -> bool:
        """Connect to target network"""
        try:
            # Create WPA supplicant configuration
            wpa_conf = f"""
network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
"""
            conf_file = '/tmp/wpa_supplicant_pendonn.conf'
            with open(conf_file, 'w') as f:
                f.write(wpa_conf)
            
            # Get management interface
            interface = self.config['wifi']['management_interface']
            
            # Kill existing wpa_supplicant
            subprocess.run(['killall', 'wpa_supplicant'], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            
            # Start wpa_supplicant
            subprocess.Popen([
                'wpa_supplicant',
                '-B',  # Background
                '-i', interface,
                '-c', conf_file
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            time.sleep(5)
            
            # Get IP address via DHCP
            subprocess.run(['dhclient', '-r', interface], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = subprocess.run(['dhclient', interface], 
                                  capture_output=True, timeout=30)
            
            time.sleep(3)
            
            # Verify connection
            result = subprocess.run(['ip', 'addr', 'show', interface], 
                                  capture_output=True, text=True)
            
            if 'inet ' in result.stdout:
                logger.info(f"Successfully connected to {ssid}")
                return True
            
            return False
        
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def _disconnect_from_network(self):
        """Disconnect from current network"""
        try:
            interface = self.config['wifi']['management_interface']
            subprocess.run(['killall', 'wpa_supplicant'], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['dhclient', '-r', interface], 
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Disconnected from network")
        except Exception as e:
            logger.error(f"Disconnection error: {e}")
    
    def _discover_hosts(self) -> List[str]:
        """Discover active hosts on network"""
        try:
            # Get local IP and network
            interface = self.config['wifi']['management_interface']
            result = subprocess.run(['ip', 'addr', 'show', interface], 
                                  capture_output=True, text=True)
            
            # Extract IP address
            import re
            ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', result.stdout)
            if not ip_match:
                return []
            
            network = ip_match.group(1)
            
            # Ping scan for host discovery
            logger.info(f"Scanning network: {network}")
            self.nm.scan(hosts=network, arguments=f'-sn {self.nmap_timing}')
            
            hosts = []
            for host in self.nm.all_hosts():
                if self.nm[host].state() == 'up':
                    hosts.append(host)
            
            logger.info(f"Discovered {len(hosts)} hosts")
            return hosts
        
        except Exception as e:
            logger.error(f"Host discovery error: {e}")
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
