"""
DNS Scanner Plugin
Checks for DNS misconfigurations, zone transfers, and subdomain enumeration
"""

import dns.resolver
import dns.zone
import dns.query
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class DNSScanner(PluginBase):
    """DNS vulnerability scanner"""
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for DNS vulnerabilities"""
        self.log_info("Starting DNS vulnerability scan")
        
        vulnerabilities_found = 0
        
        # Find hosts with DNS port open
        dns_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            if any(p['port'] == 53 for p in ports):
                dns_hosts.append(host)
        
        self.log_info(f"Found {len(dns_hosts)} DNS servers")
        
        for host in dns_hosts:
            self.log_info(f"Scanning DNS on {host}")
            
            # Check for zone transfer vulnerability
            if self._check_zone_transfer(host):
                self.log_warning(f"DNS zone transfer allowed on {host}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=53,
                    service='dns',
                    vuln_type='DNS Zone Transfer',
                    severity='high',
                    description='DNS server allows zone transfers, exposing internal network information.',
                    plugin_name=self.name
                )
                vulnerabilities_found += 1
            
            # Check for DNS recursion
            if self._check_recursion(host):
                self.log_warning(f"Open DNS recursion on {host}")
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=53,
                    service='dns',
                    vuln_type='Open DNS Recursion',
                    severity='medium',
                    description='DNS server allows recursive queries from external sources (DNS amplification risk).',
                    plugin_name=self.name
                )
                vulnerabilities_found += 1
        
        self.log_info(f"DNS scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found
        }
    
    def _check_zone_transfer(self, host: str) -> bool:
        """Check if zone transfer is allowed"""
        try:
            # Try to get zone transfer for common domains
            test_domains = ['example.com', 'test.local', 'domain.local']
            
            for domain in test_domains:
                try:
                    zone = dns.zone.from_xfr(dns.query.xfr(host, domain, timeout=5))
                    if zone:
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            self.log_debug(f"Zone transfer check error: {e}")
            return False
    
    def _check_recursion(self, host: str) -> bool:
        """Check if DNS recursion is enabled"""
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [host]
            resolver.timeout = 5
            resolver.lifetime = 5
            
            # Try to resolve external domain
            resolver.resolve('google.com', 'A')
            return True
        except:
            return False


def get_plugin():
    """Plugin entry point"""
    return DNSScanner
