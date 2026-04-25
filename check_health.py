#!/usr/bin/env python3
"""
PenDonn System Health Check
Monitors system health and detects potential issues
"""

import os
import sys
import time
import sqlite3
import threading
from datetime import datetime, timedelta

# Color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")

def print_error(text):
    print(f"{RED}✗ {text}{RESET}")

def check_database_health(db_path="./data/pendonn.db"):
    """Check database health"""
    print_header("Database Health Check")
    
    try:
        if not os.path.exists(db_path):
            print_error(f"Database not found: {db_path}")
            return False
        
        # Check file size
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print_success(f"Database size: {size_mb:.2f} MB")
        
        # Check database integrity
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        
        if result == "ok":
            print_success("Database integrity: OK")
        else:
            print_error(f"Database integrity: {result}")
            return False
        
        # Count records
        tables = {
            'networks': 'Networks discovered',
            'handshakes': 'Handshakes captured',
            'cracked_passwords': 'Passwords cracked',
            'scans': 'Scans completed',
            'vulnerabilities': 'Vulnerabilities found'
        }
        
        print(f"\n{BLUE}Database Statistics:{RESET}")
        for table, description in tables.items():
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {description}: {count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print_error(f"Database check failed: {e}")
        return False

def check_thread_safety():
    """Test database thread safety"""
    print_header("Thread Safety Test")
    
    try:
        db_path = "./data/pendonn.db"
        if not os.path.exists(db_path):
            print_warning(f"Database not found: {db_path}")
            print("  Run PenDonn first to create database")
            return True
        
        errors = []
        
        def thread_test(thread_id):
            """Test database access from thread"""
            try:
                for i in range(10):
                    # Direct sqlite3 access
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM networks')
                    cursor.fetchone()
                    conn.close()
                    time.sleep(0.01)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Spawn multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=thread_test, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        if errors:
            print_error(f"Thread safety issues found:")
            for error in errors:
                print(f"  - {error}")
            return False
        else:
            print_success("Thread safety test passed (5 concurrent threads)")
            return True
            
    except Exception as e:
        print_error(f"Thread test failed: {e}")
        return False

def check_log_file():
    """Check log file health"""
    print_header("Log File Check")
    
    log_path = "./logs/pendonn.log"
    
    try:
        if not os.path.exists(log_path):
            print_warning(f"Log file not found: {log_path}")
            print("  (This is normal if PenDonn hasn't been run yet)")
            return True
        
        # Check file size
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        
        if size_mb > 100:
            print_warning(f"Log file is large: {size_mb:.2f} MB")
            print("  Consider rotating or archiving logs")
        else:
            print_success(f"Log file size: {size_mb:.2f} MB")
        
        # Check for recent errors
        with open(log_path, 'r') as f:
            lines = f.readlines()
            
            if len(lines) == 0:
                print_warning("Log file is empty")
                return True
            
            # Check last 100 lines for errors
            recent_lines = lines[-100:]
            error_count = sum(1 for line in recent_lines if 'ERROR' in line)
            exception_count = sum(1 for line in recent_lines if 'Traceback' in line)
            
            if error_count > 0:
                print_warning(f"Found {error_count} errors in recent logs")
                print("  Check logs/pendonn.log for details")
            else:
                print_success("No recent errors in logs")
            
            if exception_count > 0:
                print_error(f"Found {exception_count} exceptions in recent logs")
                print("  Run: grep -A 10 'Traceback' logs/pendonn.log")
                return False
            
        return True
        
    except Exception as e:
        print_error(f"Log check failed: {e}")
        return False

def check_process_status():
    """Check if PenDonn is running"""
    print_header("Process Status")
    
    try:
        import subprocess
        
        # Check systemd service
        result = subprocess.run(['systemctl', 'is-active', 'pendonn'], 
                              capture_output=True, text=True)
        
        if result.stdout.strip() == 'active':
            print_success("PenDonn service is running")
            
            # Get uptime
            result = subprocess.run(['systemctl', 'show', 'pendonn', '--property=ActiveEnterTimestamp'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                timestamp_line = result.stdout.strip()
                print(f"  {timestamp_line}")
        else:
            print_warning("PenDonn service is not running")
            print("  Start with: sudo systemctl start pendonn")
        
        return True
        
    except FileNotFoundError:
        print_warning("systemctl not found - cannot check service status")
        return True
    except Exception as e:
        print_error(f"Process check failed: {e}")
        return False

def check_system_resources():
    """Check system resources"""
    print_header("System Resources")
    
    try:
        import subprocess
        
        # Check memory
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            mem_info = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':')
                    mem_info[key.strip()] = value.strip()
        
        total = int(mem_info['MemTotal'].split()[0]) / 1024
        available = int(mem_info['MemAvailable'].split()[0]) / 1024
        used_pct = ((total - available) / total) * 100
        
        print(f"  Memory: {available:.0f}/{total:.0f} MB available ({used_pct:.1f}% used)")
        
        if used_pct > 90:
            print_error("  WARNING: High memory usage!")
        elif used_pct > 75:
            print_warning("  Memory usage is high")
        
        # Check disk space
        result = subprocess.run(['df', '-h', '.'], capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            disk_used = parts[4] if len(parts) > 4 else "N/A"
            print(f"  Disk usage: {disk_used}")
            
            if disk_used != "N/A":
                used_val = int(disk_used.rstrip('%'))
                if used_val > 90:
                    print_error("  WARNING: Low disk space!")
                elif used_val > 75:
                    print_warning("  Disk space is getting low")
        
        return True
        
    except Exception as e:
        print_error(f"Resource check failed: {e}")
        return False

def main():
    """Run all health checks"""
    print(f"\n{BLUE}╔{'═' * 58}╗{RESET}")
    print(f"{BLUE}║{' ' * 12}PenDonn System Health Check{' ' * 19}║{RESET}")
    print(f"{BLUE}╚{'═' * 58}╝{RESET}")
    
    results = []
    
    results.append(("Database Health", check_database_health()))
    results.append(("Thread Safety", check_thread_safety()))
    results.append(("Log File Health", check_log_file()))
    results.append(("Process Status", check_process_status()))
    results.append(("System Resources", check_system_resources()))
    
    # Summary
    print_header("Health Check Summary")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"  {check_name:.<40} {status}")
    
    print(f"\n{BLUE}Overall: {passed}/{total} checks passed{RESET}\n")
    
    if passed == total:
        print(f"{GREEN}✓ System is healthy!{RESET}\n")
        return 0
    else:
        print(f"{YELLOW}⚠ Some issues found. Review output above.{RESET}\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
