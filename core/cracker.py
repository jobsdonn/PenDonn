"""
PenDonn Password Cracking Module
Handles password cracking using aircrack-ng, John the Ripper, and Hashcat.

Accepts both legacy `.cap` files (airodump-era) and modern `.pcapng` files
(hcxdumptool-era). The capture path is now hcxdumptool-only, so all new
captures are .pcapng — but we keep .cap support for any operator-provided
or pre-existing files.
"""

import os
import re
import time
import subprocess
import threading
import queue
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


def _hashfile_for(capture_file: str) -> str:
    """Return the hashcat-22000 path for a given capture file.

    Handles both .cap and .pcapng inputs by replacing the trailing
    extension. The previous `capture_file.replace('.cap', '.22000')`
    would silently no-op on .pcapng inputs, leaving cracker stuck in a
    loop trying to convert a file it had already named wrong.
    """
    return re.sub(r"\.(cap|pcapng|pcap)$", ".22000", capture_file)


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

        # Any handshake left in 'cracking' status at startup means the previous
        # run crashed mid-crack — reset to 'pending' so we retry.
        try:
            for h in self.db.get_all_handshakes(status='cracking'):
                self.db.update_handshake_status(h['id'], 'pending')
                logger.info(f"Reset orphaned 'cracking' handshake {h['id']} to pending")
        except Exception as e:
            logger.warning(f"Could not reset orphaned handshakes: {e}")

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
                logger.debug(f"Password already cracked for {ssid} ({bssid}) - skipping handshake {handshake_id}")
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
                
                # Update status (use .get to guard stop() race clearing active_cracks)
                self.db.update_handshake_status(handshake_id, 'cracking')
                if handshake_id in self.active_cracks:
                    self.active_cracks[handshake_id]['status'] = 'cracking'
                    self.active_cracks[handshake_id]['start_time'] = time.time()
                if not self.running:
                    self.crack_queue.task_done()
                    break
                
                # Try each enabled cracking engine
                cracked = False
                for engine in self.engines:
                    logger.info(f"Attempting to crack with engine: {engine}")
                    if engine == 'cowpatty':
                        result = self._crack_with_cowpatty(handshake)
                    elif engine == 'john':
                        result = self._crack_with_john(handshake)
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
                
                # Remove from active cracks (pop guards against race with stop())
                self.active_cracks.pop(handshake_id, None)

                self.crack_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
                time.sleep(1)
    
    def _crack_with_cowpatty(self, handshake: Dict) -> Optional[tuple]:
        """Crack WPA2 handshake using cowpatty.

        cowpatty reads .pcapng/.cap natively, computes PBKDF2-SHA1 in C, and
        requires no GPU/OpenCL. Reliable on ARM (Raspberry Pi 4) where the
        PoCL-based hashcat crashes during kernel self-test.

        Speed on Pi 4: ~140 H/s — sufficient for targeted wordlists; rockyou.txt
        takes ~29 h. For offline cracking against large wordlists, export the
        .22000 hash to a GPU host instead.
        """
        try:
            capture_file = handshake['file_path']
            ssid = handshake['ssid']

            if not os.path.exists(capture_file):
                logger.error(f"cowpatty: capture file not found: {capture_file}")
                return None

            # cowpatty must have a wordlist
            if not os.path.exists(self.wordlist):
                logger.warning(f"cowpatty: wordlist not found: {self.wordlist}")
                return None

            logger.info(f"cowpatty: cracking {ssid} with {self.wordlist}")
            start_time = time.time()

            cmd = [
                'cowpatty',
                '-f', self.wordlist,
                '-r', capture_file,
                '-s', ssid,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200,  # 2-hour cap
            )
            crack_time = time.time() - start_time

            if result.returncode not in (0, 1):
                logger.warning(f"cowpatty: unexpected exit code {result.returncode}: {result.stderr[:200]}")
                return None

            # cowpatty success: "The PSK is \"<password>\"."
            for line in result.stdout.splitlines():
                if line.startswith('The PSK is "'):
                    password = line[len('The PSK is "'):-2]  # strip trailing "."
                    logger.info(f"cowpatty: found password: {password}")
                    return (password, crack_time)

            logger.debug(f"cowpatty: exhausted wordlist for {ssid}")
            return None

        except FileNotFoundError:
            logger.warning("cowpatty not installed — skipping. Install: sudo apt install cowpatty")
            return None
        except subprocess.TimeoutExpired:
            logger.warning(f"cowpatty: timeout for {handshake['ssid']}")
            return None
        except Exception as e:
            logger.error(f"cowpatty error: {e}", exc_info=True)
            return None

    def _crack_with_john(self, handshake: Dict) -> Optional[tuple]:
        """Crack password using John the Ripper.

        John uses `wpapcap2john` to convert capture → john format. On
        most john-jumbo builds wpapcap2john only handles classic .cap;
        skip .pcapng inputs and let aircrack-ng/hashcat handle those.
        """
        try:
            handshake_id = handshake['id']
            capture_file = handshake['file_path']

            # Skip john for pcapng — wpapcap2john doesn't read it.
            if capture_file.lower().endswith(('.pcapng', '.pcap')):
                logger.debug(f"Skipping john for {capture_file} — wpapcap2john requires .cap")
                return None

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
            # Use wpapcap2john (part of john) to convert cap to john format
            john_hash_file = capture_file.replace('.cap', '.john')
            
            # Convert using wpapcap2john (comes with john)
            if not os.path.exists(john_hash_file):
                try:
                    # Try wpapcap2john first (standard with john)
                    result = subprocess.run(
                        ['wpapcap2john', capture_file],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        # Save John hash to file
                        with open(john_hash_file, 'w') as f:
                            f.write(result.stdout)
                        logger.info(f"Successfully converted to John format using wpapcap2john: {john_hash_file}")
                    else:
                        logger.warning(f"wpapcap2john failed for {handshake_id}, trying aircrack-ng")
                        # Fallback: use aircrack-ng to extract EAPOL
                        return None
                            
                except FileNotFoundError:
                    logger.error("wpapcap2john not found. Install john with: sudo apt install john")
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

            # aircrack-ng on this Pi (1.7) cannot read hcxdumptool's pcapng
            # directly (link-type IEEE802_11_RADIO). Convert to legacy pcap
            # via tcpdump first; tcpdump handles the radiotap encapsulation.
            crack_input = capture_file
            converted_cap = None
            if capture_file.lower().endswith(('.pcapng', '.pcap')):
                converted_cap = re.sub(r"\.(pcapng|pcap)$", "_aircrack.cap", capture_file)
                try:
                    conv = subprocess.run(
                        ['tcpdump', '-r', capture_file, '-w', converted_cap],
                        capture_output=True, text=True, timeout=30,
                    )
                    if conv.returncode == 0 and os.path.exists(converted_cap):
                        crack_input = converted_cap
                        logger.info(f"Converted {os.path.basename(capture_file)} → .cap for aircrack-ng")
                    else:
                        logger.warning(f"tcpdump conversion failed: {conv.stderr.strip()[:200]} — trying pcapng directly")
                        converted_cap = None
                except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"tcpdump not available: {e} — trying pcapng directly")
                    converted_cap = None

            # Run aircrack-ng
            start_time = time.time()

            from .secure_io import secure_temp_config
            cracked_out = secure_temp_config(f"cracked_{handshake_id}", suffix=".txt")

            cmd = [
                'aircrack-ng',
                crack_input,
                '-w', self.wordlist,
                '-b', bssid,  # Specify BSSID to avoid interactive prompt
                '-l', cracked_out,  # Output file for password (0600 in secure dir)
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

            if stdout:
                logger.info(f"aircrack-ng stdout: {stdout[:1000]}")
            if stderr:
                logger.info(f"aircrack-ng stderr: {stderr[:1000]}")
            logger.info(f"aircrack-ng exit code: {process.returncode}")

            # Clean up converted pcap if we made one.
            if converted_cap and os.path.exists(converted_cap):
                try:
                    os.remove(converted_cap)
                except OSError:
                    pass

            # Check the -l output file (cracked_out) first.
            if os.path.exists(cracked_out):
                with open(cracked_out, 'r') as f:
                    password = f.read().strip()
                if password:
                    logger.info(f"aircrack-ng found password: {password}")
                    try:
                        os.remove(cracked_out)
                    except OSError:
                        pass
                    return (password, crack_time)

            # Fallback: parse "KEY FOUND! [ password ]" from stdout.
            if 'KEY FOUND!' in stdout:
                for line in stdout.split('\n'):
                    if 'KEY FOUND!' in line and '[' in line and ']' in line:
                        password = line[line.index('[') + 1:line.index(']')].strip()
                        if password:
                            logger.info(f"aircrack-ng found password in stdout: {password}")
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
