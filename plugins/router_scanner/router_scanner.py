"""
Router & IoT Device Scanner Plugin
Tests default credentials on common home routers and IoT devices
"""

import requests
import socket
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class RouterScanner(PluginBase):
    """Router and IoT device scanner"""
    
    # Common router/IoT default credentials
    DEFAULT_CREDS = [
        # Routers
        ('admin', 'admin'),
        ('admin', 'password'),
        ('admin', ''),
        ('root', 'root'),
        ('root', 'admin'),
        ('admin', '1234'),
        ('admin', '12345'),
        ('user', 'user'),
        
        # TP-Link
        ('admin', 'admin'),
        
        # Netgear
        ('admin', 'password'),
        ('admin', '1234'),
        
        # D-Link
        ('admin', ''),
        ('Admin', ''),
        
        # Linksys
        ('admin', 'admin'),
        ('', 'admin'),
        
        # ASUS
        ('admin', 'admin'),
        
        # Cameras
        ('admin', ''),
        ('admin', '12345'),
        ('admin', 'admin'),
        ('root', '12345'),
        ('root', 'root'),
        ('admin', 'password'),
        ('888888', '888888'),
        
        # Printers
        ('admin', 'admin'),
        ('admin', ''),
        ('root', ''),
    ]
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for router/IoT vulnerabilities"""
        self.log_info("Starting Router/IoT device scan")
        
        vulnerabilities_found = 0
        
        # Find hosts with HTTP ports (routers usually have web interface)
        web_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            for port_info in ports:
                port = port_info['port']
                service = port_info.get('service', '').lower()
                
                if port in [80, 443, 8080, 8443, 8000, 8888] or 'http' in service:
                    web_hosts.append({
                        'host': host,
                        'port': port,
                        'protocol': 'https' if port in [443, 8443] else 'http'
                    })
        
        self.log_info(f"Found {len(web_hosts)} potential router/IoT devices")
        
        for web_host in web_hosts:
            host = web_host['host']
            port = web_host['port']
            protocol = web_host['protocol']
            
            url = f"{protocol}://{host}:{port}"
            
            self.log_info(f"Testing {url}")
            
            # Detect device type
            device_info = self._detect_device(url)
            
            # Test default credentials
            for username, password in self.DEFAULT_CREDS:
                if self._test_web_auth(url, username, password):
                    self.log_warning(f"Default credentials found on {url} - {username}:{password}")
                    
                    desc = f'Device accessible with default credentials: {username}:{password}'
                    if device_info:
                        desc += f' (Detected: {device_info})'
                    
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=port,
                        service='http',
                        vuln_type='Default Router/IoT Credentials',
                        severity='critical',
                        description=desc,
                        plugin_name=self.name
                    )
                    vulnerabilities_found += 1
                    break  # Found one, don't test more
        
        self.log_info(f"Router/IoT scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found
        }
    
    def _detect_device(self, url: str) -> str:
        """Try to detect device type from response"""
        try:
            response = requests.get(url, timeout=10, verify=False, allow_redirects=True)
            html = response.text.lower()
            
            # Check for common router signatures
            if 'tp-link' in html or 'tplink' in html:
                return 'TP-Link Router'
            elif 'netgear' in html:
                return 'Netgear Router'
            elif 'd-link' in html or 'dlink' in html:
                return 'D-Link Router'
            elif 'linksys' in html:
                return 'Linksys Router'
            elif 'asus' in html and 'router' in html:
                return 'ASUS Router'
            elif 'camera' in html or 'ipcam' in html:
                return 'IP Camera'
            elif 'printer' in html:
                return 'Network Printer'
            
            return None
        except Exception as e:
            self.log_debug(f"Device detection error: {e}")
            return None
    
    def _test_web_auth(self, url: str, username: str, password: str) -> bool:
        """Test HTTP Basic Auth"""
        try:
            # Try basic auth
            response = requests.get(
                url,
                auth=(username, password),
                timeout=10,
                verify=False,
                allow_redirects=False
            )
            
            # Success if not 401/403
            if response.status_code not in [401, 403]:
                return True
            
            # Try form-based auth on common endpoints
            login_endpoints = [
                '/login.cgi',
                '/login.asp',
                '/login.html',
                '/cgi-bin/login',
                '/api/login',
                '/login',
            ]
            
            for endpoint in login_endpoints:
                try:
                    login_url = url.rstrip('/') + endpoint
                    response = requests.post(
                        login_url,
                        data={'username': username, 'password': password, 'user': username, 'pass': password},
                        timeout=10,
                        verify=False,
                        allow_redirects=False
                    )
                    
                    if response.status_code in [200, 302] and 'error' not in response.text.lower():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            self.log_debug(f"Web auth test error: {e}")
            return False


def get_plugin():
    """Plugin entry point"""
    return RouterScanner
