"""
PenDonn Display Module
Handles Waveshare 7.3inch ACeP 7-Color E-Paper Display (800×480)
"""

import os
import sys
import time
import threading
import logging
import socket
import subprocess
from typing import Dict
from datetime import datetime

# Check if we're on actual Raspberry Pi hardware before attempting GPIO
def is_raspberry_pi():
    """Check if running on Raspberry Pi hardware"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            return 'Raspberry Pi' in f.read() or 'BCM' in f.read()
    except:
        return False

# Only attempt GPIO imports on Raspberry Pi hardware
if is_raspberry_pi():
    try:
        from PIL import Image, ImageDraw, ImageFont
        import RPi.GPIO as GPIO
        import spidev
        DISPLAY_AVAILABLE = True
    except ImportError:
        DISPLAY_AVAILABLE = False
        logging.warning("Display libraries not available. Display functionality disabled.")
else:
    DISPLAY_AVAILABLE = False
    logging.info("Not running on Raspberry Pi - Display functionality disabled")

# Try to import Waveshare library
try:
    # Add Waveshare lib to path if it exists
    waveshare_path = '/usr/local/lib/waveshare_epd'
    if os.path.exists(waveshare_path) and waveshare_path not in sys.path:
        sys.path.insert(0, waveshare_path)
    
    # Import the specific module directly (avoids circular import issues)
    # Using 2.13 inch V4 (3-color: black, white, red)
    # Note: This will fail if not running as root with GPIO access, but that's OK
    # The service runs as root and will have proper permissions
    import waveshare_epd.epd2in13_V4 as epd_driver
    
    WAVESHARE_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    # RuntimeError happens if GPIO initialization fails (not root, no GPIO hardware)
    WAVESHARE_AVAILABLE = False
    logging.warning(f"Waveshare EPD library not available: {e}. Using image simulation only.")
    epd_driver = None

logger = logging.getLogger(__name__)


class Display:
    """Waveshare 7.3inch ACeP 7-Color E-Paper Display handler"""
    
    # Define colors for 7-color display
    BLACK   = 0x000000
    WHITE   = 0xFFFFFF
    GREEN   = 0x00FF00
    BLUE    = 0x0000FF
    RED     = 0xFF0000
    YELLOW  = 0xFFFF00
    ORANGE  = 0xFF8000
    
    def __init__(self, config: Dict, database):
        """Initialize display"""
        self.config = config
        self.db = database
        
        # SAFETY: Never enable if not on Raspberry Pi hardware
        if not is_raspberry_pi():
            logger.warning("Display disabled - not running on Raspberry Pi hardware")
            self.enabled = False
        else:
            self.enabled = config['display']['enabled'] and DISPLAY_AVAILABLE
        # E-paper displays need 30+ seconds for full refresh - set minimum to 30
        refresh_config = config['display']['refresh_interval']
        self.refresh_interval = max(30, refresh_config) if refresh_config < 30 else refresh_config
        
        self.running = False
        self.update_thread = None
        self.epd = None
        self.updating = False  # Track if update is in progress to prevent overlapping refreshes
        
        # Display dimensions for Waveshare 2.13inch V4 (3-color)
        self.display_width = 250
        self.display_height = 122
        
        if self.enabled:
            self._init_display()
            logger.info("Display initialized")
        else:
            logger.info("Display disabled or not available")
    
    def _init_display(self):
        """Initialize Waveshare 2.13inch V4 display hardware"""
        try:
            # Initialize Waveshare EPD if available
            if WAVESHARE_AVAILABLE and epd_driver:
                try:
                    logger.info("Initializing Waveshare 2.13inch V4 display (3-color)...")
                    logger.info("Creating EPD object...")
                    self.epd = epd_driver.EPD()
                    logger.info("Calling EPD.init()...")
                    self.epd.init()
                    logger.info("Waveshare 2.13 V4 display initialized successfully")
                except RuntimeError as e:
                    # GPIO permission or hardware access issues
                    logger.error(f"GPIO/Hardware error initializing display: {e}", exc_info=True)
                    logger.error("Make sure the service is running as root and GPIO is accessible")
                    logger.warning("Display will operate in simulation mode (saving to /tmp/pendonn_display.png)")
                    self.epd = None
                except Exception as e:
                    logger.error(f"Failed to initialize Waveshare display: {e}", exc_info=True)
                    logger.warning("Display will operate in simulation mode (saving to /tmp/pendonn_display.png)")
                    self.epd = None
                    # Don't disable completely - allow simulation mode
            else:
                logger.warning("Waveshare library not available - display will use simulation mode")
            
            # Create image buffer (800x480 for Waveshare 7.3inch ACeP)
            self.image = Image.new('RGB', (self.display_width, self.display_height), self.WHITE)
            self.draw = ImageDraw.Draw(self.image)
            
            # Try to load better fonts (smaller sizes for 2.13 inch display)
            try:
                self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                self.font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
                self.font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
                self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
                self.font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8)
            except Exception as e:
                logger.warning(f"Could not load custom fonts: {e}")
                # Fallback to default font
                self.font_title = ImageFont.load_default()
                self.font_large = ImageFont.load_default()
                self.font_medium = ImageFont.load_default()
                self.font_small = ImageFont.load_default()
                self.font_tiny = ImageFont.load_default()
            
            logger.info(f"Display initialized: {self.display_width}x{self.display_height}")
        
        except Exception as e:
            logger.error(f"Display initialization error: {e}", exc_info=True)
            logger.warning("Display functionality disabled due to initialization failure")
            self.enabled = False
            self.epd = None
    
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
        
        # Clear display and put to sleep
        try:
            if self.epd:
                logger.info("Putting display to sleep...")
                self.epd.Clear()
                self.epd.sleep()
        except Exception as e:
            logger.error(f"Error during display shutdown: {e}")
        
        logger.info("Display updates stopped")
    
    def _update_loop(self):
        """Main display update loop"""
        while self.running:
            try:
                # Only update if not already updating (prevents overlapping refreshes)
                if not self.updating:
                    self.updating = True
                    self._render_display()
                    self.updating = False
                else:
                    logger.debug("Skipping display update - previous update still in progress")
                
                time.sleep(self.refresh_interval)
            
            except Exception as e:
                logger.error(f"Display update error: {e}", exc_info=True)
                self.updating = False
                time.sleep(10)  # Wait longer after error
    
    def _render_display(self):
        """Render current status to display with v1.1.0 design"""
        try:
            # Clear screen with white background
            self.draw.rectangle([(0, 0), (self.display_width, self.display_height)], fill=self.WHITE)
            
            # ========== HEADER SECTION ==========
            # Draw header background (dark bar at top)
            self.draw.rectangle([(0, 0), (self.display_width, 80)], fill=self.BLACK)
            
            # Title and version
            self.draw.text((20, 15), "PenDonn", font=self.font_title, fill=self.RED)
            self.draw.text((220, 35), "v1.1.0", font=self.font_small, fill=self.WHITE)
            
            # Get system IP
            try:
                ip_addr = self._get_ip_address()
                self.draw.text((self.display_width - 200, 15), f"IP: {ip_addr}", font=self.font_small, fill=self.GREEN)
            except:
                pass
            
            # Timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.draw.text((self.display_width - 200, 45), timestamp, font=self.font_tiny, fill=self.WHITE)
            
            # ========== STATISTICS SECTION ==========
            y_offset = 100
            
            # Get statistics
            stats = self.db.get_statistics()
            
            # Section title
            self.draw.text((20, y_offset), "PENETRATION TEST RESULTS", font=self.font_medium, fill=self.BLACK)
            self.draw.line([(20, y_offset + 30), (780, y_offset + 30)], fill=self.BLACK, width=2)
            y_offset += 50
            
            # Main statistics in 2 columns
            col1_x = 40
            col2_x = 420
            row_spacing = 55
            
            # Column 1
            self._draw_stat_box(col1_x, y_offset, "Networks", stats['networks_discovered'], self.BLUE)
            y_offset += row_spacing
            
            self._draw_stat_box(col1_x, y_offset, "Handshakes", stats['handshakes_captured'], self.GREEN)
            y_offset += row_spacing
            
            self._draw_stat_box(col1_x, y_offset, "Passwords", stats['passwords_cracked'], self.RED)
            
            # Column 2
            y_offset = 200  # Reset for second column
            
            self._draw_stat_box(col2_x, y_offset, "Scans", stats['scans_completed'], self.ORANGE)
            y_offset += row_spacing
            
            self._draw_stat_box(col2_x, y_offset, "Vulnerabilities", stats['vulnerabilities_found'], self.YELLOW)
            y_offset += row_spacing
            
            # Critical vulnerabilities (highlighted)
            critical_count = stats.get('critical_vulnerabilities', 0)
            if critical_count > 0:
                self._draw_stat_box(col2_x, y_offset, "CRITICAL", critical_count, self.RED, highlight=True)
            else:
                self._draw_stat_box(col2_x, y_offset, "Critical", 0, self.GREEN)
            
            # ========== STATUS SECTION ==========
            y_offset = 420
            
            # Draw status bar
            self.draw.rectangle([(10, y_offset), (790, y_offset + 50)], outline=self.BLACK, width=2)
            
            # Active processes
            status_text = "● ACTIVE"
            status_color = self.GREEN
            
            if stats['handshakes_pending'] > 0:
                status_text += f"  |  ⚡ Cracking: {stats['handshakes_pending']}"
                status_color = self.ORANGE
            else:
                status_text += "  |  ✓ Ready"
            
            self.draw.text((20, y_offset + 10), status_text, font=self.font_medium, fill=status_color)
            
            # Update physical display
            self._update_physical_display()
        
        except Exception as e:
            logger.error(f"Display render error: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _draw_stat_box(self, x: int, y: int, label: str, value: int, color: int, highlight: bool = False):
        """Draw a statistic box with icon-style design"""
        # Draw box outline if highlighted
        if highlight:
            self.draw.rectangle([(x - 5, y - 5), (x + 320, y + 40)], outline=color, width=3)
        
        # Label
        self.draw.text((x, y), label.upper(), font=self.font_small, fill=self.BLACK)
        
        # Value (large and colored)
        value_str = str(value)
        self.draw.text((x + 250, y - 5), value_str, font=self.font_large, fill=color)
    
    def _get_ip_address(self) -> str:
        """Get the primary IP address of the system"""
        try:
            # Try to get IP from network interface
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            # Fallback to hostname resolution
            try:
                return socket.gethostbyname(socket.gethostname())
            except:
                return "N/A"
    
    def _draw_stat(self, x: int, y: int, label: str, value: int):
        """Draw a statistic on display (legacy method for compatibility)"""
        # Label
        self.draw.text((x, y), label, font=self.font_medium, fill=self.BLACK)
        
        # Value
        value_str = str(value)
        self.draw.text((x + 250, y), value_str, font=self.font_medium, fill=self.BLUE)
    
    def _update_physical_display(self):
        """Update physical Waveshare display hardware"""
        try:
            if self.epd and WAVESHARE_AVAILABLE:
                logger.debug("Updating physical display...")
                # Display the image on the e-paper
                self.epd.display(self.epd.getbuffer(self.image))
                logger.debug("Display updated successfully")
            else:
                # Save to file for debugging when hardware not available
                debug_path = '/tmp/pendonn_display.png'
                self.image.save(debug_path)
                logger.debug(f"Display image saved to {debug_path} (hardware not available)")
        except Exception as e:
            logger.error(f"Failed to update physical display: {e}")
    
    def _clear_display(self):
        """Clear the display"""
        try:
            if self.epd and WAVESHARE_AVAILABLE:
                logger.info("Clearing display...")
                self.epd.Clear()
            else:
                # Clear image buffer
                if hasattr(self, 'draw'):
                    self.draw.rectangle(
                        [(0, 0), (self.display_width, self.display_height)], 
                        fill=self.WHITE
                    )
                    self._update_physical_display()
        except Exception as e:
            logger.error(f"Display clear error: {e}")
    
    def show_message(self, message: str, duration: int = 3, message_type: str = "info"):
        """Show a temporary message with type-based coloring"""
        if not self.enabled:
            return
        
        try:
            # Clear screen
            self.draw.rectangle([(0, 0), (self.display_width, self.display_height)], fill=self.WHITE)
            
            # Choose color based on message type
            color_map = {
                'info': self.BLUE,
                'success': self.GREEN,
                'warning': self.ORANGE,
                'error': self.RED
            }
            msg_color = color_map.get(message_type, self.BLACK)
            
            # Draw border
            self.draw.rectangle([(20, 20), (780, 460)], outline=msg_color, width=4)
            
            # Draw message centered
            # Calculate text position (approximate centering)
            text_x = self.display_width // 2 - 150
            text_y = self.display_height // 2 - 30
            
            self.draw.text((text_x, text_y), message, font=self.font_large, fill=msg_color)
            
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
