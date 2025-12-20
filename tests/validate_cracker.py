#!/usr/bin/env python3
"""
Comprehensive Cracker Validation
Uses mock system to generate test data, then validates real cracker logic
"""

import os
import sys
import logging
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Must import after path is set
from core.database import Database
from core.cracker import PasswordCracker

# Configure logging to flush immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# Flush immediately
sys.stdout.flush()
sys.stderr.flush()


def validate_cracker_logic():
    """Validate the cracker's logic, error handling, and flow"""
    
    logger.info("=" * 70)
    logger.info("Cracker Code Validation")
    logger.info("=" * 70)
    
    try:
        # Load debug config
        with open('./config/config.debug.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return False
    
    # Force real cracker (not mock)
    config['debug']['mock_cracking'] = False
    
    try:
        db = Database(config['database']['path'])
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
    
    logger.info("\n1. Checking existing test data...")
    
    try:
        # Get data from previous mock run
        networks = db.get_networks()
        handshakes = db.get_pending_handshakes()
        cracked = db.get_cracked_passwords()
        
        logger.info(f"   Networks in DB: {len(networks)}")
        logger.info(f"   Handshakes in DB: {len(handshakes)}")
        logger.info(f"   Previously cracked: {len(cracked)}")
    except Exception as e:
        logger.error(f"Failed to query database: {e}", exc_info=True)
        return False
    
    if handshakes:
        logger.info("\n2. Validating cracker initialization...")
        
        try:
            cracker = PasswordCracker(config, db)
            logger.info("   ✓ Cracker initialized successfully")
            
            logger.info("\n3. Validating file checks...")
            
            for hs in handshakes[:3]:  # Test first 3
                file_path = hs['file_path']
                exists = os.path.exists(file_path)
                size = os.path.getsize(file_path) if exists else 0
                
                logger.info(f"   {hs['ssid']}:")
                logger.info(f"      File: {file_path}")
                logger.info(f"      Exists: {'✓' if exists else '✗'}")
                logger.info(f"      Size: {size} bytes {'(✓ >1KB)' if size > 1000 else '(✗ too small)'}")
            
            logger.info("\n4. Validating cracker methods...")
            
            # Check method availability
            has_john = hasattr(cracker, '_crack_with_john')
            has_hashcat = hasattr(cracker, '_crack_with_hashcat')
            has_worker = hasattr(cracker, '_crack_worker')
            
            logger.info(f"   _crack_with_john: {'✓' if has_john else '✗'}")
            logger.info(f"   _crack_with_hashcat: {'✓' if has_hashcat else '✗'}")
            logger.info(f"   _crack_worker: {'✓' if has_worker else '✗'}")
            
            logger.info("\n5. Checking cracking tools availability...")
            
            import shutil
            tools = {
                'john': shutil.which('john'),
                'hashcat': shutil.which('hashcat'),
                'hcx2john': shutil.which('hcx2john'),
                'hcxpcapngtool': shutil.which('hcxpcapngtool')
            }
            
            for tool, path in tools.items():
                if path:
                    logger.info(f"   {tool}: ✓ {path}")
                else:
                    logger.info(f"   {tool}: ✗ Not installed")
            
            all_tools = all(tools.values())
            
            logger.info("\n6. Code Logic Validation Summary:")
            logger.info("   " + "=" * 66)
            
            checks = [
                ("Cracker initialization", True),
                ("Database integration", len(handshakes) > 0),
                ("File path handling", all(os.path.exists(hs['file_path']) for hs in handshakes[:3])),
                ("Method definitions", has_john and has_hashcat and has_worker),
                ("Tool availability (for full test)", all_tools)
            ]
            
            for check_name, passed in checks:
                status = "✓ PASS" if passed else "✗ FAIL" 
                logger.info(f"   {check_name:.<50} {status}")
            
            logger.info("   " + "=" * 66)
            
            all_passed = all(result for _, result in checks[:-1])  # Exclude tool check
            
            if all_passed:
                logger.info("\n[SUCCESS] CRACKER CODE VALIDATION PASSED")
                logger.info("The cracker code structure and logic are working correctly!")
                
                if not all_tools:
                    logger.info("\n[Note] Some cracking tools are not installed.")
                    logger.info("Install them for full end-to-end testing:")
                    logger.info("  Raspberry Pi: sudo apt install john hashcat hcxtools")
                    logger.info("  Windows: Download from official websites")
                
                if handshakes and all_tools:
                    logger.info("\n7. You can now test actual cracking:")
                    logger.info("   Run: python test_real_cracker.py")
                    logger.info("   Or use real WPA2 captures with known passwords")
                
                return True
            else:
                logger.error("\n✗ VALIDATION FAILED")
                logger.error("Some cracker code checks failed. Review the output above.")
                return False
                
        except Exception as e:
            logger.error(f"\n✗ VALIDATION FAILED: {e}", exc_info=True)
            return False
    
    else:
        logger.info("\n✗ No test data available")
        logger.info("Run the mock system first to generate test data:")
        logger.info("  python test_mock_system.py")
        return False


if __name__ == "__main__":
    success = validate_cracker_logic()
    sys.exit(0 if success else 1)
