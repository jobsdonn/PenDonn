#!/usr/bin/env python3
"""
Test script for mock system with realistic data
This validates the complete flow: scan -> capture -> crack
"""

import sys
import time
import logging
from main import PenDonn

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def test_mock_system():
    """Test the complete mock system flow"""
    logger.info("=" * 70)
    logger.info("Testing Mock System with Realistic Data")
    logger.info("=" * 70)
    
    # Initialize PenDonn with debug config
    logger.info("\n1. Initializing PenDonn with debug config...")
    system = PenDonn(config_path='./config/config.debug.json')
    
    # Start the system
    logger.info("\n2. Starting all modules...")
    system.start()
    
    # Let it run for a while to see results
    logger.info("\n3. System running - monitoring for 60 seconds...")
    logger.info("   - Networks should be discovered within 5-10 seconds")
    logger.info("   - Handshakes should be captured within 15-30 seconds")
    logger.info("   - Passwords should be cracked within 45-60 seconds")
    logger.info("-" * 70)
    
    try:
        for i in range(60):
            time.sleep(1)
            
            # Show progress every 10 seconds
            if (i + 1) % 10 == 0:
                logger.info(f"\n[{i+1}s] Progress check:")
                
                # Query database for stats
                networks = system.db.get_networks()
                handshakes = system.db.get_pending_handshakes()
                cracked = system.db.get_cracked_passwords()
                
                logger.info(f"  Networks discovered: {len(networks)}")
                logger.info(f"  Handshakes captured: {len(handshakes)}")
                logger.info(f"  Passwords cracked: {len(cracked)}")
                
                # Show cracked passwords
                if cracked:
                    logger.info("  Cracked networks:")
                    for entry in cracked[-3:]:  # Show last 3
                        logger.info(f"    - {entry['ssid']}: '{entry['password']}'")
    
    except KeyboardInterrupt:
        logger.info("\n\nTest interrupted by user")
    
    finally:
        # Stop the system
        logger.info("\n4. Stopping system...")
        system.stop()
        
        # Final statistics
        logger.info("\n" + "=" * 70)
        logger.info("Final Test Results")
        logger.info("=" * 70)
        
        networks = system.db.get_networks()
        handshakes = system.db.get_pending_handshakes()
        cracked = system.db.get_cracked_passwords()
        
        logger.info(f"Networks discovered: {len(networks)}")
        logger.info(f"Handshakes captured: {len(handshakes)}")
        logger.info(f"Passwords cracked: {len(cracked)}")
        
        if cracked:
            logger.info("\nCracked Passwords:")
            for entry in cracked:
                logger.info(f"  SSID: {entry['ssid']}")
                logger.info(f"  BSSID: {entry['bssid']}")
                logger.info(f"  Password: '{entry['password']}'")
                logger.info(f"  Crack time: {entry['crack_time_seconds']}s")
                logger.info(f"  Tool: {entry['cracking_engine']}")
                logger.info("-" * 70)
        
        # Success criteria
        logger.info("\n" + "=" * 70)
        success = len(networks) > 0 and len(handshakes) > 0 and len(cracked) > 0
        
        if success:
            logger.info("✓ TEST PASSED - Mock system working with realistic data!")
            logger.info("  - Networks discovered successfully")
            logger.info("  - Handshakes captured successfully")
            logger.info("  - Passwords cracked successfully")
        else:
            logger.warning("✗ TEST INCOMPLETE - Some steps didn't complete")
            logger.warning(f"  Networks: {'✓' if len(networks) > 0 else '✗'}")
            logger.warning(f"  Handshakes: {'✓' if len(handshakes) > 0 else '✗'}")
            logger.warning(f"  Cracked: {'✓' if len(cracked) > 0 else '✗'}")
        
        logger.info("=" * 70)
        
        return success


if __name__ == "__main__":
    success = test_mock_system()
    sys.exit(0 if success else 1)
