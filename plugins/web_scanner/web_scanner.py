"""
Web Vulnerability Scanner Plugin
Checks for common web vulnerabilities and misconfigurations
"""

import requests
import subprocess
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class WebScanner(PluginBase):
    """Web vulnerability scanner"""
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """
        Scan for web vulnerabilities
        
        Args:
            scan_id: Database scan ID
            hosts: List of IP addresses
            scan_results: Nmap scan results
        
        Returns:
            Results dictionary
        """
        self.log_info("Starting web vulnerability scan")
        
        vulnerabilities_found = 0
        results = []
        
        # Find hosts with HTTP/HTTPS ports open
        web_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            for port_info in ports:
                port = port_info['port']
                service = port_info.get('service', '').lower()
                
                # Check for HTTP/HTTPS
                if port in [80, 443, 8080, 8443] or 'http' in service:
                    protocol = 'https' if port in [443, 8443] or 'https' in service else 'http'
                    web_hosts.append({
                        'host': host,
                        'port': port,
                        'protocol': protocol
                    })
        
        self.log_info(f"Found {len(web_hosts)} web servers")
        
        # Scan each web host
        for web_host in web_hosts:
            host = web_host['host']
            port = web_host['port']
            protocol = web_host['protocol']
            
            url = f"{protocol}://{host}:{port}"
            
            self.log_info(f"Scanning {url}")
            
            # Check for directory listing
            if self._check_directory_listing(url):
                self.log_warning(f"Directory listing enabled on {url}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='http',
                    vuln_type='Directory Listing',
                    severity='low',
                    description='Directory listing is enabled, potentially exposing sensitive files.',
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
            
            # Check security headers
            missing_headers = self._check_security_headers(url)
            if missing_headers:
                self.log_warning(f"Missing security headers on {url}: {', '.join(missing_headers)}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='http',
                    vuln_type='Missing Security Headers',
                    severity='low',
                    description=f"Missing security headers: {', '.join(missing_headers)}",
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
            
            # Check for default credentials on common paths
            if self._check_default_credentials(url):
                self.log_warning(f"Default credentials found on {url}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='http',
                    vuln_type='Default Credentials',
                    severity='critical',
                    description='Web application uses default credentials.',
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
            
            # Check for common sensitive files
            sensitive_files = self._check_sensitive_files(url)
            if sensitive_files:
                self.log_warning(f"Sensitive files found on {url}: {', '.join(sensitive_files)}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port,
                    service='http',
                    vuln_type='Exposed Sensitive Files',
                    severity='medium',
                    description=f"Sensitive files exposed: {', '.join(sensitive_files)}",
                    plugin_name=self.name
                )
                
                vulnerabilities_found += 1
            
            # Run nikto for comprehensive scan
            nikto_vulns = self._run_nikto(host, port)
            vulnerabilities_found += nikto_vulns
        
        self.log_info(f"Web scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'results': results
        }
    
    def _check_directory_listing(self, url: str) -> bool:
        """Check for directory listing"""
        try:
            response = requests.get(url, timeout=10, verify=False)
            
            # Look for common directory listing indicators
            indicators = [
                'Index of /',
                'Directory listing for',
                'Parent Directory',
                '<title>Index of'
            ]
            
            return any(ind in response.text for ind in indicators)
        
        except Exception as e:
            self.log_error(f"Directory listing check error: {e}")
            return False
    
    def _check_security_headers(self, url: str) -> List[str]:
        """Check for missing security headers"""
        missing = []
        
        try:
            response = requests.get(url, timeout=10, verify=False)
            headers = response.headers
            
            # Check for important security headers
            security_headers = [
                'X-Content-Type-Options',
                'X-Frame-Options',
                'Content-Security-Policy',
                'Strict-Transport-Security',
                'X-XSS-Protection'
            ]
            
            for header in security_headers:
                if header not in headers:
                    missing.append(header)
        
        except Exception as e:
            self.log_error(f"Security headers check error: {e}")
        
        return missing
    
    def _check_default_credentials(self, url: str) -> bool:
        """Check for default credentials"""
        # Common default credentials
        credentials = [
            ('admin', 'admin'),
            ('admin', 'password'),
            ('admin', ''),
            ('root', 'root'),
            ('administrator', 'administrator')
        ]
        
        # Common login paths
        login_paths = [
            '/admin',
            '/login',
            '/admin/login',
            '/administrator',
            '/wp-login.php',
            '/wp-admin'
        ]
        
        try:
            for path in login_paths:
                login_url = url + path
                
                # Try to access
                try:
                    response = requests.get(login_url, timeout=5, verify=False)
                    
                    if response.status_code == 200:
                        # Try credentials
                        for username, password in credentials:
                            try:
                                auth_response = requests.post(
                                    login_url,
                                    data={'username': username, 'password': password},
                                    timeout=5,
                                    verify=False
                                )
                                
                                # Check for successful login indicators
                                if 'dashboard' in auth_response.url.lower() or \
                                   'logout' in auth_response.text.lower():
                                    return True
                            
                            except:
                                continue
                
                except:
                    continue
        
        except Exception as e:
            self.log_error(f"Default credentials check error: {e}")
        
        return False
    
    def _check_sensitive_files(self, url: str) -> List[str]:
        """Check for exposed sensitive files"""
        sensitive_files = [
            '/.git/config',
            '/.env',
            '/config.php',
            '/wp-config.php',
            '/configuration.php',
            '/web.config',
            '/robots.txt',
            '/.htaccess',
            '/phpinfo.php',
            '/info.php',
            '/backup.sql',
            '/database.sql'
        ]
        
        found = []
        
        try:
            for file_path in sensitive_files:
                file_url = url + file_path
                
                try:
                    response = requests.get(file_url, timeout=5, verify=False)
                    
                    if response.status_code == 200 and len(response.content) > 0:
                        found.append(file_path)
                
                except:
                    continue
        
        except Exception as e:
            self.log_error(f"Sensitive files check error: {e}")
        
        return found
    
    def _run_nikto(self, host: str, port: int) -> int:
        """Run Nikto web scanner"""
        try:
            self.log_info(f"Running Nikto on {host}:{port}")
            
            # Run nikto
            result = subprocess.run(
                ['nikto', '-h', f'{host}', '-p', str(port), '-Format', 'txt'],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Count vulnerabilities in output (basic parsing)
            vuln_count = result.stdout.count('+ OSVDB-')
            
            self.log_info(f"Nikto found {vuln_count} items")
            
            return vuln_count
        
        except Exception as e:
            self.log_error(f"Nikto error: {e}")
            return 0


# Disable SSL warnings
requests.packages.urllib3.disable_warnings()
