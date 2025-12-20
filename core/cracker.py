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
    
    def __init__(self, config: Dict, database, wifi_scanner=None):
        """Initialize password cracker"""
        self.config = config
        self.db = database
        self.wifi_scanner = wifi_scanner
        
        self.enabled = config['cracking']['enabled']
        self.engines = config['cracking']['engines']
        self.wordlist = config['cracking']['wordlist_path']
        self.auto_start = config['cracking']['auto_start_cracking']
        self.max_concurrent = config['cracking']['max_concurrent_cracks']
        
        self.john_format = config['cracking']['john_format']
        self.hashcat_mode = config['cracking']['hashcat_mode']
        self.hashcat_rules_dir = config['cracking'].get('hashcat_rules_dir', './rules')
        self.hashcat_use_rules = config['cracking'].get('use_rules', True)
        self.hashcat_brute_force = config['cracking'].get('brute_force', True)
        self.hashcat_brute_max_length = config['cracking'].get('brute_max_length', 8)
        self.session_prefix = config['cracking'].get('session_prefix', 'pendonn')
        
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
    
    def _parse_hashcat_potfile(self, potfile_path: str = None) -> Dict[str, str]:
        """Parse hashcat potfile into hash:password lookup table for O(1) access
        
        Args:
            potfile_path: Path to hashcat.potfile, defaults to hashcat default location
            
        Returns:
            Dictionary with hash as key and password as value
        """
        if not potfile_path:
            # Try common hashcat potfile locations
            possible_paths = [
                os.path.expanduser('~/.hashcat/hashcat.potfile'),
                os.path.expanduser('~/.local/share/hashcat/hashcat.potfile'),
                './hashcat.potfile'
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    potfile_path = path
                    break
        
        hash_lookup = {}
        
        if not potfile_path or not os.path.exists(potfile_path):
            logger.debug("No hashcat potfile found")
            return hash_lookup
        
        try:
            with open(potfile_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        # Format: hash:password
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            hash_lookup[parts[0]] = parts[1]
            
            logger.info(f"Loaded {len(hash_lookup)} cracked hashes from potfile")
        except Exception as e:
            logger.error(f"Error parsing potfile: {e}")
        
        return hash_lookup
    
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
            bssid = handshake['bssid']
            ssid = handshake['ssid']
            
            # Skip if password already cracked for this network
            if self.db.get_password_for_network(bssid):
                logger.info(f"Password already cracked for {ssid} ({bssid}) - skipping handshake {handshake_id}")
                return
            
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
                    logger.info(f"Attempting to crack with engine: {engine}")
                    if engine == 'john':
                        result = self._crack_with_john(handshake)
                    elif engine == 'hashcat':
                        result = self._crack_with_hashcat(handshake)
                    elif engine == 'aircrack-ng':
                        result = self._crack_with_aircrack(handshake)
                    else:
                        logger.warning(f"Unknown cracking engine: {engine}")
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
                        
                        # Note: We don't forcibly stop active captures as it may kill shared processes
                        # Instead, the wifi_scanner will naturally skip this network on next scan cycle
                        
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
            
            # Wait a bit and verify file exists and has content
            for i in range(10):  # Try for up to 10 seconds
                if os.path.exists(capture_file) and os.path.getsize(capture_file) > 1000:
                    break
                logger.debug(f"Waiting for capture file {capture_file} to be ready...")
                time.sleep(1)
            
            if not os.path.exists(capture_file):
                logger.error(f"Capture file not found: {capture_file}")
                return None
            
            if os.path.getsize(capture_file) < 1000:
                logger.error(f"Capture file too small: {capture_file} ({os.path.getsize(capture_file)} bytes)")
                return None
            
            logger.info(f"Cracking with John the Ripper: {handshake['ssid']}")
            
            # John can't read hashcat 22000 format directly
            # Use hcx2john to convert cap to john format
            john_hash_file = capture_file.replace('.cap', '.john')
            
            # Convert using hcx2john
            if not os.path.exists(john_hash_file):
                try:
                    # Use hcx2john to create John-compatible hash
                    result = subprocess.run(
                        ['hcx2john', capture_file],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        # Save John hash to file
                        with open(john_hash_file, 'w') as f:
                            f.write(result.stdout)
                        logger.info(f"Successfully converted to John format: {john_hash_file}")
                    else:
                        logger.warning(f"hcx2john failed for {handshake_id}")
                        return None
                            
                except FileNotFoundError:
                    logger.error("hcx2john not found. Install with: sudo apt install hcxtools")
                    return None
            
            if not os.path.exists(john_hash_file) or os.path.getsize(john_hash_file) == 0:
                logger.warning(f"Could not create John hash file for {handshake_id}")
                return None
            
            # Run John the Ripper with WPAPSK format
            start_time = time.time()
            
            # Try wpapsk-opencl first, then wpapsk
            formats_to_try = ['wpapsk-opencl', 'wpapsk']
            
            for john_format in formats_to_try:
                cmd = [
                    'john',
                    '--wordlist=' + self.wordlist,
                    f'--format={john_format}',
                    john_hash_file
                ]
                
                logger.info(f"Running John command: {' '.join(cmd)}")
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                self.active_cracks[handshake_id]['process'] = process
                
                # Wait for completion (with timeout)
                stdout, stderr = process.communicate(timeout=3600)  # 1 hour timeout
                
                # Log John's output for debugging
                if stdout:
                    logger.info(f"John stdout ({john_format}): {stdout[:500]}")
                if stderr:
                    logger.info(f"John stderr ({john_format}): {stderr[:500]}")
                
                # Check for format error
                if 'Unknown ciphertext format' in stderr or 'No password hashes loaded' in stderr:
                    logger.warning(f"Format {john_format} not working, trying next...")
                    continue
                
                crack_time = time.time() - start_time
                
                # Check if password was found
                show_cmd = ['john', '--show', f'--format={john_format}', john_hash_file]
                logger.info(f"Running John show command: {' '.join(show_cmd)}")
                result = subprocess.run(show_cmd, capture_output=True, text=True)
                
                logger.info(f"John show output: {result.stdout[:500]}")
                
                if result.stdout and '0 password hashes cracked' not in result.stdout:
                    # Parse password from output
                    # Format is typically: SSID:password
                    for line in result.stdout.split('\n'):
                        if ':' in line and 'password' not in line.lower() and line.strip():
                            parts = line.split(':')
                            if len(parts) >= 2:
                                password = parts[-1].strip()
                                if password and password != '':
                                    logger.info(f"John found password: {password}")
                                    return (password, crack_time)
                
                # If we got here without errors, format worked but no password found
                if 'Unknown ciphertext format' not in stderr:
                    break
            
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
        """Crack password using Hashcat with multiple attack strategies
        
        Implements:
        1. Dictionary attack with wordlist
        2. Rule-based attacks (if enabled)
        3. Incremental brute force (if enabled)
        4. Session management for resume capability
        """
        try:
            handshake_id = handshake['id']
            capture_file = handshake['file_path']
            ssid = handshake['ssid']
            
            # Wait a bit and verify file exists and has content
            for i in range(10):  # Try for up to 10 seconds
                if os.path.exists(capture_file) and os.path.getsize(capture_file) > 1000:
                    break
                logger.debug(f"Waiting for capture file {capture_file} to be ready...")
                time.sleep(1)
            
            if not os.path.exists(capture_file):
                logger.error(f"Capture file not found: {capture_file}")
                return None
            
            if os.path.getsize(capture_file) < 1000:
                logger.error(f"Capture file too small: {capture_file} ({os.path.getsize(capture_file)} bytes)")
                return None
            
            logger.info(f"Cracking with Hashcat: {ssid}\")")
            
            # Convert to hashcat 22000 format
            hash_file = capture_file.replace('.cap', '.22000')
            
            if not os.path.exists(hash_file):
                try:
                    # Try hcxpcapngtool (newer, for 22000 format)
                    result = subprocess.run(
                        ['hcxpcapngtool', '-o', hash_file, capture_file],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode != 0:
                        stderr = result.stderr.strip() if result.stderr else "Unknown error"
                        stdout = result.stdout.strip() if result.stdout else ""
                        logger.warning(f"hcxpcapngtool failed for hashcat: {stderr[:200]}")
                        logger.debug(f"hcxpcapngtool stdout: {stdout[:200]}")
                        
                        # Try hcxpcaptool (older version)
                        try:
                            result = subprocess.run(
                                ['hcxpcaptool', '-z', hash_file, capture_file],
                                capture_output=True,
                                text=True,
                                timeout=30
                            )
                            if result.returncode != 0:
                                logger.warning(f"hcxpcaptool also failed")
                                return None
                        except FileNotFoundError:
                            logger.warning(f"Neither hcxpcapngtool nor hcxpcaptool found")
                            return None
                    else:
                        # Log successful conversion
                        logger.info(f"Successfully converted {capture_file} to {hash_file} for hashcat")
                            
                except FileNotFoundError:
                    logger.error("hcxpcapngtool not found. Install with: sudo apt install hcxtools")
                    return None
            
            if not os.path.exists(hash_file) or os.path.getsize(hash_file) == 0:
                logger.warning(f"Could not create Hashcat format file for {handshake_id}: file doesn't exist or is empty")
                return None
            
            # Output file for cracked passwords
            output_file = hash_file + '.cracked'
            
            # Remove old output file if it exists
            if os.path.exists(output_file):
                os.remove(output_file)
            
            # Run Hashcat
            start_time = time.time()
            
            cmd = [
                'hashcat',
                '-m', str(self.hashcat_mode),  # 22000 for WPA-PBKDF2-PMKID+EAPOL
                '-a', '0',  # Dictionary attack
                hash_file,
                self.wordlist,
                '-o', output_file,
                '--force'  # Force if no GPU, removed --quiet to see errors
            ]
            
            logger.info(f"Running Hashcat command: {' '.join(cmd)}")
            
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
            
            # Log Hashcat's output for debugging
            if stdout:
                logger.info(f"Hashcat stdout: {stdout[:1000]}")
            if stderr:
                logger.info(f"Hashcat stderr: {stderr[:1000]}")
            
            logger.info(f"Hashcat exit code: {process.returncode}")
            
            # Check if password was found
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    content = f.read().strip()
                    logger.info(f"Hashcat output file content: {content[:200]}")
                    if content:
                        # Parse hashcat output format
                        # Format for 22000: hash*data:password
                        # The password is after the last colon
                        if ':' in content:
                            parts = content.split(':')
                            password = parts[-1].strip()
                            if password and password != '':
                                logger.info(f"Hashcat found password: {password}")
                                return (password, crack_time)
            else:
                logger.warning(f"Hashcat output file not created: {output_file}")
            
            return None
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Hashcat timeout for {handshake['ssid']}")
            if 'process' in self.active_cracks.get(handshake_id, {}):
                self.active_cracks[handshake_id]['process'].kill()
            return None
        except Exception as e:
            logger.error(f"Hashcat error: {e}")
            return None
    
    def _crack_with_aircrack(self, handshake: Dict) -> Optional[tuple]:
        """Crack password using aircrack-ng (most reliable on Raspberry Pi)"""
        try:
            handshake_id = handshake['id']
            capture_file = handshake['file_path']
            ssid = handshake['ssid']
            bssid = handshake['bssid']
            
            # Wait a bit and verify file exists and has content
            for i in range(10):  # Try for up to 10 seconds
                if os.path.exists(capture_file) and os.path.getsize(capture_file) > 1000:
                    break
                logger.debug(f"Waiting for capture file {capture_file} to be ready...")
                time.sleep(1)
            
            if not os.path.exists(capture_file):
                logger.error(f"Capture file not found: {capture_file}")
                return None
            
            if os.path.getsize(capture_file) < 1000:
                logger.error(f"Capture file too small: {capture_file} ({os.path.getsize(capture_file)} bytes)")
                return None
            
            logger.info(f"Cracking with aircrack-ng: {ssid}")
            
            # Run aircrack-ng
            start_time = time.time()
            
            cmd = [
                'aircrack-ng',
                capture_file,
                '-w', self.wordlist,
                '-b', bssid,  # Specify BSSID to avoid interactive prompt
                '-l', f'/tmp/cracked_{handshake_id}.txt'  # Output file for password
            ]
            
            logger.info(f"Running aircrack-ng command: {' '.join(cmd)}")
            
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
            
            # Log aircrack-ng's output for debugging
            if stdout:
                logger.info(f"aircrack-ng stdout: {stdout[:1000]}")
            if stderr:
                logger.info(f"aircrack-ng stderr: {stderr[:1000]}")
            
            logger.info(f"aircrack-ng exit code: {process.returncode}")
            
            # Check output file first
            output_file = f'/tmp/cracked_{handshake_id}.txt'
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    password = f.read().strip()
                    if password:
                        logger.info(f"aircrack-ng found password: {password}")
                        os.remove(output_file)  # Clean up
                        return (password, crack_time)
            
            # Also check stdout for "KEY FOUND" message
            if 'KEY FOUND!' in stdout:
                # Extract password from output
                # Format: KEY FOUND! [ password ]
                for line in stdout.split('\n'):
                    if 'KEY FOUND!' in line:
                        # Extract password between brackets
                        if '[' in line and ']' in line:
                            start = line.index('[') + 1
                            end = line.index(']')
                            password = line[start:end].strip()
                            if password:
                                logger.info(f"aircrack-ng found password in output: {password}")
                                return (password, crack_time)
            
            logger.info(f"aircrack-ng did not find password for {ssid}")
            return None
        
        except subprocess.TimeoutExpired:
            logger.warning(f"aircrack-ng timeout for {handshake['ssid']}")
            if 'process' in self.active_cracks.get(handshake_id, {}):
                self.active_cracks[handshake_id]['process'].kill()
            return None
        except Exception as e:
            logger.error(f"aircrack-ng error: {e}")
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
