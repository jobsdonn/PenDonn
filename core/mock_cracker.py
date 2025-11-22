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
        
        # Mock passwords that will "crack"
        self.mock_passwords = [
            "password123",
            "admin123",
            "welcome1",
            "qwerty123",
            "letmein",
            "password",
            "123456789",
            "admin"
        ]
        
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
        """Worker thread for mock password cracking"""
        logger.info(f"Mock crack worker {worker_id} started")
        
        while self.running:
            try:
                # Get handshake from queue
                handshake = self.crack_queue.get(timeout=1)
                
                logger.info(f"Mock Worker {worker_id}: Starting crack for {handshake['ssid']}")
                
                # Simulate cracking time (10-30 seconds)
                crack_time = random.uniform(10, 30)
                if self.config['debug'].get('simulate_delays', True):
                    time.sleep(crack_time)
                else:
                    time.sleep(2)  # Quick mode
                
                # Simulate success rate (70%)
                if random.random() < 0.7:
                    password = random.choice(self.mock_passwords)
                    
                    # Save cracked password
                    self.db.add_cracked_password(
                        handshake_id=handshake['id'],
                        ssid=handshake['ssid'],
                        bssid=handshake['bssid'],
                        password=password,
                        crack_time=int(crack_time)
                    )
                    
                    logger.info(f"Mock Worker {worker_id}: ✓ Cracked {handshake['ssid']} - "
                               f"Password: {password} (took {int(crack_time)}s)")
                else:
                    logger.info(f"Mock Worker {worker_id}: ✗ Failed to crack {handshake['ssid']}")
                
                self.crack_queue.task_done()
            
            except Empty:
                # Queue is empty, this is normal - just wait for more work
                pass
            except Exception as e:
                logger.error(f"Mock worker {worker_id} error: {e}")
        
        logger.info(f"Mock crack worker {worker_id} stopped")
    
    def get_statistics(self) -> Dict:
        """Get mock cracking statistics"""
        return {
            'queue_size': self.crack_queue.qsize(),
            'running': self.running,
            'workers': len(self.workers)
        }
