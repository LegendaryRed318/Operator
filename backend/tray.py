#!/usr/bin/env python3
"""
tray.py - System tray icon for Operator.
"""

import os
import sys
import time
import webbrowser
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

# Paths
ALERT_FLAG_PATH = Path("C:/Projects/Operator/logs/alert.flag")

ICON_SIZE = 64

# Colors
COLOR_GREY = (128, 128, 128)
COLOR_RED = (220, 53, 69)
COLOR_DARK = (30, 30, 30)


class OperatorTray:
    def __init__(self):
        self.icon = None
        self.current_color = "grey"
        self.running = True
        self.alert_thread = None
    
    def create_icon_image(self, color):
        """Create a simple square icon with the given color."""
        image = Image.new('RGBA', (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw rounded rectangle background
        padding = 4
        draw.rounded_rectangle(
            [padding, padding, ICON_SIZE - padding, ICON_SIZE - padding],
            radius=12,
            fill=color
        )
        
        # Draw inner highlight
        inner_padding = 8
        draw.rounded_rectangle(
            [inner_padding, inner_padding, ICON_SIZE - inner_padding, ICON_SIZE - inner_padding],
            radius=8,
            fill=tuple(min(c + 40, 255) for c in color)
        )
        
        # Draw letter "O" in center (compatible with older Pillow versions)
        try:
            # Calculate position to center the text (approximately)
            text = "O"
            x = (ICON_SIZE - 20) // 2
            y = (ICON_SIZE - 24) // 2
            draw.text((x, y), text, fill=COLOR_DARK)
        except Exception:
            pass  # Skip text if font rendering fails
        
        return image
    
    def create_grey_icon(self):
        return self.create_icon_image(COLOR_GREY)
    
    def create_red_icon(self):
        return self.create_icon_image(COLOR_RED)
    
    def open_dashboard(self):
        """Open the dashboard in default browser."""
        print(f"[TRAY] Opening dashboard at http://localhost:8081")
        webbrowser.open("http://localhost:8081")
    
    def quit_app(self):
        """Quit the tray application."""
        print("[TRAY] Quitting...")
        self.running = False
        if self.icon:
            self.icon.stop()
    
    def check_alerts(self):
        """Background thread that checks alert flag every 2 seconds."""
        while self.running:
            try:
                if ALERT_FLAG_PATH.exists():
                    with open(ALERT_FLAG_PATH, "r") as f:
                        content = f.read().strip()
                    
                    if content == "RED":
                        print("[TRAY] Alert detected! Changing icon to RED")
                        self.current_color = "red"
                        
                        # Update icon
                        if self.icon:
                            self.icon.icon = self.create_red_icon()
                        
                        # Reset flag
                        with open(ALERT_FLAG_PATH, "w") as f:
                            f.write("GREY")
                    
                    elif content == "GREY" and self.current_color != "grey":
                        print("[TRAY] Resetting icon to GREY")
                        self.current_color = "grey"
                        
                        if self.icon:
                            self.icon.icon = self.create_grey_icon()
                        
            except Exception as e:
                print(f"[TRAY ERROR] {e}")
            
            time.sleep(2)
    
    def run(self):
        """Start the tray icon."""
        print("[TRAY] Starting Operator system tray icon...")
        
        # Ensure alert flag file exists
        ALERT_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not ALERT_FLAG_PATH.exists():
            with open(ALERT_FLAG_PATH, "w") as f:
                f.write("GREY")
        
        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem("Open Dashboard", lambda: self.open_dashboard()),
            pystray.MenuItem("Quit", lambda: self.quit_app())
        )
        
        # Create initial grey icon
        icon_image = self.create_grey_icon()
        
        # Create and start icon
        self.icon = pystray.Icon(
            "Operator",
            icon_image,
            "Operator - Error Monitor",
            menu
        )
        
        # Start alert checking thread
        self.alert_thread = threading.Thread(target=self.check_alerts, daemon=True)
        self.alert_thread.start()
        
        print("[TRAY] Tray icon active. Right-click for menu.")
        print("[TRAY] Checking for alerts every 2 seconds...")
        
        # Run the icon (blocking)
        self.icon.run()
        
        # Cleanup
        self.running = False
        if self.alert_thread:
            self.alert_thread.join(timeout=1)
        
        print("[TRAY] Stopped.")


def main():
    tray = OperatorTray()
    tray.run()


if __name__ == "__main__":
    main()
