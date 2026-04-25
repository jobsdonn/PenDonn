#!/usr/bin/env python3
"""
Patch Waveshare epdconfig.py to delay GPIO initialization.

The original epdconfig.py initializes GPIO hardware at import time (line ~313):
    implementation = RaspberryPi()
    
This causes RuntimeError when importing without root permissions or GPIO hardware.

This script modifies epdconfig.py to only initialize when explicitly called,
following the same pattern as pwnagotchi.
"""

import sys
import os
import re

def patch_epdconfig(filepath):
    """
    Patch epdconfig.py to delay GPIO initialization
    
    Changes:
    1. Comment out module-level initialization: implementation = RaspberryPi()
    2. Add lazy initialization in functions that need it
    """
    
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        return False
    
    print(f"Patching {filepath}...")
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Check if already patched
    if '# PATCHED BY PENDONN' in content:
        print("Already patched, skipping...")
        return True
    
    # Pattern 1: Comment out module-level initialization
    # implementation = RaspberryPi()
    content = re.sub(
        r'^implementation = RaspberryPi\(\)',
        r'# PATCHED BY PENDONN - Delay GPIO initialization\n# implementation = RaspberryPi()\nimplementation = None  # Will be initialized on first use',
        content,
        flags=re.MULTILINE
    )
    
    # Pattern 2: Add lazy initialization to module_init
    if 'def module_init' in content:
        content = re.sub(
            r'(def module_init.*?:.*?\n)',
            r'''\1    global implementation
    if implementation is None:
        implementation = RaspberryPi()
    ''',
            content,
            flags=re.DOTALL,
            count=1
        )
    
    # Pattern 3: Add lazy initialization to all functions that use implementation
    functions_to_patch = [
        'digital_write',
        'digital_read', 
        'delay_ms',
        'spi_writebyte',
        'module_exit'
    ]
    
    for func_name in functions_to_patch:
        pattern = rf'(def {func_name}.*?:.*?\n)'
        replacement = r'''\1    global implementation
    if implementation is None:
        implementation = RaspberryPi()
    '''
        content = re.sub(pattern, replacement, content, flags=re.DOTALL, count=1)
    
    # Check if we actually changed anything
    if content == original_content:
        print("Warning: No changes made - pattern not found")
        print("This might be a different version of epdconfig.py")
        return False
    
    # Backup original
    backup_path = filepath + '.original'
    if not os.path.exists(backup_path):
        with open(backup_path, 'w') as f:
            f.write(original_content)
        print(f"Backup saved to {backup_path}")
    
    # Write patched version
    with open(filepath, 'w') as f:
        f.write(content)
    
    print("✓ Patching complete")
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: patch_waveshare.py <path_to_epdconfig.py>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success = patch_epdconfig(filepath)
    sys.exit(0 if success else 1)
