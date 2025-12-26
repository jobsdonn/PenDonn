"""
FTP Scanner Plugin
Tests for anonymous FTP access and weak credentials
"""

from ftplib import FTP
from typing import List, Dict
import sys
import os
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class FTPScanner(PluginBase):
    """FTP vulnerability scanner"""
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for FTP vulnerabilities"""
        self.log_info("Starting FTP vulnerability scan")
        
        vulnerabilities_found = 0
        
        # Weak credentials to test
        weak_creds = [
            ('ftp', 'ftp'),
            ('anonymous', ''),
            ('anonymous', 'anonymous'),
            ('admin', 'admin'),
            ('root', 'root'),
            ('user', 'user')
        ]
        
        # Find hosts with FTP port open
        ftp_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            for port_info in ports:
                if port_info['port'] in [21, 2121] or 'ftp' in port_info.get('service', '').lower():
                    ftp_hosts.append({'host': host, 'port': port_info['port']})
        
        self.log_info(f"Found {len(ftp_hosts)} FTP servers")
        
        for ftp_host in ftp_hosts:
            host = ftp_host['host']
            port = ftp_host['port']
            
            self.log_info(f"Scanning FTP on {host}:{port}")
            
            # Check for anonymous FTP
            if self._check_anonymous_ftp(host, port):
                self.log_warning(f"Anonymous FTP access on {host}:{port}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='ftp',
                    vuln_type='Anonymous FTP Access',
                    severity='high',
                    description='FTP server allows anonymous access, potentially exposing sensitive files.',
                    plugin_name=self.name
                )
                vulnerabilities_found += 1
                continue  # Skip credential testing if anonymous works
            
            # Test weak credentials
            for username, password in weak_creds:
                if self._test_ftp_credentials(host, port, username, password):
                    self.log_warning(f"Weak FTP credentials on {host}:{port} - {username}:{password}")
                    
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=port,
                        service='ftp',
                        vuln_type='Weak FTP Credentials',
                        severity='critical',
                        description=f'FTP accessible with weak credentials: {username}:{password}',
                        plugin_name=self.name
                    )
                    vulnerabilities_found += 1
                    break
        
        self.log_info(f"FTP scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found
        }
    
    def _check_anonymous_ftp(self, host: str, port: int) -> bool:
        """Check for anonymous FTP access"""
        try:
            ftp = FTP(timeout=10)
            ftp.connect(host, port)
            ftp.login('anonymous', 'anonymous@')
            ftp.quit()
            return True
        except Exception as e:
            self.log_debug(f"Anonymous FTP check failed: {e}")
            return False
    
    def _test_ftp_credentials(self, host: str, port: int, username: str, password: str) -> bool:
        """Test FTP credentials"""
        try:
            ftp = FTP(timeout=10)
            ftp.connect(host, port)
            ftp.login(username, password)
            ftp.quit()
            return True
        except Exception as e:
            self.log_debug(f"FTP login failed for {username}: {e}")
            return False


def get_plugin():
    """Plugin entry point"""
    return FTPScanner
