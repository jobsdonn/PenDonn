"""
PenDonn Database Module
Handles all database operations for storing networks, handshakes, 
cracked passwords, and scan results.
"""

import sqlite3
import json
import os
import shutil
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite database handler for PenDonn with thread-safe connections"""
    
    def __init__(self, db_path: str = "./data/pendonn.db"):
        """Initialize database connection"""
        self.db_path = db_path
        self._ensure_directory()
        # Use thread-local storage for connections to prevent race conditions
        self._local = threading.local()
        self._lock = threading.Lock()  # Lock for database writes
        self.init_database()
    
    def _ensure_directory(self):
        """Ensure database directory exists"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def connect(self):
        """Create thread-local database connection"""
        # Each thread gets its own connection
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=True)
            self._local.conn.row_factory = sqlite3.Row
            logger.debug(f"Created new database connection for thread {threading.current_thread().name}")
        return self._local.conn
    
    def _ensure_connection(self):
        """Ensure database connection is valid, reconnect if needed"""
        try:
            conn = self.connect()
            # Test if connection is alive
            conn.execute("SELECT 1")
            return conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # Connection is closed or invalid, reconnect
            logger.warning("Database connection lost, reconnecting...")
            self._local.conn = None
            return self.connect()
    
    def init_database(self):
        """Initialize database schema"""
        try:
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

            # Scope authorizations: each row is a human "I confirm we have
            # written authorization to attack these SSIDs" gate. Latest row
            # is the authoritative receipt. Daemon refuses to attack any
            # SSID not present in the latest row's ssids_json.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scope_authorizations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    confirmed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_by TEXT,
                    ssids_json TEXT NOT NULL,
                    note TEXT,
                    revoked INTEGER DEFAULT 0,
                    revoked_at TIMESTAMP,
                    revoked_by TEXT
                )
            ''')

            # Audit log: append-only record of operator-visible actions.
            # Captures who did what when, for compliance + post-engagement
            # review. Distinct from system_logs (which is for the daemon's
            # own runtime info) — audit_log is for human-attributable
            # actions and security-relevant daemon decisions.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actor TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    details TEXT,
                    source_ip TEXT
                )
            ''')
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp '
                'ON audit_log (timestamp DESC)'
            )

            conn.commit()
            # Don't close the connection - let it stay open for thread-local use
            # conn.close()
            logger.info("Database initialized successfully")
            
        except sqlite3.OperationalError as e:
            if "disk I/O error" in str(e):
                logger.error("Disk I/O error while initializing database!")
                logger.error("Possible causes:")
                logger.error("  - SD card corruption (run: sudo fsck)")
                logger.error("  - Insufficient disk space")
                logger.error("  - Filesystem mounted read-only")
                logger.error("  - Bad SD card sectors")
                raise RuntimeError(f"Database initialization failed due to disk error: {e}")
            else:
                logger.error(f"Database operational error: {e}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise
    
    # Network operations
    def add_network(self, ssid: str, bssid: str, channel: int, 
                   encryption: str, signal_strength: int) -> int:
        """Add or update a discovered network"""
        with self._lock:  # Protect writes with lock
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
            
            # Get the network_id (either newly inserted or existing)
            cursor.execute('SELECT id FROM networks WHERE bssid = ?', (bssid,))
            network_id = cursor.fetchone()['id']
            conn.commit()
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
        return networks
    
    def get_network_by_bssid(self, bssid: str) -> Optional[Dict]:
        """Get network by BSSID"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM networks WHERE bssid = ?', (bssid,))
        row = cursor.fetchone()
        
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
        return handshakes
    
    def get_handshakes_for_network(self, bssid: str) -> List[Dict]:
        """Get all handshakes for a specific network"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM handshakes WHERE bssid = ?', (bssid,))
        handshakes = [dict(row) for row in cursor.fetchall()]
        return handshakes

    def get_all_handshakes(self, status: Optional[str] = None) -> List[Dict]:
        """Get all handshakes, newest first, optionally filtered by status.

        Note: schema column is `capture_date` (singular). Don't rename it
        — the existing data on deployed Pis would migrate badly.
        """
        conn = self.connect()
        cursor = conn.cursor()
        if status:
            cursor.execute(
                'SELECT * FROM handshakes WHERE status = ? ORDER BY capture_date DESC',
                (status,),
            )
        else:
            cursor.execute('SELECT * FROM handshakes ORDER BY capture_date DESC')
        return [dict(row) for row in cursor.fetchall()]
    
    def update_handshake_status(self, handshake_id: int, status: str):
        """Update handshake processing status"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('UPDATE handshakes SET status = ? WHERE id = ?', 
                      (status, handshake_id))
        conn.commit()
    
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
        logger.info(f"Password cracked for {ssid} using {engine}")
        return password_id
    
    def get_cracked_passwords(self) -> List[Dict]:
        """Get all cracked passwords"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cracked_passwords ORDER BY cracked_date DESC')
        passwords = [dict(row) for row in cursor.fetchall()]
        return passwords
    
    def get_password_for_network(self, bssid: str) -> Optional[str]:
        """Get cracked password for a specific network"""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM cracked_passwords WHERE bssid = ? LIMIT 1', 
                      (bssid,))
        result = cursor.fetchone()
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
        return vulns

    # ----- Scope authorization -----
    #
    # The "scope authorization" gate sits between the allowlist and the
    # actual attack code. The allowlist alone says *which SSIDs are
    # configured as in-scope*; the scope authorization says *a human
    # confirmed in the UI that those SSIDs are authorized to attack right
    # now*. Daemon refuses handshake/deauth attacks against any SSID not
    # covered by the latest non-revoked scope_authorizations row.

    def confirm_scope(self, ssids: List[str], confirmed_by: str,
                      note: Optional[str] = None) -> int:
        """Record an operator's confirmation that the given SSIDs are
        authorized to attack. Returns the new row id."""
        with self._lock:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO scope_authorizations (confirmed_by, ssids_json, note) VALUES (?, ?, ?)',
                (confirmed_by, json.dumps(sorted(set(ssids))), note),
            )
            row_id = cursor.lastrowid
            conn.commit()
            logger.info(f"Scope confirmed by {confirmed_by} for {len(ssids)} SSID(s)")
            return row_id

    def revoke_scope(self, revoked_by: str) -> bool:
        """Revoke the latest active scope authorization. Returns True if a
        row was actually revoked, False if there was nothing to revoke."""
        with self._lock:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id FROM scope_authorizations WHERE revoked = 0 ORDER BY id DESC LIMIT 1'
            )
            row = cursor.fetchone()
            if not row:
                return False
            cursor.execute(
                'UPDATE scope_authorizations SET revoked = 1, '
                'revoked_at = CURRENT_TIMESTAMP, revoked_by = ? WHERE id = ?',
                (revoked_by, row['id']),
            )
            conn.commit()
            logger.info(f"Scope authorization {row['id']} revoked by {revoked_by}")
            return True

    def get_active_scope(self) -> Optional[Dict]:
        """Return the latest non-revoked scope authorization, or None.

        The shape includes a parsed ssids list (not the raw JSON), so
        callers can compare directly against the configured allowlist."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM scope_authorizations WHERE revoked = 0 '
            'ORDER BY id DESC LIMIT 1'
        )
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d['ssids'] = json.loads(d['ssids_json']) if d.get('ssids_json') else []
        except (TypeError, ValueError):
            d['ssids'] = []
        return d

    def is_scope_confirmed_for(self, allowlist_ssids: List[str]) -> Tuple[bool, List[str]]:
        """Check whether the given allowlist is fully covered by the latest
        scope authorization.

        Returns a (confirmed, missing) pair:
          - confirmed=True  -> every SSID in allowlist is in the active scope
          - confirmed=False -> missing[] holds the SSIDs that are not yet
            authorized; UI should prompt operator to re-confirm.
        Empty allowlist trivially counts as confirmed (nothing to attack).
        """
        wanted = sorted(set(allowlist_ssids))
        if not wanted:
            return (True, [])
        active = self.get_active_scope()
        if not active:
            return (False, wanted)
        confirmed_set = set(active.get('ssids') or [])
        missing = [s for s in wanted if s not in confirmed_set]
        return (not missing, missing)

    # ----- Audit log -----
    #
    # Append-only record of operator-visible actions. The intent is a
    # single place to answer "who did what when" — covering both human
    # actions through the WebUI and security-relevant daemon decisions.
    # Use dotted action names: `<area>.<verb>` (e.g. `scope.confirm`,
    # `allowlist.add`, `attack.refused`, `login.failure`).

    def add_audit_log(
        self,
        action: str,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        details: Optional[Dict] = None,
        source_ip: Optional[str] = None,
    ) -> int:
        """Append an audit-log entry. Best-effort — never raises into the
        caller; an audit-log failure must not break the actual operation."""
        try:
            with self._lock:
                conn = self.connect()
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO audit_log (actor, action, target, details, source_ip) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (actor, action, target,
                     json.dumps(details) if details is not None else None,
                     source_ip),
                )
                row_id = cursor.lastrowid
                conn.commit()
                return row_id
        except Exception as e:
            logger.warning(f"audit_log write failed (action={action}): {e}")
            return 0

    def get_audit_log(
        self,
        action_prefix: Optional[str] = None,
        actor: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict]:
        """Read recent audit log entries, newest first.

        action_prefix matches dotted prefixes — e.g. 'scope.' returns
        scope.confirm and scope.revoke; 'login' returns login.success
        and login.failure.
        """
        conn = self.connect()
        cursor = conn.cursor()
        query = 'SELECT * FROM audit_log WHERE 1=1'
        params: List = []
        if action_prefix:
            query += ' AND action LIKE ?'
            params.append(action_prefix + '%')
        if actor:
            query += ' AND actor = ?'
            params.append(actor)
        # Order by id DESC as well as timestamp — SQLite's CURRENT_TIMESTAMP
        # is per-second, so two events in the same second would otherwise
        # come back in undefined order.
        query += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        cursor.execute(query, params)
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            # Parse details JSON for templates that want to render it.
            if d.get('details'):
                try:
                    d['details_parsed'] = json.loads(d['details'])
                except (TypeError, ValueError):
                    d['details_parsed'] = None
            else:
                d['details_parsed'] = None
            rows.append(d)
        return rows

    # System logs
    def add_log(self, module: str, message: str, level: str = "INFO") -> int:
        """Insert a row into system_logs.

        Called from evil_twin and enumerator. Args match the order they pass:
        (module, message, level). Returns the new row id.
        """
        with self._lock:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO system_logs (level, module, message) VALUES (?, ?, ?)',
                (level, module, message),
            )
            row_id = cursor.lastrowid
            conn.commit()
            return row_id

    def get_logs(self, level: Optional[str] = None, module: Optional[str] = None,
                 limit: int = 200) -> List[Dict]:
        """Read recent rows from system_logs, optionally filtered."""
        conn = self.connect()
        cursor = conn.cursor()
        query = 'SELECT * FROM system_logs WHERE 1=1'
        params: List = []
        if level:
            query += ' AND level = ?'
            params.append(level)
        if module:
            query += ' AND module = ?'
            params.append(module)
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

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
    
    def purge_old_data(
        self,
        system_logs_days: int = 7,
        failed_handshakes_days: int = 30,
        scans_days: int = 90,
        handshakes_dir: str = "./handshakes",
    ) -> Dict:
        """Delete old rows to keep the database from growing unbounded.

        Rules:
          - system_logs: rows older than system_logs_days are deleted.
          - handshakes: rows with status='failed' older than
            failed_handshakes_days are deleted; their files are removed.
          - scans + vulnerabilities: scans older than scans_days are deleted
            (cascade deletes vulnerabilities via FK).
          - cracked_passwords: never purged — operator evidence.
          - audit_log: never purged — legal/compliance evidence.

        Returns a dict summarising what was deleted.
        """
        result = {"logs": 0, "handshakes": 0, "handshake_files": 0, "scans": 0}
        try:
            conn = self._ensure_connection()

            if system_logs_days > 0:
                cur = conn.execute(
                    "DELETE FROM system_logs WHERE timestamp < datetime('now', ?)",
                    (f"-{system_logs_days} days",),
                )
                result["logs"] = cur.rowcount

            if failed_handshakes_days > 0:
                # Collect capture file paths before deleting rows.
                rows = conn.execute(
                    "SELECT file_path FROM handshakes "
                    "WHERE status='failed' AND capture_date < datetime('now', ?)",
                    (f"-{failed_handshakes_days} days",),
                ).fetchall()
                stale_files = [r[0] for r in rows if r[0]]
                cur = conn.execute(
                    "DELETE FROM handshakes "
                    "WHERE status='failed' AND capture_date < datetime('now', ?)",
                    (f"-{failed_handshakes_days} days",),
                )
                result["handshakes"] = cur.rowcount
                for fpath in stale_files:
                    for ext in ("", ".pcapng", ".cap", ".22000"):
                        p = fpath if not ext else (
                            fpath.rsplit(".", 1)[0] + ext
                            if "." in fpath else fpath + ext
                        )
                        if os.path.isfile(p):
                            try:
                                os.unlink(p)
                                result["handshake_files"] += 1
                            except OSError:
                                pass

            if scans_days > 0:
                cur = conn.execute(
                    "DELETE FROM scans WHERE started_at < datetime('now', ?)",
                    (f"-{scans_days} days",),
                )
                result["scans"] = cur.rowcount

            conn.commit()

            total = sum(result.values())
            if total > 0:
                logger.info(
                    "Retention purge: %d log rows, %d handshake rows, "
                    "%d files, %d scan rows deleted",
                    result["logs"], result["handshakes"],
                    result["handshake_files"], result["scans"],
                )
            else:
                logger.debug("Retention purge: nothing to clean up")

        except Exception as e:
            logger.error(f"Retention purge failed: {e}", exc_info=True)

        return result

    def close(self):
        """Close database connection for current thread"""
        if hasattr(self._local, 'conn') and self._local.conn:
            try:
                self._local.conn.close()
                self._local.conn = None
                logger.debug(f"Closed database connection for thread {threading.current_thread().name}")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}", exc_info=True)
    
    def close_all(self):
        """Close all database connections (call during shutdown)"""
        # Close the current thread's connection
        self.close()


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
