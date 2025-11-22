"""
PenDonn Test Data Generator
Generates realistic test data for development and testing
"""

import os
import random
import logging
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)


class TestDataGenerator:
    """Generate test data for PenDonn database"""
    
    def __init__(self, database):
        """Initialize test data generator"""
        self.db = database
        
        # Sample data pools
        self.sample_ssids = [
            "HomeNetwork_5G", "Starbucks_WiFi", "Office_Guest", 
            "ATT_WiFi_2.4G", "Neighbor_Network", "Hotel_Lobby",
            "Airport_Free", "CoffeeShop", "Library_Public",
            "Restaurant_Guest", "Mall_WiFi", "School_Network"
        ]
        
        self.sample_passwords = [
            "password123", "admin123", "welcome1", "qwerty123",
            "letmein", "12345678", "password", "admin",
            "guest123", "wifi2023", "internet", "default"
        ]
        
        self.vulnerability_types = [
            "SMBv1 Enabled", "Weak SSH Credentials", "Open FTP",
            "Default Credentials", "Directory Listing Enabled",
            "Missing Security Headers", "Outdated SSH Version",
            "Anonymous FTP Access", "Open Telnet", "Weak RDP Password"
        ]
        
        logger.info("Test Data Generator initialized")
    
    def generate_all(self, num_networks: int = 10, num_handshakes: int = 5, 
                    num_scans: int = 3, num_vulnerabilities: int = 8):
        """Generate complete test dataset"""
        logger.info("Generating test data...")
        
        self.generate_networks(num_networks)
        self.generate_handshakes(num_handshakes)
        self.generate_cracked_passwords(3)
        self.generate_scans(num_scans)
        self.generate_vulnerabilities(num_vulnerabilities)
        
        logger.info("Test data generation complete!")
    
    def generate_networks(self, count: int = 10):
        """Generate sample networks"""
        logger.info(f"Generating {count} sample networks...")
        
        for i in range(count):
            ssid = random.choice(self.sample_ssids) + f"_{i}"
            bssid = self._generate_mac()
            channel = random.choice([1, 6, 11])
            encryption = random.choice(["WPA2", "WPA3", "WPA/WPA2"])
            signal_strength = random.randint(-85, -30)
            
            self.db.add_network(
                ssid=ssid,
                bssid=bssid,
                channel=channel,
                encryption=encryption,
                signal_strength=signal_strength
            )
            
            logger.debug(f"Generated network: {ssid} ({bssid})")
    
    def generate_handshakes(self, count: int = 5):
        """Generate sample handshakes"""
        logger.info(f"Generating {count} sample handshakes...")
        
        networks = self.db.execute_query("SELECT * FROM networks ORDER BY RANDOM() LIMIT ?", (count,))
        
        handshake_dir = "./handshakes"
        os.makedirs(handshake_dir, exist_ok=True)
        
        for network in networks:
            handshake_file = os.path.join(handshake_dir, f"{network['bssid'].replace(':', '-')}.cap")
            
            # Create mock handshake file
            with open(handshake_file, 'wb') as f:
                f.write(b'MOCK_TEST_HANDSHAKE_DATA_' + network['bssid'].encode())
            
            self.db.add_handshake(
                network_id=network['id'],
                ssid=network['ssid'],
                bssid=network['bssid'],
                handshake_file=handshake_file
            )
            
            logger.debug(f"Generated handshake for: {network['ssid']}")
    
    def generate_cracked_passwords(self, count: int = 3):
        """Generate cracked passwords"""
        logger.info(f"Generating {count} cracked passwords...")
        
        handshakes = self.db.execute_query(
            "SELECT * FROM handshakes WHERE id NOT IN (SELECT handshake_id FROM cracked_passwords) ORDER BY RANDOM() LIMIT ?",
            (count,)
        )
        
        for handshake in handshakes:
            password = random.choice(self.sample_passwords)
            crack_time = random.randint(30, 3600)
            
            self.db.add_cracked_password(
                handshake_id=handshake['id'],
                ssid=handshake['ssid'],
                bssid=handshake['bssid'],
                password=password,
                crack_time=crack_time
            )
            
            logger.debug(f"Generated cracked password for: {handshake['ssid']}")
    
    def generate_scans(self, count: int = 3):
        """Generate network scans"""
        logger.info(f"Generating {count} network scans...")
        
        # Get networks with cracked passwords
        cracked = self.db.execute_query(
            "SELECT * FROM cracked_passwords ORDER BY RANDOM() LIMIT ?",
            (count,)
        )
        
        for crack in cracked:
            target_ip = self._generate_ip()
            gateway = ".".join(target_ip.split(".")[:-1]) + ".1"
            
            # Generate hosts
            num_hosts = random.randint(3, 10)
            hosts = [self._generate_ip(gateway.rsplit(".", 1)[0]) for _ in range(num_hosts)]
            
            scan_results = {
                "network": f"{gateway}/24",
                "hosts_found": num_hosts,
                "hosts": []
            }
            
            for host_ip in hosts:
                host_data = {
                    "ip": host_ip,
                    "hostname": f"device-{host_ip.split('.')[-1]}",
                    "mac": self._generate_mac(),
                    "ports": []
                }
                
                # Add random open ports
                num_ports = random.randint(1, 5)
                possible_ports = [22, 80, 443, 445, 3389, 21, 23, 3306, 5432, 8080]
                for port in random.sample(possible_ports, num_ports):
                    host_data["ports"].append({
                        "port": port,
                        "state": "open",
                        "service": self._get_service_name(port)
                    })
                
                scan_results["hosts"].append(host_data)
            
            self.db.add_scan(
                network_id=self.db.get_network_id(crack['bssid']),
                target_network=scan_results["network"],
                scan_results=scan_results
            )
            
            logger.debug(f"Generated scan for network: {crack['ssid']}")
    
    def generate_vulnerabilities(self, count: int = 8):
        """Generate sample vulnerabilities"""
        logger.info(f"Generating {count} vulnerabilities...")
        
        # Get recent scans
        scans = self.db.execute_query("SELECT * FROM scans ORDER BY RANDOM() LIMIT 3")
        
        for scan in scans:
            num_vulns = random.randint(1, 4)
            
            for _ in range(num_vulns):
                vuln_type = random.choice(self.vulnerability_types)
                severity = random.choice(["critical", "high", "medium", "low"])
                
                # Get a random host from scan results
                import json
                results = json.loads(scan['scan_results'])
                if results['hosts']:
                    host = random.choice(results['hosts'])
                    target = f"{host['ip']}:{random.choice([p['port'] for p in host['ports']])}" if host['ports'] else host['ip']
                else:
                    target = self._generate_ip()
                
                description = self._generate_vulnerability_description(vuln_type, target)
                
                self.db.add_vulnerability(
                    scan_id=scan['id'],
                    target=target,
                    vulnerability_type=vuln_type,
                    severity=severity,
                    description=description
                )
                
                logger.debug(f"Generated {severity} vulnerability: {vuln_type}")
    
    def _generate_mac(self) -> str:
        """Generate random MAC address"""
        return ":".join([f"{random.randint(0, 255):02X}" for _ in range(6)])
    
    def _generate_ip(self, subnet: str = "192.168.1") -> str:
        """Generate random IP address"""
        return f"{subnet}.{random.randint(2, 254)}"
    
    def _get_service_name(self, port: int) -> str:
        """Get service name for port"""
        services = {
            22: "ssh", 80: "http", 443: "https", 445: "smb",
            3389: "rdp", 21: "ftp", 23: "telnet", 3306: "mysql",
            5432: "postgresql", 8080: "http-proxy"
        }
        return services.get(port, "unknown")
    
    def _generate_vulnerability_description(self, vuln_type: str, target: str) -> str:
        """Generate vulnerability description"""
        descriptions = {
            "SMBv1 Enabled": f"SMBv1 protocol detected on {target}. This legacy protocol has known vulnerabilities.",
            "Weak SSH Credentials": f"Weak or default SSH credentials detected on {target}. Brute force attack successful.",
            "Open FTP": f"Anonymous FTP access allowed on {target}. Sensitive data may be exposed.",
            "Default Credentials": f"Default administrator credentials detected on {target}.",
            "Directory Listing Enabled": f"Directory listing enabled on {target}. File structure exposed.",
            "Missing Security Headers": f"Critical security headers missing on {target}.",
            "Outdated SSH Version": f"Outdated SSH version detected on {target}. Known CVEs exist.",
            "Anonymous FTP Access": f"Anonymous FTP access enabled on {target}.",
            "Open Telnet": f"Unencrypted Telnet service running on {target}.",
            "Weak RDP Password": f"Weak RDP password detected on {target}. Account may be compromised."
        }
        return descriptions.get(vuln_type, f"Vulnerability detected: {vuln_type} on {target}")
