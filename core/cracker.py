"""
PenDonn Password Cracking Module
Handles password cracking using John the Ripper and Hashcat
"""

import os
import time
import subprocess
import threading
import queue
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class PasswordCracker:
    """Password cracking with John the Ripper and Hashcat"""
    
    def __init__(self, config: Dict, database):
        """Initialize password cracker"""
        self.config = config
        self.db = database
        
        self.enabled = config['cracking']['enabled']
        self.engines = config['cracking']['engines']
        self.wordlist = config['cracking']['wordlist_path']
        self.auto_start = config['cracking']['auto_start_cracking']
        self.max_concurrent = config['cracking']['max_concurrent_cracks']
        
        self.john_format = config['cracking']['john_format']
        self.hashcat_mode = config['cracking']['hashcat_mode']
        
        self.running = False
        self.crack_queue = queue.Queue()
        self.active_cracks = {}  # handshake_id -> crack_info
        
        logger.info("Password Cracker initialized")
    
    def start(self):
        """Start password cracking service"""
        if not self.enabled:
            logger.info("Password cracking is disabled")
            return
        
        logger.info("Starting password cracking service...")
        self.running = True
        
        # Start worker threads
        for i in range(self.max_concurrent):
            worker = threading.Thread(target=self._crack_worker, args=(i,), daemon=True)
            worker.start()
        
        # Start queue monitor
        monitor = threading.Thread(target=self._queue_monitor, daemon=True)
        monitor.start()
        
        logger.info("Password cracking service started")
    
    def stop(self):
        """Stop password cracking service"""
        logger.info("Stopping password cracking service...")
        self.running = False
        
        # Stop active cracks
        for handshake_id, crack_info in list(self.active_cracks.items()):
            if crack_info.get('process'):
                try:
                    crack_info['process'].terminate()
                    crack_info['process'].wait(timeout=5)
                except:
                    pass
        
        self.active_cracks.clear()
        logger.info("Password cracking service stopped")
    
    def _queue_monitor(self):
        """Monitor database for new handshakes to crack"""
        while self.running:
            try:
                if self.auto_start:
                    # Get pending handshakes from database
                    pending = self.db.get_pending_handshakes()
                    
                    for handshake in pending:
                        handshake_id = handshake['id']
                        
                        # Check if already in queue or being cracked
                        if handshake_id not in self.active_cracks:
                            self.queue_handshake(handshake)
                
                time.sleep(10)
            
            except Exception as e:
                logger.error(f"Queue monitor error: {e}")
                time.sleep(5)
    
    def queue_handshake(self, handshake: Dict):
        """Add handshake to cracking queue"""
        try:
            handshake_id = handshake['id']
            
            if handshake_id not in self.active_cracks:
                self.crack_queue.put(handshake)
                self.active_cracks[handshake_id] = {
                    'status': 'queued',
                    'engine': None,
                    'start_time': None
                }
                logger.info(f"Queued handshake {handshake_id} for cracking")
        
        except Exception as e:
            logger.error(f"Error queueing handshake: {e}")
    
    def _crack_worker(self, worker_id: int):
        """Worker thread for cracking passwords"""
        logger.info(f"Crack worker {worker_id} started")
        
        while self.running:
            try:
                # Get handshake from queue
                handshake = self.crack_queue.get(timeout=5)
                handshake_id = handshake['id']
                
                logger.info(f"Worker {worker_id} processing handshake {handshake_id}")
                
                # Update status
                self.db.update_handshake_status(handshake_id, 'cracking')
                self.active_cracks[handshake_id]['status'] = 'cracking'
                self.active_cracks[handshake_id]['start_time'] = time.time()
                
                # Try each enabled cracking engine
                cracked = False
                for engine in self.engines:
                    if engine == 'john':
                        result = self._crack_with_john(handshake)
                    elif engine == 'hashcat':
                        result = self._crack_with_hashcat(handshake)
                    else:
                        continue
                    
                    if result:
                        cracked = True
                        password, crack_time = result
                        
                        # Store cracked password
                        self.db.add_cracked_password(
                            handshake_id=handshake_id,
                            ssid=handshake['ssid'],
                            bssid=handshake['bssid'],
                            password=password,
                            engine=engine,
                            crack_time=int(crack_time)
                        )
                        
                        logger.info(f"Password cracked for {handshake['ssid']}: {password}")
                        break
                
                # Update status
                if cracked:
                    self.db.update_handshake_status(handshake_id, 'cracked')
                else:
                    self.db.update_handshake_status(handshake_id, 'failed')
                    logger.warning(f"Failed to crack handshake {handshake_id}")
                
                # Remove from active cracks
                del self.active_cracks[handshake_id]
                
                self.crack_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                time.sleep(1)
    
    def _crack_with_john(self, handshake: Dict) -> Optional[tuple]:
        """Crack password using John the Ripper"""
        try:
            handshake_id = handshake['id']
            capture_file = handshake['file_path']
            
            logger.info(f"Cracking with John the Ripper: {handshake['ssid']}")
            
            # Convert to John format if needed
            john_file = capture_file.replace('.cap', '.john')
            
            # Convert using hccap2john or aircrack2john
            if not os.path.exists(john_file):
                # Try to convert
                subprocess.run(
                    ['aircrack-ng', '-J', john_file.replace('.john', ''), capture_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30
                )
                john_file = john_file.replace('.john', '.hccap.john')
            
            if not os.path.exists(john_file):
                logger.warning(f"Could not create John format file for {handshake_id}")
                return None
            
            # Run John the Ripper
            start_time = time.time()
            
            cmd = [
                'john',
                '--wordlist=' + self.wordlist,
                '--format=' + self.john_format,
                john_file
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.active_cracks[handshake_id]['process'] = process
            
            # Wait for completion (with timeout)
            stdout, stderr = process.communicate(timeout=3600)  # 1 hour timeout
            
            crack_time = time.time() - start_time
            
            # Check if password was found
            show_cmd = ['john', '--show', '--format=' + self.john_format, john_file]
            result = subprocess.run(show_cmd, capture_output=True, text=True)
            
            if result.stdout:
                # Parse password from output
                for line in result.stdout.split('\n'):
                    if ':' in line and 'password' not in line.lower():
                        parts = line.split(':')
                        if len(parts) >= 2:
                            password = parts[-1].strip()
                            if password:
                                return (password, crack_time)
            
            return None
        
        except subprocess.TimeoutExpired:
            logger.warning(f"John the Ripper timeout for {handshake['ssid']}")
            if 'process' in self.active_cracks.get(handshake_id, {}):
                self.active_cracks[handshake_id]['process'].kill()
            return None
        except Exception as e:
            logger.error(f"John the Ripper error: {e}")
            return None
    
    def _crack_with_hashcat(self, handshake: Dict) -> Optional[tuple]:
        """Crack password using Hashcat"""
        try:
            handshake_id = handshake['id']
            capture_file = handshake['file_path']
            
            logger.info(f"Cracking with Hashcat: {handshake['ssid']}")
            
            # Convert to hashcat format (hc22000)
            hc_file = capture_file.replace('.cap', '.hc22000')
            
            if not os.path.exists(hc_file):
                # Convert using hcxpcapngtool
                result = subprocess.run(
                    ['hcxpcapngtool', '-o', hc_file, capture_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30
                )
                
                if not os.path.exists(hc_file):
                    logger.warning(f"Could not create Hashcat format file for {handshake_id}")
                    return None
            
            # Output file for cracked passwords
            output_file = hc_file + '.cracked'
            
            # Run Hashcat
            start_time = time.time()
            
            cmd = [
                'hashcat',
                '-m', str(self.hashcat_mode),
                '-a', '0',  # Dictionary attack
                hc_file,
                self.wordlist,
                '-o', output_file,
                '--force',  # Force if no GPU
                '--quiet'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.active_cracks[handshake_id]['process'] = process
            
            # Wait for completion
            stdout, stderr = process.communicate(timeout=3600)  # 1 hour timeout
            
            crack_time = time.time() - start_time
            
            # Check if password was found
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        # Parse hashcat output format
                        # Format: hash:password or hash:hex:password
                        parts = content.split(':')
                        if len(parts) >= 2:
                            password = parts[-1].strip()
                            if password:
                                return (password, crack_time)
            
            return None
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Hashcat timeout for {handshake['ssid']}")
            if 'process' in self.active_cracks.get(handshake_id, {}):
                self.active_cracks[handshake_id]['process'].kill()
            return None
        except Exception as e:
            logger.error(f"Hashcat error: {e}")
            return None
    
    def get_status(self) -> Dict:
        """Get cracker status"""
        return {
            'running': self.running,
            'queue_size': self.crack_queue.qsize(),
            'active_cracks': len(self.active_cracks),
            'engines_enabled': self.engines
        }
    
    def get_active_cracks(self) -> List[Dict]:
        """Get list of active cracking jobs"""
        return [
            {
                'handshake_id': hid,
                'status': info['status'],
                'engine': info.get('engine'),
                'elapsed_time': int(time.time() - info['start_time']) if info['start_time'] else 0
            }
            for hid, info in self.active_cracks.items()
        ]
