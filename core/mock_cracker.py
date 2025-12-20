"""
PenDonn Mock Password Cracker Module
Simulates password cracking for testing/development
"""

import os
import time
import threading
import logging
import random
from datetime import datetime
from typing import Dict, List, Optional
from queue import Queue, Empty

logger = logging.getLogger(__name__)


class MockPasswordCracker:
    """Mock password cracking for development/testing"""
    
    def __init__(self, config: Dict, database):
        """Initialize mock password cracker"""
        self.config = config
        self.db = database
        
        self.enabled = config['cracking']['enabled']
        self.auto_start = config['cracking']['auto_start_cracking']
        self.max_concurrent = config['cracking']['max_concurrent_cracks']
        
        self.running = False
        self.crack_queue = Queue()
        self.workers = []
        
        # Mock passwords - realistic common passwords from rockyou.txt style wordlists
        # These represent real-world weak passwords that would be crackable
        self.mock_passwords = {
            # By SSID pattern - makes testing predictable and realistic
            "NETGEAR42": "password123",
            "TP-Link_5F3A": "admin123",
            "Linksys00234": "welcome1",
            "ASUS_Guest": "guest2024",
            "MyHome2024": "mypassword",
            "Starbucks WiFi": "starbucks",
            "CoffeeShop_Guest": "coffee123",
            "Office_Corp": "Company2024",
            "CompanyGuest": "guest123",
            "SmartHome": "12345678",
            "WiFi-2.4G": "qwerty123",
            "Hidden_EE:12": "letmein",
            
            # Default fallback for any network
            "default": "password"
        }
        
        logger.info("Mock Password Cracker initialized (DEBUG MODE)")
    
    def start(self):
        """Start mock password cracking service"""
        if not self.enabled:
            logger.info("Password cracking is disabled")
            return
        
        logger.info("Starting mock password cracking service...")
        self.running = True
        
        # Start worker threads
        for i in range(self.max_concurrent):
            worker = threading.Thread(target=self._crack_worker, args=(i,), daemon=True)
            worker.start()
            self.workers.append(worker)
        
        # Start queue monitor
        if self.auto_start:
            monitor = threading.Thread(target=self._queue_monitor, daemon=True)
            monitor.start()
        
        logger.info(f"Mock password cracking started with {self.max_concurrent} workers")
    
    def stop(self):
        """Stop mock password cracking"""
        logger.info("Stopping mock password cracker...")
        self.running = False
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=2)
        
        logger.info("Mock password cracker stopped")
    
    def _queue_monitor(self):
        """Monitor database for pending handshakes"""
        logger.info("Mock queue monitor started")
        
        while self.running:
            try:
                # Check for pending handshakes
                pending = self.db.get_pending_handshakes()
                
                for handshake in pending:
                    if not self.running:
                        break
                    
                    # Add to queue if not already queued
                    self.queue_handshake(handshake)
                
                time.sleep(10)  # Check every 10 seconds
            
            except Exception as e:
                logger.error(f"Mock queue monitor error: {e}")
                time.sleep(30)
    
    def queue_handshake(self, handshake: Dict):
        """Add handshake to cracking queue"""
        logger.info(f"Mock: Queuing handshake for {handshake['ssid']} (BSSID: {handshake['bssid']})")
        self.crack_queue.put(handshake)
    
    def _crack_worker(self, worker_id: int):
        """Worker thread for mock password cracking - simulates John/Hashcat behavior"""
        logger.info(f"Mock crack worker {worker_id} started (simulating John the Ripper + Hashcat)")
        
        while self.running:
            try:
                # Get handshake from queue
                handshake = self.crack_queue.get(timeout=1)
                
                logger.info(f"Mock Worker {worker_id}: Starting crack for {handshake['ssid']} (BSSID: {handshake['bssid']})")
                logger.info(f"Mock Worker {worker_id}: Using handshake file: {handshake['file_path']}")
                
                # Simulate file readiness check (like real cracker)
                time.sleep(1)  # Wait for file to be ready
                
                # Simulate realistic cracking time based on tool
                # John the Ripper: 10-20s for simple passwords
                # Hashcat: 5-15s for simple passwords
                use_john = random.choice([True, False])
                tool_name = "John the Ripper" if use_john else "Hashcat"
                
                if use_john:
                    crack_time = random.uniform(10, 20)
                    logger.info(f"Mock Worker {worker_id}: Using John the Ripper (hcx2john + --format=wpapsk)")
                else:
                    crack_time = random.uniform(5, 15)
                    logger.info(f"Mock Worker {worker_id}: Using Hashcat (-m 22000 -a 0)")
                
                # Apply debug timing
                if self.config['debug'].get('simulate_delays', True):
                    # Show realistic progress updates
                    for progress in [25, 50, 75]:
                        time.sleep(crack_time / 4)
                        logger.debug(f"Mock Worker {worker_id}: Cracking progress ~{progress}% ({tool_name})")
                else:
                    time.sleep(2)  # Quick mode for testing
                
                # Determine password based on SSID (realistic mapping)
                password = self.mock_passwords.get(handshake['ssid'], self.mock_passwords['default'])
                
                # High success rate (85%) since we're using known weak passwords
                if random.random() < 0.85:
                    # Save cracked password
                    self.db.add_cracked_password(
                        handshake_id=handshake['id'],
                        ssid=handshake['ssid'],
                        bssid=handshake['bssid'],
                        password=password,
                        engine=tool_name,
                        crack_time=int(crack_time)
                    )
                    
                    logger.info(f"Mock Worker {worker_id}: ✓ SUCCESS - Cracked {handshake['ssid']}")
                    logger.info(f"Mock Worker {worker_id}: Password: '{password}' (found with {tool_name} in {int(crack_time)}s)")
                else:
                    # Failed - password not in wordlist or file issue
                    logger.warning(f"Mock Worker {worker_id}: ✗ FAILED - Could not crack {handshake['ssid']}")
                    logger.warning(f"Mock Worker {worker_id}: Password not found in wordlist after {int(crack_time)}s")
                
                self.crack_queue.task_done()
            
            except Empty:
                # Queue is empty, this is normal - just wait for more work
                pass
            except Exception as e:
                logger.error(f"Mock worker {worker_id} error: {e}", exc_info=True)
        
        logger.info(f"Mock crack worker {worker_id} stopped")
    
    def get_statistics(self) -> Dict:
        """Get mock cracking statistics"""
        return {
            'queue_size': self.crack_queue.qsize(),
            'running': self.running,
            'workers': len(self.workers)
        }
