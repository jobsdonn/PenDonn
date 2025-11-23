#!/usr/bin/env python3
"""
PenDonn Debug Mode Test Script
Quick test of all debug features
"""

import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database
from core.test_data_generator import TestDataGenerator

def print_banner():
    print("\n" + "="*60)
    print("  PenDonn Debug Mode - Test Data Generator")
    print("="*60 + "\n")

def main():
    print_banner()
    
    # Initialize database
    db_path = './data/pendonn_debug.db'
    print(f"📂 Initializing database: {db_path}")
    db = Database(db_path)
    
    # Check current stats
    stats = db.get_statistics()
    print(f"\n📊 Current Database Statistics:")
    print(f"   Networks: {stats['networks_discovered']}")
    print(f"   Handshakes: {stats['handshakes_captured']}")
    print(f"   Passwords: {stats['passwords_cracked']}")
    print(f"   Scans: {stats['scans_completed']}")
    print(f"   Vulnerabilities: {stats['vulnerabilities_found']}")
    
    # Ask if user wants to generate test data
    if stats['networks_discovered'] > 0:
        print(f"\n⚠️  Database already contains data.")
        response = input("   Generate additional test data? (y/n): ")
        if response.lower() != 'y':
            print("\n✓ Exiting without changes")
            db.close()
            return
    
    # Generate test data
    print("\n🔧 Generating test data...")
    generator = TestDataGenerator(db)
    
    print("   → Creating networks...")
    generator.generate_networks(12)
    
    print("   → Creating handshakes...")
    generator.generate_handshakes(8)
    
    print("   → Creating cracked passwords...")
    generator.generate_cracked_passwords(4)
    
    print("   → Creating network scans...")
    generator.generate_scans(4)
    
    print("   → Creating vulnerabilities...")
    generator.generate_vulnerabilities(10)
    
    # Show new stats
    stats = db.get_statistics()
    print(f"\n✅ Test data generated successfully!")
    print(f"\n📊 Updated Database Statistics:")
    print(f"   Networks: {stats['networks_discovered']}")
    print(f"   Handshakes: {stats['handshakes_captured']}")
    print(f"   Passwords: {stats['passwords_cracked']}")
    print(f"   Scans: {stats['scans_completed']}")
    print(f"   Vulnerabilities: {stats['vulnerabilities_found']}")
    print(f"     - Critical: {stats['critical_vulnerabilities']}")
    print(f"     - High: {stats['high_vulnerabilities']}")
    print(f"     - Medium: {stats['medium_vulnerabilities']}")
    print(f"     - Low: {stats['low_vulnerabilities']}")
    
    print("\n🎯 Next Steps:")
    print("   1. Start PenDonn in debug mode:")
    print("      python main.py --debug")
    print("   2. Open web interface:")
    print("      http://localhost:8080")
    print("   3. Explore the generated test data!")
    
    db.close()
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
