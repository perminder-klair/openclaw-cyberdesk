"""
Raspberry Pi Display Backlight Controller
Handles screen brightness via /sys/class/backlight/
"""

import glob
from typing import Optional

from log import get_logger

logger = get_logger('backlight')

# Try to detect backlight device, fall back to mock for development
BACKLIGHT_PATH: Optional[str] = None
MOCK_MODE = True
MAX_BRIGHTNESS = 255

# Auto-detect backlight device
backlight_paths = glob.glob('/sys/class/backlight/*/brightness')
if backlight_paths:
    BACKLIGHT_PATH = backlight_paths[0].replace('/brightness', '')
    try:
        with open(f"{BACKLIGHT_PATH}/max_brightness", 'r') as f:
            MAX_BRIGHTNESS = int(f.read().strip())
        MOCK_MODE = False
        logger.info("Found device at %s, max brightness: %d", BACKLIGHT_PATH, MAX_BRIGHTNESS)
    except (IOError, ValueError) as e:
        logger.warning("Could not read max brightness: %s", e)
        MOCK_MODE = True

if MOCK_MODE:
    logger.warning("Running in mock mode - no backlight device available")


class BacklightController:
    def __init__(self):
        self.current_brightness = 100  # Percentage 0-100
        self._read_current_brightness()

    def _read_current_brightness(self):
        """Read current brightness from hardware"""
        if MOCK_MODE or not BACKLIGHT_PATH:
            return

        try:
            with open(f"{BACKLIGHT_PATH}/brightness", 'r') as f:
                raw_value = int(f.read().strip())
                self.current_brightness = round((raw_value / MAX_BRIGHTNESS) * 100)
        except (IOError, ValueError) as e:
            logger.error("Failed to read brightness: %s", e)

    def set_brightness(self, brightness: int):
        """Set screen brightness (0-100, min 10% to avoid black screen)"""
        brightness = max(10, min(100, int(brightness)))
        self.current_brightness = brightness

        if MOCK_MODE:
            logger.debug("Mock brightness: %d%%", brightness)
            return

        if not BACKLIGHT_PATH:
            return

        # Convert percentage to hardware value
        raw_value = round((brightness / 100) * MAX_BRIGHTNESS)

        try:
            with open(f"{BACKLIGHT_PATH}/brightness", 'w') as f:
                f.write(str(raw_value))
            logger.info("Set to %d%% (%d/%d)", brightness, raw_value, MAX_BRIGHTNESS)
        except IOError as e:
            logger.error("Failed to set brightness: %s", e)
            logger.error("Tip: Run with sudo or add udev rule for permissions")

    def get_brightness(self) -> int:
        """Get current brightness percentage"""
        return self.current_brightness

    def get_status(self) -> dict:
        """Get current backlight status"""
        return {
            "brightness": self.current_brightness,
            "online": not MOCK_MODE,
            "mock": MOCK_MODE,
            "device": BACKLIGHT_PATH,
        }


# Singleton instance
_controller: Optional[BacklightController] = None


def get_backlight_controller() -> BacklightController:
    global _controller
    if _controller is None:
        _controller = BacklightController()
    return _controller
