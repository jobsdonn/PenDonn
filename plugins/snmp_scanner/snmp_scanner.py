"""
SNMP Scanner Plugin
Tests for default SNMP community strings and information disclosure
"""

from pysnmp.hlapi import *
from typing import List, Dict
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase


class SNMPScanner(PluginBase):
    """SNMP vulnerability scanner"""
    
    # Common SNMP community strings
    COMMUNITY_STRINGS = [
        'public',
        'private',
        'community',
        'snmp',
        'admin',
        'manager',
        'cisco',
        'default',
        'read',
        'write',
        '0',
        '1234',
    ]
    
    def run(self, scan_id: int, hosts: List[str], scan_results: List[Dict]) -> Dict:
        """Scan for SNMP vulnerabilities"""
        self.log_info("Starting SNMP vulnerability scan")
        
        vulnerabilities_found = 0
        
        # Find hosts with SNMP port open
        snmp_hosts = []
        for host_scan in scan_results:
            host = host_scan.get('ip')
            ports = host_scan.get('ports', [])
            
            if any(p['port'] == 161 for p in ports):
                snmp_hosts.append(host)
        
        self.log_info(f"Found {len(snmp_hosts)} hosts with SNMP")
        
        for host in snmp_hosts:
            self.log_info(f"Testing SNMP on {host}")
            
            # Test community strings
            for community in self.COMMUNITY_STRINGS:
                if self._test_snmp_community(host, community):
                    self.log_warning(f"Valid SNMP community string on {host}: {community}")
                    
                    # Get system info
                    sys_info = self._get_system_info(host, community)
                    
                    desc = f'SNMP accessible with community string: {community}'
                    if sys_info:
                        desc += f'\\n\\nSystem Information:\\n{sys_info}'
                    
                    severity = 'critical' if community in ['public', 'private'] else 'high'
                    
                    self.db.add_vulnerability(
                        scan_id=scan_id,
                        host=host,
                        port=161,
                        service='snmp',
                        vuln_type='Weak SNMP Community String',
                        severity=severity,
                        description=desc,
                        plugin_name=self.name
                    )
                    vulnerabilities_found += 1
                    break  # Found one, don't test more
        
        self.log_info(f"SNMP scan complete. Found {vulnerabilities_found} vulnerabilities")
        
        return {
            'vulnerabilities': vulnerabilities_found
        }
    
    def _test_snmp_community(self, host: str, community: str) -> bool:
        """Test SNMP community string"""
        try:
            # Try to get sysDescr (1.3.6.1.2.1.1.1.0)
            errorIndication, errorStatus, errorIndex, varBinds = next(
                getCmd(SnmpEngine(),
                      CommunityData(community),
                      UdpTransportTarget((host, 161), timeout=5.0, retries=1),
                      ContextData(),
                      ObjectType(ObjectIdentity('1.3.6.1.2.1.1.1.0')))
            )
            
            if errorIndication or errorStatus:
                return False
            
            return True
        except Exception as e:
            self.log_debug(f"SNMP test error: {e}")
            return False
    
    def _get_system_info(self, host: str, community: str) -> str:
        """Get system information via SNMP"""
        try:
            info = []
            
            # OIDs to query
            oids = {
                '1.3.6.1.2.1.1.1.0': 'System Description',
                '1.3.6.1.2.1.1.5.0': 'Hostname',
                '1.3.6.1.2.1.1.6.0': 'Location',
                '1.3.6.1.2.1.1.4.0': 'Contact',
            }
            
            for oid, name in oids.items():
                try:
                    errorIndication, errorStatus, errorIndex, varBinds = next(
                        getCmd(SnmpEngine(),
                              CommunityData(community),
                              UdpTransportTarget((host, 161), timeout=5.0, retries=1),
                              ContextData(),
                              ObjectType(ObjectIdentity(oid)))
                    )
                    
                    if not errorIndication and not errorStatus:
                        for varBind in varBinds:
                            value = str(varBind[1])
                            if value and value != 'No Such Object currently exists':
                                info.append(f'{name}: {value}')
                except:
                    continue
            
            return '\\n'.join(info) if info else None
        except Exception as e:
            self.log_debug(f"SNMP info gathering error: {e}")
            return None


def get_plugin():
    """Plugin entry point"""
    return SNMPScanner
