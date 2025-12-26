"""
UPnP Scanner Plugin
Detects exposed UPnP services (common security risk in home networks)
"""

import socket
import requests
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class UPnPScanner(PluginBase):
    """UPnP vulnerability scanner"""
    
    SSDP_DISCOVER = (
        'M-SEARCH * HTTP/1.1\\r\\n'
        'HOST: 239.255.255.250:1900\\r\\n'
        'MAN: "ssdp:discover"\\r\\n'
        'MX: 2\\r\\n'
        'ST: upnp:rootdevice\\r\\n'
        '\\r\\n'
    )
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for UPnP vulnerabilities"""
        self.log_info("Starting UPnP vulnerability scan")
        
        vulnerabilities_found = 0
        upnp_devices = []
        
        # Check each host for UPnP
        for host in hosts:
            self.log_info(f"Checking UPnP on {host}")
            
            # Try SSDP discovery
            devices = self._discover_upnp(host)
            
            if devices:
                self.log_warning(f"Found {len(devices)} UPnP devices on {host}")
                
                for device in devices:
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=1900,
                        service='upnp',
                        vuln_type='UPnP Service Exposed',
                        severity='medium',
                        description=f'UPnP service exposed: {device.get("location", "unknown")}. UPnP can allow external port forwarding and network manipulation.',
                        plugin_name=self.name
                    )
                    vulnerabilities_found += 1
                    upnp_devices.append(device)
        
        self.log_info(f"UPnP scan complete. Found {len(upnp_devices)} exposed services")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'devices_found': len(upnp_devices)
        }
    
    def _discover_upnp(self, host: str) -> List[Dict]:
        """Discover UPnP devices using SSDP"""
        devices = []
        
        try:
            # Send SSDP M-SEARCH
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(5)
            sock.sendto(self.SSDP_DISCOVER.encode(), (host, 1900))
            
            # Collect responses
            while True:
                try:
                    data, addr = sock.recvfrom(8192)
                    response = data.decode('utf-8', errors='ignore')
                    
                    # Parse response
                    device = {}
                    for line in response.split('\\r\\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            device[key.strip().lower()] = value.strip()
                    
                    if device:
                        devices.append(device)
                except socket.timeout:
                    break
            
            sock.close()
        except Exception as e:
            self.log_debug(f"UPnP discovery error: {e}")
        
        return devices


def get_plugin():
    """Plugin entry point"""
    return UPnPScanner
