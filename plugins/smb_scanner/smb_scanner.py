"""
SMB Vulnerability Scanner Plugin
Checks for SMB vulnerabilities including SMBv1 and EternalBlue
"""

import subprocess
import socket
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class SMBScanner(PluginBase):
    """SMB vulnerability scanner"""
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """
        Scan for SMB vulnerabilities
        
        Args:
            scan_id: Database scan ID
            hosts: List of IP addresses
            scan_results: Nmap scan results
        
        Returns:
            Results dictionary
        """
        self.log_info("Starting SMB vulnerability scan")
        
        vulnerabilities_found = 0
        results = []
        
        # Find hosts with SMB ports open
        smb_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            # Check for SMB ports (445, 139)
            has_smb = any(p['port'] in [445, 139] for p in ports)
            
            if has_smb:
                smb_hosts.append(host)
        
        self.log_info(f"Found {len(smb_hosts)} hosts with SMB")
        
        # Scan each SMB host
        for host in smb_hosts:
            self.log_info(f"Scanning SMB on {host}")
            
            # Check for SMBv1
            if self._check_smbv1(host):
                self.log_warning(f"SMBv1 detected on {host}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=445,
                    service='smb',
                    vuln_type='SMBv1 Enabled',
                    severity='high',
                    description='SMBv1 is enabled. This protocol is vulnerable to various attacks including EternalBlue.',
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
                results.append({
                    'host': host,
                    'vulnerability': 'SMBv1 Enabled',
                    'severity': 'high'
                })
            
            # Check for null session
            if self._check_null_session(host):
                self.log_warning(f"Null session allowed on {host}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=445,
                    service='smb',
                    vuln_type='SMB Null Session',
                    severity='medium',
                    description='SMB allows null session authentication, potentially exposing share information.',
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
                results.append({
                    'host': host,
                    'vulnerability': 'SMB Null Session',
                    'severity': 'medium'
                })
            
            # Check for open shares
            shares = self._enumerate_shares(host)
            if shares:
                self.log_info(f"Found {len(shares)} SMB shares on {host}")
                
                for share in shares:
                    if share['writable']:
                        self.log_warning(f"Writable share found: {share['name']} on {host}")
                        
                        self.db.add_vulnerability(
                            scan_id=scan_id,
                            host=host,
                            port=445,
                            service='smb',
                            vuln_type='Writable SMB Share',
                            severity='medium',
                            description=f"SMB share '{share['name']}' is writable without authentication.",
                            plugin_name=self.name
                        )
                        
                        vulnerabilities_found += 1
        
        self.log_info(f"SMB scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'results': results
        }
    
    def _check_smbv1(self, host: str) -> bool:
        """Check if SMBv1 is enabled"""
        try:
            # Use nmap script to check SMBv1
            result = subprocess.run(
                ['nmap', '-p', '445', '--script', 'smb-protocols', host],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check if SMBv1 is in output
            return 'SMBv1' in result.stdout or 'NT LM 0.12' in result.stdout
        
        except Exception as e:
            self.log_error(f"SMBv1 check error: {e}")
            return False
    
    def _check_null_session(self, host: str) -> bool:
        """Check for SMB null session"""
        try:
            # Use smbclient to attempt null session
            result = subprocess.run(
                ['smbclient', '-L', f'//{host}', '-N'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            # If we get share listings, null session is allowed
            return 'Sharename' in result.stdout
        
        except Exception as e:
            self.log_error(f"Null session check error: {e}")
            return False
    
    def _enumerate_shares(self, host: str) -> List[Dict]:
        """Enumerate SMB shares"""
        shares = []
        
        try:
            # List shares
            result = subprocess.run(
                ['smbclient', '-L', f'//{host}', '-N'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            # Parse shares
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Disk' in line:
                    parts = line.split()
                    if parts:
                        share_name = parts[0]
                        
                        # Check if writable
                        writable = self._check_share_writable(host, share_name)
                        
                        shares.append({
                            'name': share_name,
                            'writable': writable
                        })
        
        except Exception as e:
            self.log_error(f"Share enumeration error: {e}")
        
        return shares
    
    def _check_share_writable(self, host: str, share: str) -> bool:
        """Check if SMB share is writable"""
        try:
            # Attempt to create a file
            result = subprocess.run(
                ['smbclient', f'//{host}/{share}', '-N', '-c', 'mkdir testdir'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            return result.returncode == 0
        
        except Exception:
            return False
