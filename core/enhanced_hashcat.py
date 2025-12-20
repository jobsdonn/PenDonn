"""
Enhanced Hashcat Methods - Optimized based on PowerShell techniques
Add these methods to the PasswordCracker class for advanced cracking strategies
"""

import os
import subprocess
import time
import logging
from typing import Optional, List, Dict, tuple

logger = logging.getLogger(__name__)


class HashcatEnhancements:
    """
    Enhanced hashcat cracking strategies inspired by PowerShell optimization techniques:
    
    1. Hash lookup tables for O(1) potfile parsing (vs O(n) filtering)
    2. Rule-based attacks with automatic rule file discovery
    3. Incremental brute force with configurable mask
    4. Session management for resume capability
    5. Multiple wordlist support
    """
    
    def parse_hashcat_potfile(self, potfile_path: str = None) -> Dict[str, str]:
        """Parse hashcat potfile into hash:password lookup table for O(1) access
        
        Inspired by PowerShell: $hashLookup = @{} with O(1) lookup
        
        Args:
            potfile_path: Path to hashcat.potfile
            
        Returns:
            Dictionary with hash as key and password as value
        """
        if not potfile_path:
            # Try common hashcat potfile locations
            possible_paths = [
                os.path.expanduser('~/.hashcat/hashcat.potfile'),
                os.path.expanduser('~/.local/share/hashcat/hashcat.potfile'),
                './hashcat.potfile',
                '/root/.hashcat/hashcat.potfile'
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
    
    def hashcat_rule_attacks(self, hash_file: str, wordlist: str, output_file: str, 
                            rules_dir: str = './rules', hashcat_mode: int = 22000,
                            session: str = 'pendonn') -> Optional[tuple]:
        """Perform rule-based attacks with all available rules
        
        Inspired by PowerShell loop through rules directory:
        foreach ($rule in $rules){ if($rule.FullName -like "*.rule"){...} }
        
        Args:
            hash_file: Hash file to crack
            wordlist: Wordlist path
            output_file: Output file for cracked passwords
            rules_dir: Directory containing .rule files
            hashcat_mode: Hashcat mode (22000 for WPA2)
            session: Session name for resume
            
        Returns:
            Tuple of (password, crack_time) if successful
        """
        try:
            # Get all rule files
            rule_files = []
            if os.path.isdir(rules_dir):
                for file in os.listdir(rules_dir):
                    if file.endswith('.rule'):
                        rule_files.append(os.path.join(rules_dir, file))
            
            if not rule_files:
                logger.warning(f"No rule files found in {rules_dir}")
                return None
            
            logger.info(f"Found {len(rule_files)} rule files to test")
            
            # Try each rule file (PowerShell-style loop)
            for rule_file in rule_files:
                rule_name = os.path.basename(rule_file)
                logger.info(f"Testing rule: {rule_name}")
                
                cmd = [
                    'hashcat',
                    '-m', str(hashcat_mode),
                    '-a', '0',  # Dictionary attack
                    hash_file,
                    wordlist,
                    '-r', rule_file,  # Apply rule
                    '-o', output_file,
                    '--session', f"{session}_{rule_name}",
                    '--force'
                ]
                
                result = self._run_hashcat(cmd, output_file)
                if result:
                    logger.info(f"✓ Password found with rule: {rule_name}")
                    return result
            
            return None
        except Exception as e:
            logger.error(f"Rule-based attack error: {e}")
            return None
    
    def hashcat_brute_force(self, hash_file: str, output_file: str, 
                           max_length: int = 8, hashcat_mode: int = 22000,
                           session: str = 'pendonn') -> Optional[tuple]:
        """Perform incremental brute force attack
        
        Inspired by PowerShell: ?a?a?a?a?a?a?a?a with --increment
        
        Args:
            hash_file: Hash file to crack
            output_file: Output file for cracked passwords
            max_length: Maximum password length (default 8)
            hashcat_mode: Hashcat mode (22000 for WPA2)
            session: Session name for resume
            
        Returns:
            Tuple of (password, crack_time) if successful
        """
        try:
            # Build mask: ?a = all characters
            mask = '?a' * max_length
            
            logger.info(f"Brute force: mask {mask} (up to {max_length} chars)")
            
            cmd = [
                'hashcat',
                '-m', str(hashcat_mode),
                '-a', '3',  # Brute force attack
                hash_file,
                mask,
                '-o', output_file,
                '--increment',  # Incremental mode
                '--increment-min', '1',
                '--increment-max', str(max_length),
                '--session', f"{session}_brute",
                '--force',
                '-O'  # Optimized kernel
            ]
            
            return self._run_hashcat(cmd, output_file, timeout=7200)  # 2 hour timeout
        except Exception as e:
            logger.error(f"Brute force attack error: {e}")
            return None
    
    def hashcat_multi_wordlist(self, hash_file: str, wordlists: List[str], 
                              output_file: str, hashcat_mode: int = 22000,
                              session: str = 'pendonn') -> Optional[tuple]:
        """Try multiple wordlists sequentially
        
        Inspired by PowerShell: multiple wordlist files in baseString
        
        Args:
            hash_file: Hash file to crack
            wordlists: List of wordlist paths
            output_file: Output file for cracked passwords
            hashcat_mode: Hashcat mode (22000 for WPA2)
            session: Session name for resume
            
        Returns:
            Tuple of (password, crack_time) if successful
        """
        try:
            for wordlist in wordlists:
                if not os.path.exists(wordlist):
                    logger.warning(f"Wordlist not found: {wordlist}")
                    continue
                
                wordlist_name = os.path.basename(wordlist)
                logger.info(f"Trying wordlist: {wordlist_name}")
                
                cmd = [
                    'hashcat',
                    '-m', str(hashcat_mode),
                    '-a', '0',  # Dictionary attack
                    hash_file,
                    wordlist,
                    '-o', output_file,
                    '--session', f"{session}_{wordlist_name}",
                    '--force'
                ]
                
                result = self._run_hashcat(cmd, output_file)
                if result:
                    logger.info(f"✓ Password found with wordlist: {wordlist_name}")
                    return result
            
            return None
        except Exception as e:
            logger.error(f"Multi-wordlist attack error: {e}")
            return None
    
    def hashcat_session_restore(self, session: str) -> bool:
        """Restore a previous hashcat session
        
        Inspired by PowerShell: --session $project --restore
        
        Args:
            session: Session name to restore
            
        Returns:
            True if session restored successfully
        """
        try:
            cmd = [
                'hashcat',
                '--session', session,
                '--restore'
            ]
            
            logger.info(f"Restoring session: {session}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=3600)
            
            if process.returncode == 0:
                logger.info(f"✓ Session {session} restored successfully")
                return True
            else:
                logger.warning(f"Session restore failed: {stderr[:200]}")
                return False
        
        except Exception as e:
            logger.error(f"Session restore error: {e}")
            return False
    
    def extract_cracked_passwords(self, potfile_path: str = None) -> List[str]:
        """Extract all cracked passwords from potfile
        
        Inspired by PowerShell: foreach($line in $fileContent){ $password = $line.Substring(33); $passwords += $password }
        
        Args:
            potfile_path: Path to hashcat.potfile
            
        Returns:
            List of cracked passwords
        """
        hash_lookup = self.parse_hashcat_potfile(potfile_path)
        passwords = list(hash_lookup.values())
        
        logger.info(f"Extracted {len(passwords)} passwords from potfile")
        return passwords
    
    def analyze_password_patterns(self, passwords: List[str]) -> Dict:
        """Analyze password patterns for insights
        
        Inspired by PowerShell: $moredata | group Password | sort Count -Descending
        
        Args:
            passwords: List of cracked passwords
            
        Returns:
            Dictionary with password statistics
        """
        if not passwords:
            return {}
        
        # Count password occurrences
        from collections import Counter
        password_counts = Counter(passwords)
        
        # Get top 10 most common
        top_10 = password_counts.most_common(10)
        
        # Calculate statistics
        stats = {
            'total_passwords': len(passwords),
            'unique_passwords': len(password_counts),
            'top_10_passwords': [
                {'password': pwd, 'count': count} 
                for pwd, count in top_10
            ],
            'avg_length': sum(len(p) for p in passwords) / len(passwords),
            'min_length': min(len(p) for p in passwords),
            'max_length': max(len(p) for p in passwords)
        }
        
        logger.info(f"Password analysis: {stats['unique_passwords']} unique out of {stats['total_passwords']} total")
        return stats
    
    def _run_hashcat(self, cmd: List[str], output_file: str, timeout: int = 3600) -> Optional[tuple]:
        """Run hashcat command and parse results
        
        Args:
            cmd: Hashcat command as list
            output_file: Output file path
            timeout: Timeout in seconds
            
        Returns:
            Tuple of (password, crack_time) if successful
        """
        try:
            logger.info(f"Running: {' '.join(cmd[:6])}...")
            
            start_time = time.time()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for completion
            stdout, stderr = process.communicate(timeout=timeout)
            
            crack_time = time.time() - start_time
            
            # Check if password was found
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().strip()
                    if content and ':' in content:
                        # Parse: hash*data:password
                        password = content.split(':')[-1].strip()
                        if password:
                            return (password, crack_time)
            
            return None
        
        except subprocess.TimeoutExpired:
            logger.warning(f"Hashcat command timeout after {timeout}s")
            process.kill()
            return None
        except Exception as e:
            logger.error(f"Hashcat execution error: {e}")
            return None


# Example usage:
"""
# In your cracker.py, add these to the PasswordCracker class:

from enhanced_hashcat import HashcatEnhancements

class PasswordCracker(HashcatEnhancements):
    def __init__(self, config: Dict, database):
        # ... existing init code ...
        
        # Add enhanced hashcat config
        self.hashcat_rules_dir = config['cracking'].get('hashcat_rules_dir', './rules')
        self.hashcat_use_rules = config['cracking'].get('use_rules', True)
        self.hashcat_brute_force = config['cracking'].get('brute_force', False)
        self.hashcat_brute_max_length = config['cracking'].get('brute_max_length', 8)
        self.hashcat_extra_wordlists = config['cracking'].get('extra_wordlists', [])
    
    def _crack_with_hashcat_enhanced(self, handshake: Dict) -> Optional[tuple]:
        '''Enhanced hashcat with multiple strategies'''
        hash_file = handshake['file_path'].replace('.cap', '.22000')
        output_file = hash_file + '.cracked'
        session = f"pendonn_{handshake['id']}"
        
        # Strategy 1: Primary wordlist
        result = self._run_hashcat_dict(hash_file, self.wordlist, output_file)
        if result:
            return result
        
        # Strategy 2: Rule-based attacks
        if self.hashcat_use_rules:
            result = self.hashcat_rule_attacks(
                hash_file, self.wordlist, output_file, 
                self.hashcat_rules_dir, self.hashcat_mode, session
            )
            if result:
                return result
        
        # Strategy 3: Additional wordlists
        if self.hashcat_extra_wordlists:
            result = self.hashcat_multi_wordlist(
                hash_file, self.hashcat_extra_wordlists, 
                output_file, self.hashcat_mode, session
            )
            if result:
                return result
        
        # Strategy 4: Brute force
        if self.hashcat_brute_force:
            result = self.hashcat_brute_force(
                hash_file, output_file, 
                self.hashcat_brute_max_length, self.hashcat_mode, session
            )
            if result:
                return result
        
        return None
"""
