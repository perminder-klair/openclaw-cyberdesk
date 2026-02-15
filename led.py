"""
NeoPixel LED Controller for WS2812B strip
Handles color setting, animations (pulse, flash, fade, breathe)
"""

import time
import threading
from typing import Optional, Tuple

# Try to import rpi_ws281x, fall back to mock for development
try:
    from rpi_ws281x import PixelStrip, Color
    MOCK_MODE = False
except ImportError:
    MOCK_MODE = True
    print("[LED] Running in mock mode - rpi_ws281x not available")

# LED strip configuration
LED_COUNT = 8          # Number of LED pixels (NeoPixel Stick has 8)
LED_PIN = 10           # GPIO pin (SPI MOSI - GPIO10, frees GPIO18 for I2S audio)
LED_FREQ_HZ = 800000   # LED signal frequency in hertz
LED_DMA = 10           # DMA channel to use for generating signal
LED_BRIGHTNESS = 255   # Max brightness (0-255)
LED_INVERT = False     # True to invert the signal
LED_CHANNEL = 0        # PWM channel


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def wheel(pos: int) -> Tuple[int, int, int]:
    """Generate rainbow colors across 0-255 positions"""
    pos = pos % 256
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)


class LEDController:
    def __init__(self):
        self.current_color = "#000000"
        self.current_mode = "off"
        self.current_brightness = 0
        self.strip: Optional[PixelStrip] = None
        self.animation_thread: Optional[threading.Thread] = None
        self.stop_animation = threading.Event()

        if not MOCK_MODE:
            self._init_strip()

    def _init_strip(self):
        """Initialize the LED strip"""
        try:
            self.strip = PixelStrip(
                LED_COUNT, LED_PIN, LED_FREQ_HZ,
                LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
            )
            self.strip.begin()
            print(f"[LED] Initialized {LED_COUNT} LEDs on GPIO{LED_PIN}")
        except Exception as e:
            print(f"[LED] Failed to initialize strip: {e}")
            self.strip = None

    def _stop_current_animation(self):
        """Stop any running animation"""
        self.stop_animation.set()
        if self.animation_thread and self.animation_thread.is_alive():
            self.animation_thread.join(timeout=1)
        self.stop_animation.clear()

    def _set_all_pixels(self, r: int, g: int, b: int, brightness: float = 1.0):
        """Set all pixels to the same color with brightness adjustment"""
        if MOCK_MODE or not self.strip:
            return

        # Apply brightness
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)

        color = Color(r, g, b)
        for i in range(LED_COUNT):
            self.strip.setPixelColor(i, color)
        self.strip.show()

    def _set_pixel(self, i: int, r: int, g: int, b: int, brightness: float = 1.0):
        """Set a single pixel color with brightness adjustment"""
        if MOCK_MODE or not self.strip:
            return
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)
        self.strip.setPixelColor(i, Color(r, g, b))

    def _show(self):
        """Safely call strip.show() with MOCK_MODE check"""
        if MOCK_MODE or not self.strip:
            return
        self.strip.show()

    def _animation_pulse(self, r: int, g: int, b: int, brightness: float):
        """Pulsing animation - fades in and out"""
        while not self.stop_animation.is_set():
            # Fade in
            for i in range(0, 100, 5):
                if self.stop_animation.is_set():
                    return
                self._set_all_pixels(r, g, b, (i / 100) * brightness)
                time.sleep(0.05)
            # Fade out
            for i in range(100, 0, -5):
                if self.stop_animation.is_set():
                    return
                self._set_all_pixels(r, g, b, (i / 100) * brightness)
                time.sleep(0.05)

    def _animation_breathe(self, r: int, g: int, b: int, brightness: float):
        """Gentle breathing animation - slower than pulse"""
        while not self.stop_animation.is_set():
            # Breathe in (slower)
            for i in range(20, 100, 2):
                if self.stop_animation.is_set():
                    return
                self._set_all_pixels(r, g, b, (i / 100) * brightness)
                time.sleep(0.08)
            # Breathe out
            for i in range(100, 20, -2):
                if self.stop_animation.is_set():
                    return
                self._set_all_pixels(r, g, b, (i / 100) * brightness)
                time.sleep(0.08)

    def _animation_flash(self, r: int, g: int, b: int, brightness: float):
        """Flash 3 times then return to off"""
        for _ in range(3):
            if self.stop_animation.is_set():
                return
            self._set_all_pixels(r, g, b, brightness)
            time.sleep(0.2)
            self._set_all_pixels(0, 0, 0, 0)
            time.sleep(0.2)

    def _animation_fade(self, r: int, g: int, b: int, brightness: float):
        """Fade up from off to target brightness"""
        for i in range(0, 101, 2):
            if self.stop_animation.is_set():
                return
            self._set_all_pixels(r, g, b, (i / 100) * brightness)
            time.sleep(0.03)

    def _animation_rainbow(self, r: int, g: int, b: int, brightness: float):
        """Rotating rainbow across all pixels"""
        offset = 0
        while not self.stop_animation.is_set():
            for i in range(LED_COUNT):
                color = wheel((i * 256 // LED_COUNT + offset) % 256)
                self._set_pixel(i, color[0], color[1], color[2], brightness)
            self._show()
            offset = (offset + 5) % 256
            time.sleep(0.05)

    def _animation_disco(self, r: int, g: int, b: int, brightness: float):
        """Random color flashes on random pixels"""
        import random
        while not self.stop_animation.is_set():
            for i in range(LED_COUNT):
                if random.random() > 0.6:  # 40% chance to light each pixel
                    color = wheel(random.randint(0, 255))
                    self._set_pixel(i, color[0], color[1], color[2], brightness)
                else:
                    self._set_pixel(i, 0, 0, 0, 0)
            self._show()
            time.sleep(0.1)

    def _animation_chase(self, r: int, g: int, b: int, brightness: float):
        """Theater chase effect with input color"""
        pos = 0
        while not self.stop_animation.is_set():
            for i in range(LED_COUNT):
                if i == pos:
                    self._set_pixel(i, r, g, b, brightness)
                else:
                    self._set_pixel(i, r // 8, g // 8, b // 8, brightness * 0.2)
            self._show()
            pos = (pos + 1) % LED_COUNT
            time.sleep(0.08)

    def _animation_gradient(self, r: int, g: int, b: int, brightness: float):
        """Static gradient spread of the input color"""
        for i in range(LED_COUNT):
            factor = 0.3 + (0.7 * i / (LED_COUNT - 1))  # 30% to 100%
            self._set_pixel(i, int(r * factor), int(g * factor), int(b * factor), brightness)
        self._show()
        # Keep running to prevent mode switch issues
        while not self.stop_animation.is_set():
            time.sleep(0.5)

    def set_color(self, hex_color: str, mode: str = "static", brightness: int = 100):
        """
        Set LED color and mode

        Args:
            hex_color: Color in hex format (e.g., '#FFF4E0')
            mode: Animation mode ('static', 'pulse', 'flash', 'fade', 'breathe',
                  'rainbow', 'disco', 'chase', 'gradient', 'off')
            brightness: Brightness 0-100
        """
        self._stop_current_animation()

        self.current_color = hex_color
        self.current_mode = mode
        self.current_brightness = brightness

        r, g, b = hex_to_rgb(hex_color)
        brightness_factor = brightness / 100

        if MOCK_MODE:
            print(f"[LED Mock] Color: {hex_color}, Mode: {mode}, Brightness: {brightness}%")
            return

        if mode == "off":
            self._set_all_pixels(0, 0, 0, 0)
        elif mode == "static":
            self._set_all_pixels(r, g, b, brightness_factor)
        elif mode in ("pulse", "breathe", "flash", "fade", "rainbow", "disco", "chase", "gradient"):
            # Start animation in background thread
            animation_fn = {
                "pulse": self._animation_pulse,
                "breathe": self._animation_breathe,
                "flash": self._animation_flash,
                "fade": self._animation_fade,
                "rainbow": self._animation_rainbow,
                "disco": self._animation_disco,
                "chase": self._animation_chase,
                "gradient": self._animation_gradient,
            }[mode]

            self.animation_thread = threading.Thread(
                target=animation_fn,
                args=(r, g, b, brightness_factor),
                daemon=True
            )
            self.animation_thread.start()

    def get_status(self) -> dict:
        """Get current LED status"""
        return {
            "currentColor": self.current_color,
            "currentMode": self.current_mode,
            "currentBrightness": self.current_brightness,
            "online": True,
            "mock": MOCK_MODE,
        }

    def cleanup(self):
        """Clean up - turn off LEDs"""
        self._stop_current_animation()
        if self.strip:
            self._set_all_pixels(0, 0, 0, 0)


# Singleton instance
_controller: Optional[LEDController] = None

def get_controller() -> LEDController:
    global _controller
    if _controller is None:
        _controller = LEDController()
    return _controller
