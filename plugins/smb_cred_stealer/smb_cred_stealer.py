"""
SMB Credential Stealer Plugin
Extracts credentials and sensitive files from SMB shares
"""

import subprocess
from typing import List, Dict
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class SMBCredStealer(PluginBase):
    """SMB credential and file stealer"""
    
    # Interesting files to look for
    INTERESTING_FILES = [
        # Windows
        r'.*\.rdp$',  # RDP connections
        r'.*unattend\.xml$',  # Windows install files with passwords
        r'.*\.vnc$',  # VNC passwords
        r'.*\.ppk$',  # PuTTY private keys
        r'.*id_rsa.*',  # SSH keys
        r'.*\.pem$',  # Certificates
        
        # Credentials
        r'.*password.*\.txt$',
        r'.*passwd.*\.txt$',
        r'.*credential.*\.txt$',
        r'.*secret.*\.txt$',
        
        # Config files
        r'.*\.config$',
        r'.*\.conf$',
        r'.*\.cfg$',
        r'.*\.ini$',
        
        # Database
        r'.*\.mdb$',  # Access databases
        r'.*\.accdb$',
        
        # VPN
        r'.*\.ovpn$',  # OpenVPN configs
        r'.*\.pcf$',  # Cisco VPN
    ]
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for accessible SMB shares and steal credentials"""
        self.log_info("Starting SMB credential extraction")
        
        vulnerabilities_found = 0
        files_found = []
        
        # Find hosts with SMB
        smb_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            if any(p['port'] in [445, 139] for p in ports):
                smb_hosts.append(host)
        
        self.log_info(f"Found {len(smb_hosts)} hosts with SMB")
        
        for host in smb_hosts:
            self.log_info(f"Scanning SMB shares on {host}")
            
            # Enumerate shares
            shares = self._enumerate_shares(host)
            
            for share in shares:
                share_name = share['name']
                
                # Skip administrative shares
                if share_name.endswith('$') and share_name not in ['C$', 'D$', 'E$']:
                    continue
                
                self.log_info(f"Searching share: \\\\{host}\\{share_name}")
                
                # Search for interesting files
                interesting_files = self._search_share(host, share_name)
                
                if interesting_files:
                    self.log_warning(f"Found {len(interesting_files)} sensitive files on \\\\{host}\\{share_name}")
                    
                    files_list = '\\n'.join(interesting_files[:10])  # Limit to first 10
                    if len(interesting_files) > 10:
                        files_list += f'\\n... and {len(interesting_files) - 10} more'
                    
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=445,
                        service='smb',
                        vuln_type='Sensitive Files on SMB Share',
                        severity='high',
                        description=f'Found {len(interesting_files)} sensitive files on share {share_name}:\\n{files_list}',
                        plugin_name=self.name
                    )
                    vulnerabilities_found += 1
                    files_found.extend(interesting_files)
        
        self.log_info(f"SMB credential scan complete. Found {len(files_found)} sensitive files")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'files_found': len(files_found)
        }
    
    def _enumerate_shares(self, host: str) -> List[Dict]:
        """Enumerate SMB shares"""
        try:
            # Try anonymous access first
            result = subprocess.run(
                ['smbclient', '-L', f'//{host}', '-N'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            shares = []
            for line in result.stdout.split('\\n'):
                if 'Disk' in line or 'IPC' in line:
                    parts = line.split()
                    if len(parts) >= 1:
                        shares.append({'name': parts[0], 'type': 'Disk' if 'Disk' in line else 'IPC'})
            
            return shares
        except Exception as e:
            self.log_debug(f"Share enumeration error: {e}")
            return []
    
    def _search_share(self, host: str, share: str) -> List[str]:
        """Search for interesting files in a share"""
        try:
            # Try to list files recursively
            result = subprocess.run(
                ['smbclient', f'//{host}/{share}', '-N', '-c', 'recurse ON; ls'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            interesting = []
            for line in result.stdout.split('\\n'):
                # Parse file listings
                if not line.strip() or 'blocks available' in line or 'blocks of size' in line:
                    continue
                
                # Check against interesting file patterns
                for pattern in self.INTERESTING_FILES:
                    if re.search(pattern, line, re.IGNORECASE):
                        # Extract filename
                        parts = line.split()
                        if len(parts) >= 1:
                            interesting.append(parts[0])
                        break
            
            return interesting
        except Exception as e:
            self.log_debug(f"Share search error: {e}")
            return []


def get_plugin():
    """Plugin entry point"""
    return SMBCredStealer
