"""
PenDonn Display Module
Handles Waveshare display output
"""

import os
import sys
import time
import threading
import logging
from typing import Dict
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    import RPi.GPIO as GPIO
    import spidev
    DISPLAY_AVAILABLE = True
except ImportError:
    DISPLAY_AVAILABLE = False
    logging.warning("Display libraries not available. Display functionality disabled.")

logger = logging.getLogger(__name__)


class Display:
    """Waveshare display handler"""
    
    def __init__(self, config: Dict, database):
        """Initialize display"""
        self.config = config
        self.db = database
        
        self.enabled = config['display']['enabled'] and DISPLAY_AVAILABLE
        self.refresh_interval = config['display']['refresh_interval']
        
        self.running = False
        self.update_thread = None
        
        if self.enabled:
            self._init_display()
            logger.info("Display initialized")
        else:
            logger.info("Display disabled or not available")
    
    def _init_display(self):
        """Initialize Waveshare display hardware"""
        try:
            # Import Waveshare library (if available)
            # Note: This is a placeholder - actual implementation depends on Waveshare V4 specifics
            self.display_width = 480
            self.display_height = 800
            
            # Create image buffer
            self.image = Image.new('RGB', (self.display_width, self.display_height), (0, 0, 0))
            self.draw = ImageDraw.Draw(self.image)
            
            # Try to load fonts
            try:
                self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
                self.font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
                self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            except:
                # Fallback to default font
                self.font_large = ImageFont.load_default()
                self.font_medium = ImageFont.load_default()
                self.font_small = ImageFont.load_default()
            
            logger.info("Display hardware initialized")
        
        except Exception as e:
            logger.error(f"Display initialization error: {e}")
            self.enabled = False
    
    def start(self):
        """Start display updates"""
        if not self.enabled:
            return
        
        logger.info("Starting display updates...")
        self.running = True
        
        self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self.update_thread.start()
        
        logger.info("Display updates started")
    
    def stop(self):
        """Stop display updates"""
        if not self.enabled:
            return
        
        logger.info("Stopping display updates...")
        self.running = False
        
        if self.update_thread:
            self.update_thread.join(timeout=5)
        
        # Clear display
        self._clear_display()
        
        logger.info("Display updates stopped")
    
    def _update_loop(self):
        """Main display update loop"""
        while self.running:
            try:
                self._render_display()
                time.sleep(self.refresh_interval)
            
            except Exception as e:
                logger.error(f"Display update error: {e}")
                time.sleep(5)
    
    def _render_display(self):
        """Render current status to display"""
        try:
            # Clear screen
            self.draw.rectangle([(0, 0), (self.display_width, self.display_height)], fill=(20, 40, 80))
            
            y_offset = 20
            
            # Title
            self.draw.text((20, y_offset), "PenDonn", font=self.font_large, fill=(255, 255, 255))
            y_offset += 50
            
            # Timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.draw.text((20, y_offset), timestamp, font=self.font_small, fill=(180, 200, 255))
            y_offset += 40
            
            # Get statistics
            stats = self.db.get_statistics()
            
            # Draw statistics
            self._draw_stat(20, y_offset, "Networks", stats['networks_discovered'])
            y_offset += 60
            
            self._draw_stat(20, y_offset, "Handshakes", stats['handshakes_captured'])
            y_offset += 60
            
            self._draw_stat(20, y_offset, "Passwords", stats['passwords_cracked'])
            y_offset += 60
            
            self._draw_stat(20, y_offset, "Scans", stats['scans_completed'])
            y_offset += 60
            
            self._draw_stat(20, y_offset, "Vulnerabilities", stats['vulnerabilities_found'])
            y_offset += 60
            
            # Draw pending items
            if stats['handshakes_pending'] > 0:
                y_offset += 20
                self.draw.text(
                    (20, y_offset), 
                    f"⚡ Cracking: {stats['handshakes_pending']}", 
                    font=self.font_medium, 
                    fill=(255, 200, 50)
                )
            
            # Update physical display (placeholder - depends on Waveshare library)
            self._update_physical_display()
        
        except Exception as e:
            logger.error(f"Display render error: {e}")
    
    def _draw_stat(self, x: int, y: int, label: str, value: int):
        """Draw a statistic on display"""
        # Label
        self.draw.text((x, y), label, font=self.font_medium, fill=(150, 180, 255))
        
        # Value
        value_str = str(value)
        self.draw.text((x + 250, y), value_str, font=self.font_medium, fill=(100, 255, 255))
    
    def _update_physical_display(self):
        """Update physical display hardware"""
        # This is a placeholder - actual implementation depends on Waveshare V4 library
        # Example pattern:
        # self.waveshare_display.display(self.image)
        pass
    
    def _clear_display(self):
        """Clear the display"""
        try:
            if hasattr(self, 'draw'):
                self.draw.rectangle(
                    [(0, 0), (self.display_width, self.display_height)], 
                    fill=(0, 0, 0)
                )
                self._update_physical_display()
        except Exception as e:
            logger.error(f"Display clear error: {e}")
    
    def show_message(self, message: str, duration: int = 3):
        """Show a temporary message"""
        if not self.enabled:
            return
        
        try:
            # Clear screen
            self.draw.rectangle([(0, 0), (self.display_width, self.display_height)], fill=(20, 40, 80))
            
            # Draw message
            self.draw.text(
                (self.display_width // 2, self.display_height // 2), 
                message, 
                font=self.font_large, 
                fill=(255, 255, 255),
                anchor="mm"
            )
            
            self._update_physical_display()
            
            # Wait
            time.sleep(duration)
        
        except Exception as e:
            logger.error(f"Show message error: {e}")


# Standalone display test
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    
    from core.database import Database
    
    config = {
        'display': {
            'enabled': True,
            'type': 'waveshare_v4',
            'refresh_interval': 2
        },
        'database': {
            'path': './data/pendonn.db'
        }
    }
    
    db = Database(config['database']['path'])
    display = Display(config, db)
    
    display.start()
    
    try:
        print("Display running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        display.stop()
