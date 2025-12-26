"""
PenDonn Database Module
Handles all database operations for storing networks, handshakes, 
cracked passwords, and scan results.
"""

import sqlite3
import json
import os
import shutil
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite database handler for PenDonn"""
    
    def __init__(self, db_path: str = "./data/pendonn.db"):
        """Initialize database connection"""
        self.db_path = db_path
        self._ensure_directory()
        self.conn = None
        self.init_database()
    
    def _ensure_directory(self):
        """Ensure database directory exists"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def connect(self):
        """Create database connection"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def _ensure_connection(self):
        """Ensure database connection is valid, reconnect if needed"""
        try:
            if self.conn is None:
                return self.connect()
            # Test if connection is alive
            self.conn.execute("SELECT 1")
            return self.conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # Connection is closed or invalid, reconnect
            logger.warning("Database connection lost, reconnecting...")
            return self.connect()
    
    def init_database(self):
        """Initialize database schema"""
        conn = self.connect()
        cursor = conn.cursor()
        
        # Networks table - stores discovered networks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS networks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ssid TEXT NOT NULL,
                bssid TEXT NOT NULL UNIQUE,
                channel INTEGER,
                encryption TEXT,
                signal_strength INTEGER,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_whitelisted BOOLEAN DEFAULT 0,
                notes TEXT
            )
        ''')
        
        # Handshakes table - stores captured handshakes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS handshakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network_id INTEGER,
                bssid TEXT NOT NULL,
                ssid TEXT NOT NULL,
                file_path TEXT NOT NULL,
                capture_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                quality TEXT,
                FOREIGN KEY (network_id) REFERENCES networks(id)
            )
        ''')
        
        # Cracked passwords table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cracked_passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handshake_id INTEGER,
                ssid TEXT NOT NULL,
                bssid TEXT NOT NULL,
                password TEXT NOT NULL,
                cracking_engine TEXT,
                crack_time_seconds INTEGER,
                cracked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (handshake_id) REFERENCES handshakes(id)
            )
        ''')
        
        # Enumeration scans table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                network_id INTEGER,
                ssid TEXT NOT NULL,
                scan_type TEXT NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'running',
                results TEXT,
                vulnerabilities_found INTEGER DEFAULT 0,
                FOREIGN KEY (network_id) REFERENCES networks(id)
            )
        ''')
        
        # Vulnerabilities table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vulnerabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER,
                host TEXT NOT NULL,
                port INTEGER,
                service TEXT,
                vulnerability_type TEXT NOT NULL,
                severity TEXT,
                description TEXT,
                plugin_name TEXT,
                discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans(id)
            )
        ''')
        
        # System logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT,
                module TEXT,
                message TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    # Network operations
    def add_network(self, ssid: str, bssid: str, channel: int, 
                   encryption: str, signal_strength: int) -> int:
        """Add or update a discovered network"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO networks (ssid, bssid, channel, encryption, signal_strength, last_seen)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bssid) DO UPDATE SET
                signal_strength = excluded.signal_strength,
                last_seen = CURRENT_TIMESTAMP,
                channel = excluded.channel,
                encryption = excluded.encryption,
                ssid = excluded.ssid
        ''', (ssid, bssid, channel, encryption, signal_strength))
        
        network_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return network_id
        return network_id
    
    def get_networks(self, whitelisted: Optional[bool] = None) -> List[Dict]:
        """Get all networks, optionally filtered by whitelist status"""
        conn = self.connect()
        cursor = conn.cursor()
        
        if whitelisted is None:
            cursor.execute('SELECT * FROM networks ORDER BY last_seen DESC')
        else:
            cursor.execute('SELECT * FROM networks WHERE is_whitelisted = ? ORDER BY last_seen DESC', 
                         (1 if whitelisted else 0,))
        
        networks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return networks
    
    def get_network_by_bssid(self, bssid: str) -> Optional[Dict]:
        """Get network by BSSID"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM networks WHERE bssid = ?', (bssid,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def set_whitelist(self, bssid: str, whitelisted: bool):
        """Set whitelist status for a network"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('UPDATE networks SET is_whitelisted = ? WHERE bssid = ?', 
                      (1 if whitelisted else 0, bssid))
        conn.commit()
        conn.close()
    
    # Handshake operations
    def add_handshake(self, network_id: int, bssid: str, ssid: str, 
                     file_path: str, quality: str = "unknown") -> int:
        """Add a captured handshake"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO handshakes (network_id, bssid, ssid, file_path, quality, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        ''', (network_id, bssid, ssid, file_path, quality))
        handshake_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"Handshake captured for {ssid} ({bssid})")
        return handshake_id
    
    def get_pending_handshakes(self) -> List[Dict]:
        """Get handshakes pending cracking"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM handshakes 
            WHERE status = 'pending' 
            ORDER BY capture_date ASC
        ''')
        handshakes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return handshakes
    
    def get_handshakes_for_network(self, bssid: str) -> List[Dict]:
        """Get all handshakes for a specific network"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM handshakes WHERE bssid = ?', (bssid,))
        handshakes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return handshakes
    
    def update_handshake_status(self, handshake_id: int, status: str):
        """Update handshake processing status"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('UPDATE handshakes SET status = ? WHERE id = ?', 
                      (status, handshake_id))
        conn.commit()
        conn.close()
    
    # Password operations
    def add_cracked_password(self, handshake_id: int, ssid: str, bssid: str,
                           password: str, engine: str, crack_time: int) -> int:
        """Store a cracked password"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cracked_passwords 
            (handshake_id, ssid, bssid, password, cracking_engine, crack_time_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (handshake_id, ssid, bssid, password, engine, crack_time))
        
        # Update handshake status
        cursor.execute('UPDATE handshakes SET status = ? WHERE id = ?', 
                      ('cracked', handshake_id))
        
        password_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"Password cracked for {ssid} using {engine}")
        return password_id
    
    def get_cracked_passwords(self) -> List[Dict]:
        """Get all cracked passwords"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cracked_passwords ORDER BY cracked_date DESC')
        passwords = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return passwords
    
    def get_password_for_network(self, bssid: str) -> Optional[str]:
        """Get cracked password for a specific network"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM cracked_passwords WHERE bssid = ? LIMIT 1', 
                      (bssid,))
        result = cursor.fetchone()
        conn.close()
        return result['password'] if result else None
    
    # Scan operations
    def add_scan(self, network_id: int, ssid: str, scan_type: str) -> int:
        """Start a new enumeration scan"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO scans (network_id, ssid, scan_type, status)
            VALUES (?, ?, ?, 'running')
        ''', (network_id, ssid, scan_type))
        scan_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"Started {scan_type} scan for {ssid}")
        return scan_id
    
    def update_scan(self, scan_id: int, status: str, results: Dict, 
                   vulnerabilities_found: int):
        """Update scan results"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE scans SET 
                status = ?,
                end_time = CURRENT_TIMESTAMP,
                results = ?,
                vulnerabilities_found = ?
            WHERE id = ?
        ''', (status, json.dumps(results), vulnerabilities_found, scan_id))
        conn.commit()
        conn.close()
    
    def get_scans(self, network_id: Optional[int] = None) -> List[Dict]:
        """Get scan results"""
        conn = self.connect()
        cursor = conn.cursor()
        
        if network_id:
            cursor.execute('SELECT * FROM scans WHERE network_id = ? ORDER BY start_time DESC', 
                         (network_id,))
        else:
            cursor.execute('SELECT * FROM scans ORDER BY start_time DESC')
        
        scans = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return scans
    
    # Vulnerability operations
    def add_vulnerability(self, scan_id: int, host: str, port: Optional[int],
                         service: str, vuln_type: str, severity: str, 
                         description: str, plugin_name: str) -> int:
        """Add discovered vulnerability"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO vulnerabilities 
            (scan_id, host, port, service, vulnerability_type, severity, description, plugin_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (scan_id, host, port, service, vuln_type, severity, description, plugin_name))
        vuln_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.warning(f"Vulnerability found: {vuln_type} on {host}:{port} - {severity}")
        return vuln_id
    
    def get_vulnerabilities(self, scan_id: Optional[int] = None, 
                          severity: Optional[str] = None) -> List[Dict]:
        """Get discovered vulnerabilities"""
        conn = self.connect()
        cursor = conn.cursor()
        
        query = 'SELECT * FROM vulnerabilities WHERE 1=1'
        params = []
        
        if scan_id:
            query += ' AND scan_id = ?'
            params.append(scan_id)
        
        if severity:
            query += ' AND severity = ?'
            params.append(severity)
        
        query += ' ORDER BY discovered_date DESC'
        cursor.execute(query, params)
        
        vulns = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return vulns
    
    # Statistics
    def get_statistics(self) -> Dict:
        """Get overall system statistics"""
        conn = self.connect()
        cursor = conn.cursor()
        
        stats = {}
        
        # Networks count
        cursor.execute('SELECT COUNT(*) as count FROM networks')
        stats['networks_discovered'] = cursor.fetchone()['count']
        
        # Handshakes count
        cursor.execute('SELECT COUNT(*) as count FROM handshakes')
        stats['handshakes_captured'] = cursor.fetchone()['count']
        
        # Cracked passwords count
        cursor.execute('SELECT COUNT(*) as count FROM cracked_passwords')
        stats['passwords_cracked'] = cursor.fetchone()['count']
        
        # Pending handshakes
        cursor.execute('SELECT COUNT(*) as count FROM handshakes WHERE status = "pending"')
        stats['handshakes_pending'] = cursor.fetchone()['count']
        
        # Scans completed
        cursor.execute('SELECT COUNT(*) as count FROM scans WHERE status = "completed"')
        stats['scans_completed'] = cursor.fetchone()['count']
        
        # Total vulnerabilities
        cursor.execute('SELECT COUNT(*) as count FROM vulnerabilities')
        stats['vulnerabilities_found'] = cursor.fetchone()['count']
        
        # Critical vulnerabilities
        cursor.execute('SELECT COUNT(*) as count FROM vulnerabilities WHERE severity = "critical"')
        stats['critical_vulnerabilities'] = cursor.fetchone()['count']
        
        conn.close()
        return stats
    
    # Export and reset
    def export_data(self, export_path: str) -> str:
        """Export database to JSON file"""
        conn = self.connect()
        cursor = conn.cursor()
        
        export_data = {
            'export_date': datetime.now().isoformat(),
            'networks': [],
            'handshakes': [],
            'cracked_passwords': [],
            'scans': [],
            'vulnerabilities': [],
            'statistics': self.get_statistics()
        }
        
        # Export all tables
        for table in ['networks', 'handshakes', 'cracked_passwords', 'scans', 'vulnerabilities']:
            cursor.execute(f'SELECT * FROM {table}')
            export_data[table] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        # Write to file
        os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else '.', exist_ok=True)
        with open(export_path, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        # Create backup of database file
        if os.path.exists(self.db_path):
            backup_path = f"{self.db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backed up to {backup_path}")
        
        logger.info(f"Data exported to {export_path}")
        return export_path
    
    def reset_database(self, keep_backup: bool = True, clean_files: bool = True):
        """Reset database (clear all data and reinitialize)
        
        Args:
            keep_backup: Create backup before reset
            clean_files: Also delete captured files (handshakes, scan results)
        """
        try:
            if keep_backup:
                backup_path = f"{self.db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.copy2(self.db_path, backup_path)
                logger.info(f"Database backed up to {backup_path} before reset")
            
            # Clean up captured files if requested
            if clean_files:
                files_cleaned = 0
                dirs_to_clean = [
                    ("./captures", ['.cap', '.pcap', '.hccapx', '.22000']),
                    ("./scan_results", ['.csv', '.txt', '.json', '.xml', '.gnmap', '.nmap']),
                    ("./data", ['.backup'])  # Clean old database backups from data dir
                ]
                
                for directory, extensions in dirs_to_clean:
                    if os.path.exists(directory):
                        for file in os.listdir(directory):
                            # Skip the main database file
                            if file == os.path.basename(self.db_path):
                                continue
                            # Check if file matches extensions
                            if any(file.endswith(ext) for ext in extensions):
                                try:
                                    file_path = os.path.join(directory, file)
                                    os.remove(file_path)
                                    files_cleaned += 1
                                except Exception as e:
                                    logger.warning(f"Could not delete {file}: {e}")
                
                if files_cleaned > 0:
                    logger.info(f"Cleaned up {files_cleaned} capture/scan files")
            
            # Close current connection
            if self.conn:
                self.conn.close()
                self.conn = None
            
            # Delete old database file
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
                logger.info(f"Deleted old database: {self.db_path}")
            
            # Recreate database with fresh schema
            self._ensure_directory()
            self.init_database()
            
            # Verify new database is working
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Database reset complete. Tables created: {', '.join(tables)}")
            
            logger.warning("Database has been reset successfully")
        except Exception as e:
            logger.error(f"Error resetting database: {e}")
            raise
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


# CLI for database initialization
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        print("Initializing PenDonn database...")
        db = Database()
        print("Database initialized successfully!")
        print(f"Location: {db.db_path}")
    else:
        print("Usage: python database.py --init")
