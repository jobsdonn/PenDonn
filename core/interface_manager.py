"""
PenDonn Interface Manager
Handles MAC-based interface detection to prevent issues with USB adapter name swapping
"""

import subprocess
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_mac_to_interface_mapping() -> Dict[str, str]:
    """Get mapping of MAC addresses to interface names
    
    Returns:
        Dict mapping MAC addresses (lowercase) to interface names
    """
    mapping = {}
    try:
        # Get all network interfaces
        result = subprocess.run(['ip', 'link', 'show'], 
                              capture_output=True, text=True, check=True)
        
        current_iface = None
        for line in result.stdout.split('\n'):
            # Interface name line: "3: wlan0: <...>"
            if ': wlan' in line and '<' in line:
                parts = line.split(': ')
                if len(parts) >= 2:
                    current_iface = parts[1].split(':')[0]  # Extract "wlan0"
            
            # MAC address line: "    link/ether aa:bb:cc:dd:ee:ff ..." or "    link/ieee802.11/radiotap aa:bb:cc:dd:ee:ff ..."
            elif ('link/ether' in line or 'link/ieee802.11' in line) and current_iface:
                mac = line.strip().split()[1].lower()
                mapping[mac] = current_iface
                logger.debug(f"Found interface {current_iface} with MAC {mac}")
                current_iface = None
        
        return mapping
    except Exception as e:
        logger.error(f"Failed to detect MAC to interface mapping: {e}")
        return {}


def get_interface_by_mac(mac: str) -> Optional[str]:
    """Get interface name for a given MAC address
    
    Args:
        mac: MAC address (can be any case, with or without colons)
    
    Returns:
        Interface name (e.g., 'wlan0') or None if not found
    """
    mac = mac.lower().replace('-', ':')
    mapping = get_mac_to_interface_mapping()
    return mapping.get(mac)


def resolve_interfaces(config: Dict) -> Dict[str, str]:
    """Resolve interface names from config using MAC addresses
    
    Args:
        config: Full config dict with wifi section
    
    Returns:
        Dict with resolved interface names: {
            'monitor': 'wlan0',
            'attack': 'wlan1',
            'management': 'wlan2'
        }
    """
    wifi_config = config.get('wifi', {})
    
    # Try MAC-based detection first (more reliable)
    monitor_mac = wifi_config.get('monitor_mac')
    attack_mac = wifi_config.get('attack_mac')
    management_mac = wifi_config.get('management_mac')
    
    result = {
        'monitor': None,
        'attack': None,
        'management': None
    }
    
    if monitor_mac and attack_mac and management_mac:
        # Detect current interface names by MAC address
        mac_to_iface = get_mac_to_interface_mapping()
        
        result['monitor'] = mac_to_iface.get(monitor_mac.lower())
        result['attack'] = mac_to_iface.get(attack_mac.lower())
        result['management'] = mac_to_iface.get(management_mac.lower())
        
        if not all(result.values()):
            logger.error(f"Could not find all interfaces by MAC!")
            logger.error(f"  Monitor MAC {monitor_mac} -> {result['monitor']}")
            logger.error(f"  Attack MAC {attack_mac} -> {result['attack']}")
            logger.error(f"  Management MAC {management_mac} -> {result['management']}")
            
            # Fall back to interface names
            result['monitor'] = wifi_config.get('monitor_interface', 'wlan0')
            result['attack'] = wifi_config.get('attack_interface', 'wlan1')
            result['management'] = wifi_config.get('management_interface', 'wlan2')
            logger.warning(f"Falling back to interface names from config")
        else:
            logger.info(f"✓ Resolved interfaces by MAC address:")
            logger.info(f"  Monitor: {result['monitor']} ({monitor_mac})")
            logger.info(f"  Attack: {result['attack']} ({attack_mac})")
            logger.info(f"  Management: {result['management']} ({management_mac})")
    else:
        # Fall back to interface names (legacy config)
        result['monitor'] = wifi_config.get('monitor_interface', 'wlan0')
        result['attack'] = wifi_config.get('attack_interface', 'wlan1')
        result['management'] = wifi_config.get('management_interface', 'wlan2')
        logger.warning(f"No MAC addresses in config - using interface names (may swap on reboot!)")
    
    return result
