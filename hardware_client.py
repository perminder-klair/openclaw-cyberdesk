"""
Hardware Server Client for OpenClaw CyberDeck DSI.
Communicates with the hardware server at localhost:5000 for:
- LED control (status indication)
- Presence detection (automatic backlight dimming)
- Brightness control
- Voice/TTS (optional)
"""

import threading
import time
from typing import Optional, Dict, Any, Callable
import requests
from dataclasses import dataclass
from enum import Enum

import config_dsi as config


class PresenceZone(Enum):
    """Presence detection zones."""
    NEAR = "near"         # < 50cm, at the display
    MEDIUM = "medium"     # 50-100cm, leaned back
    FAR = "far"           # >= 100cm, stepped away
    AWAY = "away"         # Not detected


@dataclass
class LEDState:
    """LED state representation."""
    r: int = 0
    g: int = 0
    b: int = 0
    mode: str = "static"  # static, pulse, flash
    duration: float = 0   # For flash/pulse duration


class HardwareClient:
    """
    Client for hardware server communication.
    Handles LED control, presence detection, and brightness management.
    """

    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.base_url = config.HARDWARE_SERVER["base_url"]
        self.timeout = config.HARDWARE_SERVER["timeout"]
        self.endpoints = config.HARDWARE_SERVER["endpoints"]

        # State tracking
        self._current_led = LEDState()
        self._current_brightness = 100
        self._presence_zone = PresenceZone.NEAR
        self._presence_running = False
        self._presence_thread: Optional[threading.Thread] = None

        # Callbacks
        self._on_presence_change: Optional[Callable[[PresenceZone], None]] = None

        # Lock for thread safety
        self._lock = threading.Lock()

    def set_presence_callback(self, callback: Callable[[PresenceZone], None]):
        """Set callback for presence changes."""
        self._on_presence_change = callback

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to hardware server."""
        if self.demo_mode:
            print(f"[Hardware] Demo: {method} {endpoint} {kwargs.get('json', {})}")
            return {"status": "ok"}

        url = f"{self.base_url}{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, timeout=self.timeout, **kwargs)
            elif method == "POST":
                response = requests.post(url, timeout=self.timeout, **kwargs)
            else:
                return None

            if response.status_code == 200:
                return response.json() if response.content else {"status": "ok"}
            else:
                # Parse JSON error responses (400, 409, etc.)
                try:
                    err = response.json()
                    print(f"[Hardware] Request failed ({response.status_code}): {err.get('error', 'unknown')}")
                except Exception:
                    print(f"[Hardware] Request failed: {response.status_code}")
                return None

        except requests.exceptions.ConnectionError:
            print(f"[Hardware] Connection error to {url}")
            return None
        except requests.exceptions.Timeout:
            print(f"[Hardware] Timeout connecting to {url}")
            return None
        except Exception as e:
            print(f"[Hardware] Request error: {e}")
            return None

    # === LED Control ===

    def set_led(self, r: int, g: int, b: int, mode: str = "static", duration: float = 0, ambient: bool = True):
        """
        Set LED color and mode.

        Args:
            r: Red (0-255)
            g: Green (0-255)
            b: Blue (0-255)
            mode: "static", "pulse", or "flash"
            duration: Duration for pulse/flash (seconds)
            ambient: If True, save as resting state on the hardware server
        """
        with self._lock:
            self._current_led = LEDState(r=r, g=g, b=b, mode=mode, duration=duration)

        color = f"#{r:02X}{g:02X}{b:02X}"
        data = {"color": color, "mode": mode, "ambient": ambient}
        if duration > 0:
            data["duration"] = duration

        self._request("POST", self.endpoints["led"], json=data)

    def set_led_state(self, state: str):
        """
        Set LED to predefined state (transient — does not save as ambient).

        Args:
            state: One of "idle", "working", "success", "error", "connected", "disconnected", "listening"
        """
        led_config = config.LED_STATES.get(state, config.LED_STATES["idle"])
        mode = "pulse" if state in ("working", "listening") else "static"
        duration = 1.0 if state in ("success", "error") else 0

        self.set_led(
            r=led_config["r"],
            g=led_config["g"],
            b=led_config["b"],
            mode=mode,
            duration=duration,
            ambient=False
        )

    def flash_led(self, r: int, g: int, b: int, duration: float = 0.5):
        """Flash LED briefly then return to previous state."""
        prev_led = self._current_led
        self.set_led(r, g, b, mode="flash", duration=duration)

        def restore():
            time.sleep(duration)
            self.set_led(prev_led.r, prev_led.g, prev_led.b, prev_led.mode)

        threading.Thread(target=restore, daemon=True).start()

    def restore_ambient_led(self):
        """Restore LED to the user's saved ambient (resting) state on the hardware server."""
        self._request("POST", self.endpoints["led_restore"])

    # === Brightness Control ===

    def set_brightness(self, level: int):
        """
        Set display backlight brightness.

        Args:
            level: Brightness level (10-100)
        """
        level = max(10, min(100, level))
        with self._lock:
            self._current_brightness = level

        self._request("POST", self.endpoints["brightness"], json={"brightness": level})

    def get_brightness(self) -> int:
        """Get current brightness level."""
        with self._lock:
            return self._current_brightness

    # === Presence Detection ===

    def get_presence(self) -> PresenceZone:
        """Get current presence zone."""
        response = self._request("GET", self.endpoints["presence"])
        if response:
            zone_str = response.get("zone", "away")
            try:
                return PresenceZone(zone_str)
            except ValueError:
                return PresenceZone.AWAY
        return PresenceZone.AWAY

    def start_presence_monitoring(self):
        """Start background presence monitoring."""
        if self._presence_running:
            return

        self._presence_running = True
        self._presence_thread = threading.Thread(
            target=self._presence_loop,
            name="PresenceMonitor",
            daemon=True
        )
        self._presence_thread.start()
        print("[Hardware] Presence monitoring started")

    def stop_presence_monitoring(self):
        """Stop presence monitoring."""
        self._presence_running = False
        if self._presence_thread:
            self._presence_thread.join(timeout=2.0)
            self._presence_thread = None
        print("[Hardware] Presence monitoring stopped")

    def _presence_loop(self):
        """Background loop for presence monitoring."""
        poll_interval = config.PRESENCE_BACKLIGHT["poll_interval"]

        while self._presence_running:
            try:
                new_zone = self.get_presence()

                with self._lock:
                    prev_zone = self._presence_zone
                    self._presence_zone = new_zone

                if new_zone != prev_zone:
                    self._handle_presence_change(new_zone)

            except Exception as e:
                print(f"[Hardware] Presence poll error: {e}")

            time.sleep(poll_interval)

    def _handle_presence_change(self, zone: PresenceZone):
        """Handle presence zone change."""
        print(f"[Hardware] Presence changed to: {zone.value}")

        # Adjust brightness based on presence
        backlight_cfg = config.PRESENCE_BACKLIGHT
        if zone == PresenceZone.NEAR:
            self.set_brightness(backlight_cfg["near_brightness"])
        elif zone == PresenceZone.MEDIUM:
            self.set_brightness(backlight_cfg["medium_brightness"])
        elif zone == PresenceZone.FAR:
            self.set_brightness(backlight_cfg["far_brightness"])
        else:  # AWAY
            self.set_brightness(backlight_cfg["away_brightness"])

        # Notify callback
        if self._on_presence_change:
            self._on_presence_change(zone)

    # === Voice/TTS ===

    def speak(self, text: str, priority: str = "normal"):
        """
        Speak text using TTS.

        Args:
            text: Text to speak
            priority: "high", "normal", or "low"
        """
        self._request("POST", self.endpoints["voice_speak"], json={
            "text": text,
            "priority": priority
        })

    def start_listening(self, mode: str = "assistant") -> bool:
        """Start voice recording via hardware server."""
        result = self._request("POST", self.endpoints["voice_listen"], json={"mode": mode})
        if result is None:
            return False
        if result.get("error"):
            print(f"[Hardware] Voice listen error: {result['error']}")
            return False
        return True

    def get_voice_status(self) -> Optional[Dict[str, Any]]:
        """Get current voice pipeline status. Returns {state, last_transcript, ...}."""
        return self._request("GET", self.endpoints["voice_status"])

    def cancel_listening(self) -> bool:
        """Cancel active voice recording."""
        result = self._request("POST", self.endpoints["voice_cancel"])
        return result is not None

    def clear_transcript(self) -> bool:
        """Clear the last transcript from hardware server."""
        result = self._request("POST", self.endpoints["voice_clear"])
        return result is not None

    # === Status ===

    def is_server_available(self) -> bool:
        """Check if hardware server is available."""
        if self.demo_mode:
            return True

        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=1.0
            )
            return response.status_code == 200
        except:
            return False

    def get_current_state(self) -> Dict[str, Any]:
        """Get current hardware state."""
        with self._lock:
            return {
                "led": {
                    "r": self._current_led.r,
                    "g": self._current_led.g,
                    "b": self._current_led.b,
                    "mode": self._current_led.mode,
                },
                "brightness": self._current_brightness,
                "presence": self._presence_zone.value,
                "server_available": self.is_server_available(),
            }

    # === Cleanup ===

    def cleanup(self):
        """Clean up resources."""
        self.stop_presence_monitoring()
        # Return LED to dim idle state
        self.set_led_state("idle")
        print("[Hardware] Cleanup complete")


# Convenience function
def create_hardware_client(demo_mode: bool = False) -> HardwareClient:
    """Create and return a hardware client instance."""
    client = HardwareClient(demo_mode=demo_mode)
    return client
