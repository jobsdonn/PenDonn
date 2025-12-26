"""
Bluetooth Enumeration Plugin

Scans for Bluetooth devices and services in range.
Detects device types, manufacturers, and potential vulnerabilities.

Author: PenDonn Team
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from core.plugin_manager import PluginBase
import subprocess
import json
import time
from datetime import datetime

class BluetoothScanner(PluginBase):
    """Bluetooth device and service scanner"""
    
    def __init__(self, config, db):
        super().__init__(config, db, "Bluetooth Scanner")
        self.scan_duration = 10  # seconds
        self.discovered_devices = []
        
    def run(self, scan_id, hosts, scan_results):
        """
        Scan for Bluetooth devices
        
        Args:
            scan_id: Database scan ID
            hosts: List of IP addresses (not used for Bluetooth)
            scan_results: Nmap results (not used for Bluetooth)
        
        Returns:
            {'vulnerabilities': count, 'results': [...]}
        """
        self.log_info("Starting Bluetooth enumeration")
        
        vulnerabilities_found = 0
        results = []
        
        # Check if Bluetooth is available
        if not self._check_bluetooth_available():
            self.log_warning("Bluetooth not available on this system")
            return {'vulnerabilities': 0, 'results': []}
        
        # Enable Bluetooth
        self._enable_bluetooth()
        
        # Scan for devices
        devices = self._scan_devices()
        
        if not devices:
            self.log_info("No Bluetooth devices found")
            return {'vulnerabilities': 0, 'results': []}
        
        self.log_info(f"Found {len(devices)} Bluetooth devices")
        
        # Enumerate each device
        for device in devices:
            mac = device.get('mac')
            name = device.get('name', 'Unknown')
            
            self.log_info(f"Enumerating device: {name} ({mac})")
            
            # Get device info
            device_info = self._get_device_info(mac)
            device.update(device_info)
            
            # Get services
            services = self._get_services(mac)
            device['services'] = services
            
            # Check for vulnerabilities
            vulns = self._check_vulnerabilities(device, scan_id)
            vulnerabilities_found += len(vulns)
            
            results.append({
                'device': device,
                'vulnerabilities': vulns
            })
        
        self.log_info(f"Bluetooth scan complete: {vulnerabilities_found} vulnerabilities found")
        
        return {
            'vulnerabilities': vulnerabilities_found,
            'results': results
        }
    
    def _check_bluetooth_available(self):
        """Check if Bluetooth adapter is available"""
        try:
            result = subprocess.run(
                ['hciconfig'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and 'hci0' in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _enable_bluetooth(self):
        """Enable Bluetooth adapter"""
        try:
            subprocess.run(['hciconfig', 'hci0', 'up'], check=True, timeout=5)
            self.log_info("Bluetooth adapter enabled")
        except Exception as e:
            self.log_warning(f"Could not enable Bluetooth: {e}")
    
    def _scan_devices(self):
        """
        Scan for Bluetooth devices
        
        Returns:
            list: List of discovered devices
        """
        devices = []
        
        try:
            self.log_info(f"Scanning for Bluetooth devices ({self.scan_duration}s)...")
            
            # Use hcitool to scan
            result = subprocess.run(
                ['hcitool', 'scan', '--flush'],
                capture_output=True,
                text=True,
                timeout=self.scan_duration + 5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                for line in lines:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        mac = parts[0].strip()
                        name = parts[1].strip() if len(parts) > 1 else 'Unknown'
                        devices.append({
                            'mac': mac,
                            'name': name,
                            'discovered_at': datetime.now().isoformat()
                        })
            
            # Also try bluetoothctl (modern approach)
            try:
                bt_devices = self._scan_with_bluetoothctl()
                for dev in bt_devices:
                    if not any(d['mac'] == dev['mac'] for d in devices):
                        devices.append(dev)
            except Exception as e:
                self.log_warning(f"bluetoothctl scan failed: {e}")
            
        except subprocess.TimeoutExpired:
            self.log_warning("Bluetooth scan timed out")
        except Exception as e:
            self.log_error(f"Bluetooth scan failed: {e}")
        
        return devices
    
    def _scan_with_bluetoothctl(self):
        """Scan using bluetoothctl (BlueZ 5)"""
        devices = []
        
        try:
            # Start scan
            subprocess.run(
                ['bluetoothctl', 'scan', 'on'],
                timeout=2,
                capture_output=True
            )
            
            # Wait for discovery
            time.sleep(self.scan_duration)
            
            # Stop scan and get devices
            subprocess.run(
                ['bluetoothctl', 'scan', 'off'],
                timeout=2,
                capture_output=True
            )
            
            # Get discovered devices
            result = subprocess.run(
                ['bluetoothctl', 'devices'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('Device'):
                        parts = line.split()
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = ' '.join(parts[2:])
                            devices.append({
                                'mac': mac,
                                'name': name,
                                'discovered_at': datetime.now().isoformat()
                            })
        
        except Exception as e:
            self.log_warning(f"bluetoothctl scan error: {e}")
        
        return devices
    
    def _get_device_info(self, mac):
        """
        Get detailed device information
        
        Args:
            mac: Device MAC address
        
        Returns:
            dict: Device information
        """
        info = {
            'class': None,
            'manufacturer': None,
            'device_type': 'Unknown',
            'rssi': None
        }
        
        try:
            # Get device info with hcitool
            result = subprocess.run(
                ['hcitool', 'info', mac],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Class:' in line:
                        class_str = line.split('Class:')[1].strip()
                        info['class'] = class_str
                        info['device_type'] = self._parse_device_class(class_str)
            
            # Get RSSI (signal strength)
            result = subprocess.run(
                ['hcitool', 'rssi', mac],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and 'RSSI' in result.stdout:
                rssi = result.stdout.split(':')[-1].strip()
                info['rssi'] = rssi
        
        except Exception as e:
            self.log_warning(f"Could not get device info for {mac}: {e}")
        
        return info
    
    def _parse_device_class(self, class_str):
        """Parse device class to human-readable type"""
        # Device class format: 0xXXXXXX
        # Reference: https://www.bluetooth.com/specifications/assigned-numbers/baseband/
        
        if not class_str or not class_str.startswith('0x'):
            return 'Unknown'
        
        try:
            device_class = int(class_str, 16)
            major_class = (device_class >> 8) & 0x1F
            
            classes = {
                0x01: 'Computer',
                0x02: 'Phone',
                0x03: 'LAN/Network Access Point',
                0x04: 'Audio/Video',
                0x05: 'Peripheral (mouse, keyboard)',
                0x06: 'Imaging (printer, scanner)',
                0x07: 'Wearable',
                0x08: 'Toy',
                0x09: 'Health',
                0x1F: 'Uncategorized'
            }
            
            return classes.get(major_class, 'Unknown')
        
        except Exception:
            return 'Unknown'
    
    def _get_services(self, mac):
        """
        Get available services on device
        
        Args:
            mac: Device MAC address
        
        Returns:
            list: List of services
        """
        services = []
        
        try:
            result = subprocess.run(
                ['sdptool', 'browse', mac],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                current_service = {}
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    
                    if line.startswith('Service Name:'):
                        if current_service:
                            services.append(current_service)
                        current_service = {
                            'name': line.split(':', 1)[1].strip()
                        }
                    elif line.startswith('Service RecHandle:'):
                        current_service['handle'] = line.split(':', 1)[1].strip()
                    elif line.startswith('Protocol Descriptor List:'):
                        current_service['protocols'] = []
                    elif 'UUID' in line and current_service:
                        uuid = line.split('UUID:')[-1].strip() if 'UUID:' in line else line
                        if 'uuid' not in current_service:
                            current_service['uuid'] = uuid
                
                if current_service:
                    services.append(current_service)
        
        except subprocess.TimeoutExpired:
            self.log_warning(f"Service discovery timed out for {mac}")
        except Exception as e:
            self.log_warning(f"Could not get services for {mac}: {e}")
        
        return services
    
    def _check_vulnerabilities(self, device, scan_id):
        """
        Check device for vulnerabilities
        
        Args:
            device: Device information dict
            scan_id: Database scan ID
        
        Returns:
            list: List of vulnerabilities found
        """
        vulnerabilities = []
        mac = device.get('mac')
        name = device.get('name', 'Unknown')
        
        # Check 1: Device discoverable (information disclosure)
        vulnerabilities.append({
            'type': 'Bluetooth Device Discoverable',
            'severity': 'low',
            'description': f"Device '{name}' is discoverable and broadcasting information"
        })
        
        self.db.add_vulnerability(
            scan_id=scan_id,
            host=mac,
            port=0,
            service='bluetooth',
            vuln_type='Information Disclosure',
            severity='low',
            description=f"Bluetooth device '{name}' ({mac}) is discoverable",
            plugin_name=self.name
        )
        
        # Check 2: Check for open services
        services = device.get('services', [])
        for service in services:
            service_name = service.get('name', 'Unknown Service')
            
            # Check for potentially insecure services
            insecure_services = [
                'OBEX Object Push',  # File transfer
                'OBEX File Transfer',
                'Serial Port',
                'Dial-up Networking'
            ]
            
            if any(insecure in service_name for insecure in insecure_services):
                vulnerabilities.append({
                    'type': f'Insecure Bluetooth Service: {service_name}',
                    'severity': 'medium',
                    'description': f"Device exposes potentially insecure service: {service_name}"
                })
                
                self.db.add_vulnerability(
                    scan_id=scan_id,
                    host=mac,
                    port=0,
                    service=service_name,
                    vuln_type='Insecure Bluetooth Service',
                    severity='medium',
                    description=f"Device '{name}' ({mac}) exposes: {service_name}",
                    plugin_name=self.name
                )
        
        # Check 3: Device type specific checks
        device_type = device.get('device_type', 'Unknown')
        
        if device_type == 'Peripheral (mouse, keyboard)':
            # Keyboard/mouse can be vulnerable to keystroke injection
            vulnerabilities.append({
                'type': 'Bluetooth Input Device',
                'severity': 'medium',
                'description': 'Bluetooth keyboard/mouse may be vulnerable to keystroke injection attacks'
            })
            
            self.db.add_vulnerability(
                scan_id=scan_id,
                host=mac,
                port=0,
                service='bluetooth',
                vuln_type='Bluetooth Injection Risk',
                severity='medium',
                description=f"Bluetooth input device '{name}' may be vulnerable to injection attacks",
                plugin_name=self.name
            )
        
        # Check 4: Signal strength (proximity)
        rssi = device.get('rssi')
        if rssi:
            try:
                rssi_val = int(rssi)
                if rssi_val > -50:
                    # Very close device
                    self.log_info(f"Device {name} is very close (RSSI: {rssi})")
            except ValueError:
                pass
        
        return vulnerabilities

def get_plugin():
    """Plugin entry point"""
    return BluetoothScanner
