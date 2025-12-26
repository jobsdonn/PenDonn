"""
VPN Credential Stealer Plugin
Extracts VPN configurations and credentials from accessible systems
"""

import requests
import subprocess
from typing import List, Dict
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class VPNCredStealer(PluginBase):
    """VPN credential stealer"""
    
    # Common VPN config locations
    VPN_PATHS = [
        # OpenVPN
        '/etc/openvpn',
        '/etc/openvpn/client',
        '/home/*/.config/openvpn',
        
        # Windows (via SMB)
        'Users/*/AppData/Roaming/OpenVPN',
        'Program Files/OpenVPN/config',
        'Program Files (x86)/OpenVPN/config',
        
        # Cisco
        '/opt/cisco/anyconnect',
        'Program Files/Cisco/Cisco AnyConnect',
        
        # WireGuard
        '/etc/wireguard',
        '/home/*/.config/wireguard',
    ]
    
    # VPN config file patterns
    VPN_PATTERNS = [
        r'.*\.ovpn$',  # OpenVPN
        r'.*\.conf$',  # OpenVPN/WireGuard
        r'.*\.pcf$',  # Cisco VPN
        r'.*\.pbk$',  # Windows VPN
        r'.*vpn.*\.txt$',
        r'.*vpn.*\.xml$',
    ]
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for VPN configurations and credentials"""
        self.log_info("Starting VPN credential extraction")
        
        vulnerabilities_found = 0
        vpn_configs_found = []
        
        # Check SMB shares for VPN configs
        smb_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            if any(p['port'] in [445, 139] for p in ports):
                smb_hosts.append(host)
        
        self.log_info(f"Searching {len(smb_hosts)} hosts for VPN configs")
        
        for host in smb_hosts:
            self.log_info(f"Searching {host} for VPN configurations")
            
            # Search for VPN files on shares
            vpn_files = self._search_vpn_configs(host)
            
            if vpn_files:
                self.log_warning(f"Found {len(vpn_files)} VPN configuration files on {host}")
                
                files_list = '\\n'.join(vpn_files[:10])
                if len(vpn_files) > 10:
                    files_list += f'\\n... and {len(vpn_files) - 10} more'
                
                # Extract credentials if possible
                creds = self._extract_vpn_credentials(host, vpn_files)
                
                desc = f'Found {len(vpn_files)} VPN configuration files:\\n{files_list}'
                if creds:
                    desc += f'\\n\\nExtracted credentials:\\n' + '\\n'.join(creds[:5])
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=445,
                    service='smb',
                    vuln_type='VPN Configuration Files Exposed',
                    severity='critical',
                    description=desc,
                    plugin_name=self.name
                )
                vulnerabilities_found += 1
                vpn_configs_found.extend(vpn_files)
        
        # Check web servers for VPN portals with weak auth
        web_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            for port_info in ports:
                port = port_info['port']
                if port in [443, 8443] or 'https' in port_info.get('service', '').lower():
                    web_hosts.append({'host': host, 'port': port})
        
        for web_host in web_hosts:
            host = web_host['host']
            port = web_host['port']
            
            # Check for VPN portals
            if self._check_vpn_portal(host, port):
                self.log_warning(f"VPN portal detected on {host}:{port}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='https',
                    vuln_type='VPN Portal Detected',
                    severity='medium',
                    description='VPN portal detected - potential target for credential attacks',
                    plugin_name=self.name
                )
                vulnerabilities_found += 1
        
        self.log_info(f"VPN scan complete. Found {len(vpn_configs_found)} configuration files")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'configs_found': len(vpn_configs_found)
        }
    
    def _search_vpn_configs(self, host: str) -> List[str]:
        """Search for VPN configuration files"""
        try:
            # Enumerate shares
            result = subprocess.run(
                ['smbclient', '-L', f'//{host}', '-N'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            vpn_files = []
            
            # Get share list
            shares = []
            for line in result.stdout.split('\\n'):
                if 'Disk' in line:
                    parts = line.split()
                    if len(parts) >= 1:
                        shares.append(parts[0])
            
            # Search each share
            for share in shares:
                if share.endswith('$') and share not in ['C$']:
                    continue
                
                try:
                    result = subprocess.run(
                        ['smbclient', f'//{host}/{share}', '-N', '-c', 'recurse ON; ls'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    
                    for line in result.stdout.split('\\n'):
                        for pattern in self.VPN_PATTERNS:
                            if re.search(pattern, line, re.IGNORECASE):
                                parts = line.split()
                                if len(parts) >= 1:
                                    vpn_files.append(f'{share}/{parts[0]}')
                                break
                except:
                    continue
            
            return vpn_files
        except Exception as e:
            self.log_debug(f"VPN config search error: {e}")
            return []
    
    def _extract_vpn_credentials(self, host: str, files: List[str]) -> List[str]:
        """Try to extract credentials from VPN config files"""
        credentials = []
        
        # Look for common credential patterns in filenames/paths
        for file in files:
            if any(keyword in file.lower() for keyword in ['auth', 'user', 'pass', 'credential']):
                credentials.append(f'Potential credential file: {file}')
        
        return credentials
    
    def _check_vpn_portal(self, host: str, port: int) -> bool:
        """Check for VPN portal"""
        try:
            url = f'https://{host}:{port}'
            response = requests.get(url, timeout=10, verify=False, allow_redirects=True)
            html = response.text.lower()
            
            # Check for VPN portal signatures
            vpn_keywords = [
                'anyconnect',
                'vpn',
                'fortinet',
                'fortigate',
                'pulse secure',
                'juniper',
                'checkpoint',
                'palo alto',
                'globalprotect',
                'openvpn',
            ]
            
            return any(keyword in html for keyword in vpn_keywords)
        except:
            return False


def get_plugin():
    """Plugin entry point"""
    return VPNCredStealer
