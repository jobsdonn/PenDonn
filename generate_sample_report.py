"""
Generate Sample PDF Report

Creates a sample PDF report with mock data to demonstrate the report format.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.pdf_report import PDFReport

class MockDatabase:
    """Mock database for generating sample report"""
    
    def get_statistics(self):
        """Return mock statistics"""
        return {
            'networks': {
                'total': 15,
                'encrypted': 12,
                'open': 3
            },
            'handshakes': {
                'total': 8,
                'cracked': 3,
                'pending': 5
            },
            'passwords': {
                'total': 3
            },
            'scans': {
                'total': 5
            },
            'vulnerabilities': {
                'total': 27,
                'by_severity': {
                    'critical': 3,
                    'high': 8,
                    'medium': 11,
                    'low': 5
                }
            }
        }
    
    def get_all_networks(self):
        """Return mock networks"""
        return [
            {
                'ssid': 'HomeWiFi_5G',
                'bssid': 'AA:BB:CC:DD:EE:01',
                'channel': 36,
                'encryption': 'WPA2',
                'signal_strength': -45
            },
            {
                'ssid': 'NETGEAR84',
                'bssid': 'AA:BB:CC:DD:EE:02',
                'channel': 6,
                'encryption': 'WPA2',
                'signal_strength': -52
            },
            {
                'ssid': 'TP-Link_Guest',
                'bssid': 'AA:BB:CC:DD:EE:03',
                'channel': 11,
                'encryption': 'Open',
                'signal_strength': -68
            },
            {
                'ssid': 'Office_WiFi',
                'bssid': 'AA:BB:CC:DD:EE:04',
                'channel': 1,
                'encryption': 'WPA3',
                'signal_strength': -55
            },
            {
                'ssid': 'SmartHome_IoT',
                'bssid': 'AA:BB:CC:DD:EE:05',
                'channel': 6,
                'encryption': 'WPA2',
                'signal_strength': -62
            },
            {
                'ssid': 'Basement_AP',
                'bssid': 'AA:BB:CC:DD:EE:06',
                'channel': 11,
                'encryption': 'WPA2',
                'signal_strength': -75
            },
            {
                'ssid': 'Guest_Network',
                'bssid': 'AA:BB:CC:DD:EE:07',
                'channel': 1,
                'encryption': 'Open',
                'signal_strength': -58
            },
            {
                'ssid': 'SecureNet_5G',
                'bssid': 'AA:BB:CC:DD:EE:08',
                'channel': 149,
                'encryption': 'WPA2',
                'signal_strength': -48
            }
        ]
    
    def get_all_handshakes(self):
        """Return mock handshakes"""
        base_time = datetime.now() - timedelta(hours=3)
        return [
            {
                'ssid': 'HomeWiFi_5G',
                'bssid': 'AA:BB:CC:DD:EE:01',
                'captured_at': (base_time + timedelta(minutes=15)).isoformat(),
                'cracked': True
            },
            {
                'ssid': 'NETGEAR84',
                'bssid': 'AA:BB:CC:DD:EE:02',
                'captured_at': (base_time + timedelta(minutes=32)).isoformat(),
                'cracked': True
            },
            {
                'ssid': 'Office_WiFi',
                'bssid': 'AA:BB:CC:DD:EE:04',
                'captured_at': (base_time + timedelta(minutes=48)).isoformat(),
                'cracked': False
            },
            {
                'ssid': 'SmartHome_IoT',
                'bssid': 'AA:BB:CC:DD:EE:05',
                'captured_at': (base_time + timedelta(minutes=65)).isoformat(),
                'cracked': True
            },
            {
                'ssid': 'Basement_AP',
                'bssid': 'AA:BB:CC:DD:EE:06',
                'captured_at': (base_time + timedelta(minutes=82)).isoformat(),
                'cracked': False
            },
            {
                'ssid': 'SecureNet_5G',
                'bssid': 'AA:BB:CC:DD:EE:08',
                'captured_at': (base_time + timedelta(minutes=105)).isoformat(),
                'cracked': False
            }
        ]
    
    def get_all_passwords(self):
        """Return mock cracked passwords"""
        base_time = datetime.now() - timedelta(hours=2)
        return [
            {
                'ssid': 'HomeWiFi_5G',
                'password': 'Summer2024!',
                'cracked_at': (base_time + timedelta(minutes=45)).isoformat()
            },
            {
                'ssid': 'NETGEAR84',
                'password': 'password123',
                'cracked_at': (base_time + timedelta(minutes=18)).isoformat()
            },
            {
                'ssid': 'SmartHome_IoT',
                'password': 'admin1234',
                'cracked_at': (base_time + timedelta(minutes=92)).isoformat()
            }
        ]
    
    def get_all_scans(self):
        """Return mock network scans"""
        base_time = datetime.now() - timedelta(hours=1, minutes=30)
        return [
            {
                'id': 1,
                'network_name': 'HomeWiFi_5G',
                'scan_date': (base_time + timedelta(minutes=10)).isoformat(),
                'hosts_found': 12
            },
            {
                'id': 2,
                'network_name': 'NETGEAR84',
                'scan_date': (base_time + timedelta(minutes=25)).isoformat(),
                'hosts_found': 8
            },
            {
                'id': 3,
                'network_name': 'Office_WiFi',
                'scan_date': (base_time + timedelta(minutes=42)).isoformat(),
                'hosts_found': 25
            },
            {
                'id': 4,
                'network_name': 'SmartHome_IoT',
                'scan_date': (base_time + timedelta(minutes=58)).isoformat(),
                'hosts_found': 6
            },
            {
                'id': 5,
                'network_name': 'Guest_Network',
                'scan_date': (base_time + timedelta(minutes=75)).isoformat(),
                'hosts_found': 3
            }
        ]
    
    def get_all_vulnerabilities(self):
        """Return mock vulnerabilities"""
        return [
            # Critical vulnerabilities
            {
                'host': '192.168.1.1',
                'service': 'HTTP',
                'vuln_type': 'Default Credentials',
                'severity': 'critical',
                'description': 'Router accessible with default credentials: admin/admin'
            },
            {
                'host': '192.168.1.105',
                'service': 'SMB',
                'vuln_type': 'VPN Credentials Found',
                'severity': 'critical',
                'description': 'VPN configuration file found on SMB share: company-vpn.ovpn'
            },
            {
                'host': '192.168.1.254',
                'service': 'SNMP',
                'vuln_type': 'Information Disclosure',
                'severity': 'critical',
                'description': 'SNMP accessible with community string "public"'
            },
            
            # High severity
            {
                'host': '192.168.1.50',
                'service': 'FTP',
                'vuln_type': 'Anonymous Access',
                'severity': 'high',
                'description': 'FTP server allows anonymous access with read/write permissions'
            },
            {
                'host': '192.168.1.1',
                'service': 'UPnP',
                'vuln_type': 'Exposed UPnP',
                'severity': 'high',
                'description': 'UPnP service exposed - port forwarding possible'
            },
            {
                'host': '192.168.1.105',
                'service': 'SMB',
                'vuln_type': 'SSH Keys Found',
                'severity': 'high',
                'description': 'Private SSH keys found on SMB share: id_rsa, id_ed25519'
            },
            {
                'host': '192.168.1.200',
                'service': 'HTTP',
                'vuln_type': 'Weak Credentials',
                'severity': 'high',
                'description': 'IP Camera accessible with credentials: admin/12345'
            },
            {
                'host': '192.168.1.15',
                'service': 'DNS',
                'vuln_type': 'Open Recursion',
                'severity': 'high',
                'description': 'DNS server allows recursive queries (amplification risk)'
            },
            {
                'host': '192.168.1.25',
                'service': 'SSH',
                'vuln_type': 'Weak Configuration',
                'severity': 'high',
                'description': 'SSH server allows password authentication'
            },
            {
                'host': '192.168.1.88',
                'service': 'HTTP',
                'vuln_type': 'Directory Listing',
                'severity': 'high',
                'description': 'Web server has directory listing enabled'
            },
            {
                'host': 'AA:BB:CC:11:22:33',
                'service': 'bluetooth',
                'vuln_type': 'Bluetooth Injection Risk',
                'severity': 'high',
                'description': 'Bluetooth keyboard vulnerable to injection attacks'
            },
            
            # Medium severity
            {
                'host': '192.168.1.100',
                'service': 'HTTP',
                'vuln_type': 'Missing Headers',
                'severity': 'medium',
                'description': 'Web application missing security headers (X-Frame-Options, CSP)'
            },
            {
                'host': '192.168.1.150',
                'service': 'SMB',
                'vuln_type': 'Null Session',
                'severity': 'medium',
                'description': 'SMB server allows null session enumeration'
            },
            {
                'host': '192.168.1.20',
                'service': 'HTTP',
                'vuln_type': 'Outdated Software',
                'severity': 'medium',
                'description': 'Web server running outdated Apache 2.4.25'
            },
            {
                'host': '192.168.1.30',
                'service': 'SSH',
                'vuln_type': 'Outdated Software',
                'severity': 'medium',
                'description': 'SSH server running OpenSSH 7.4 (multiple CVEs)'
            },
            {
                'host': '192.168.1.55',
                'service': 'HTTP',
                'vuln_type': 'Information Disclosure',
                'severity': 'medium',
                'description': 'Server banner reveals exact version information'
            },
            {
                'host': 'AA:BB:CC:44:55:66',
                'service': 'bluetooth',
                'vuln_type': 'Insecure Bluetooth Service',
                'severity': 'medium',
                'description': 'Device exposes OBEX File Transfer service'
            },
            {
                'host': '192.168.1.75',
                'service': 'SNMP',
                'vuln_type': 'Weak Community String',
                'severity': 'medium',
                'description': 'SNMP accessible with community string "private"'
            },
            {
                'host': '192.168.1.90',
                'service': 'HTTP',
                'vuln_type': 'HTTP Methods',
                'severity': 'medium',
                'description': 'Web server allows potentially dangerous HTTP methods'
            },
            {
                'host': '192.168.1.110',
                'service': 'SMB',
                'vuln_type': 'Password Files',
                'severity': 'medium',
                'description': 'Password-related files found on SMB share'
            },
            {
                'host': '192.168.1.125',
                'service': 'DNS',
                'vuln_type': 'Zone Transfer',
                'severity': 'medium',
                'description': 'DNS server allows zone transfer (AXFR)'
            },
            {
                'host': '192.168.1.135',
                'service': 'FTP',
                'vuln_type': 'Weak Credentials',
                'severity': 'medium',
                'description': 'FTP accessible with credentials: ftp/ftp'
            },
            
            # Low severity
            {
                'host': '192.168.1.10',
                'service': 'HTTP',
                'vuln_type': 'SSL/TLS Issues',
                'severity': 'low',
                'description': 'Web server supports TLS 1.0/1.1 (deprecated)'
            },
            {
                'host': '192.168.1.45',
                'service': 'SSH',
                'vuln_type': 'Banner Information',
                'severity': 'low',
                'description': 'SSH banner reveals OS and version information'
            },
            {
                'host': 'AA:BB:CC:77:88:99',
                'service': 'bluetooth',
                'vuln_type': 'Information Disclosure',
                'severity': 'low',
                'description': 'Bluetooth device "John\'s iPhone" discoverable'
            },
            {
                'host': '192.168.1.65',
                'service': 'HTTP',
                'vuln_type': 'Cookie Settings',
                'severity': 'low',
                'description': 'Cookies missing Secure and HttpOnly flags'
            },
            {
                'host': '192.168.1.80',
                'service': 'Web',
                'vuln_type': 'Clickjacking',
                'severity': 'low',
                'description': 'Application vulnerable to clickjacking attacks'
            }
        ]
    
    def add_log(self, *args, **kwargs):
        """Mock log method"""
        pass

def main():
    """Generate sample PDF report"""
    print("Generating sample PDF report...")
    
    # Create mock database
    mock_db = MockDatabase()
    
    # Generate report
    output_path = "./pendonn_sample_report.pdf"
    report = PDFReport(mock_db, output_path)
    
    try:
        generated_path = report.generate_report()
        print(f"\n✓ Sample PDF report generated: {generated_path}")
        print(f"\nThe report includes:")
        print("  • Executive summary with statistics")
        print("  • Vulnerability severity pie chart")
        print("  • Discovered networks table")
        print("  • Captured handshakes")
        print("  • Cracked passwords")
        print("  • Network scans")
        print("  • 27 vulnerabilities (3 critical, 8 high, 11 medium, 5 low)")
        print("  • Security recommendations")
        print(f"\nOpen the file to view: {os.path.abspath(generated_path)}")
    except Exception as e:
        print(f"\n✗ Error generating PDF: {e}")
        print("\nMake sure reportlab is installed:")
        print("  pip install reportlab")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
