"""
SSH Scanner Plugin
Tests for weak SSH credentials and misconfigurations
"""

import subprocess
import paramiko
from typing import List, Dict
import sys
import os
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class SSHScanner(PluginBase):
    """SSH security scanner"""
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """
        Scan for SSH vulnerabilities
        
        Args:
            scan_id: Database scan ID
            hosts: List of IP addresses
            scan_results: Nmap scan results
        
        Returns:
            Results dictionary
        """
        self.log_info("Starting SSH vulnerability scan")
        
        vulnerabilities_found = 0
        results = []
        
        # Common weak credentials to test
        weak_credentials = [
            ('root', 'root'),
            ('root', 'toor'),
            ('root', ''),
            ('admin', 'admin'),
            ('pi', 'raspberry'),
            ('ubuntu', 'ubuntu')
        ]
        
        # Find hosts with SSH open
        ssh_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            for port_info in ports:
                if port_info['port'] == 22 or 'ssh' in port_info.get('service', '').lower():
                    ssh_hosts.append({
                        'host': host,
                        'port': port_info['port']
                    })
        
        self.log_info(f"Found {len(ssh_hosts)} SSH servers")
        
        # Scan each SSH host
        for ssh_host in ssh_hosts:
            host = ssh_host['host']
            port = ssh_host['port']
            
            self.log_info(f"Scanning SSH on {host}:{port}")
            
            # Check SSH version
            version_info = self._get_ssh_version(host, port)
            if version_info and 'OpenSSH' in version_info:
                # Extract version
                try:
                    version = version_info.split('OpenSSH_')[1].split()[0]
                    major = int(version.split('.')[0])
                    
                    # Check for old versions
                    if major < 7:
                        self.log_warning(f"Old SSH version on {host}: {version}")
                        
                        self.db.add_vulnerability(
                            scan_id=scan_id,
                            host=host,
                            port=port,
                            service='ssh',
                            vuln_type='Outdated SSH Version',
                            severity='medium',
                            description=f'SSH version {version} is outdated and may contain vulnerabilities.',
                            plugin_name=self.name
                        )
                        
                        vulnerabilities_found += 1
                
                except Exception as e:
                    self.log_error(f"Version parsing error: {e}")
            
            # Test weak credentials
            for username, password in weak_credentials:
                if self._test_ssh_credentials(host, port, username, password):
                    self.log_warning(f"Weak SSH credentials found on {host}: {username}:{password}")
                    
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=port,
                        service='ssh',
                        vuln_type='Weak SSH Credentials',
                        severity='critical',
                        description=f'SSH accessible with weak credentials: {username}:{password}',
                        plugin_name=self.name
                    )
                    
                    vulnerabilities_found += 1
                    break  # Don't test more once we find one
            
            # Check for root login allowed
            if self._check_root_login(host, port):
                self.log_warning(f"Root login allowed on {host}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='ssh',
                    vuln_type='SSH Root Login Allowed',
                    severity='medium',
                    description='SSH permits root login, which is a security risk.',
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
        
        self.log_info(f"SSH scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'results': results
        }
    
    def _get_ssh_version(self, host: str, port: int) -> str:
        """Get SSH server version"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            
            # Read SSH banner
            banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
            
            sock.close()
            
            return banner
        
        except Exception as e:
            self.log_error(f"SSH version check error: {e}")
            return ""
    
    def _test_ssh_credentials(self, host: str, port: int, username: str, password: str) -> bool:
        """Test SSH credentials"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            
            client.close()
            return True
        
        except paramiko.AuthenticationException:
            return False
        except Exception as e:
            self.log_error(f"SSH credential test error: {e}")
            return False
    
    def _check_root_login(self, host: str, port: int) -> bool:
        """Check if root login is permitted"""
        try:
            # Use nmap script to check
            result = subprocess.run(
                ['nmap', '-p', str(port), '--script', 'ssh-auth-methods', '--script-args', 'ssh.user=root', host],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check if password authentication is allowed for root
            return 'password' in result.stdout.lower() and 'root' in result.stdout.lower()
        
        except Exception as e:
            self.log_error(f"Root login check error: {e}")
            return False
