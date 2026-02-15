"""
Waveshare HMMD mmWave Radar Presence Detection
Communicates via UART to detect human presence
Supports both ASCII mode ("Range XXX") and binary mode (FD FC FB FA header)

Enhanced features:
- GPIO hybrid mode: OT2 pin for instant presence, UART for detailed data
- Motion type detection: moving vs stationary
- Posture tracking: alerts when too close for extended periods
- Debug mode: 16-gate energy data visualization
"""

import re
import threading
import time
from datetime import datetime
from typing import Optional, List

# Try to import serial, fall back to mock for development
try:
    import serial

    MOCK_MODE = False
except ImportError:
    MOCK_MODE = True
    print("[Presence] Running in mock mode - pyserial not available")

# Try to import GPIO, fall back if not on Raspberry Pi
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    print("[Presence] RPi.GPIO not available - GPIO features disabled")

# UART configuration for Waveshare HMMD mmWave Sensor
SERIAL_PORT = "/dev/ttyS0"  # UART0 on Raspberry Pi (GPIO14/15)
BAUD_RATE = 115200  # HMMD sensor baud rate

# Maximum distance (cm) to consider as "present" - ignore detections further away
MAX_PRESENCE_DISTANCE = 140  # 1.4 meter

# Zone thresholds for distance-based behavior
ZONE_NEAR = 50      # < 50cm = very close to screen
ZONE_MEDIUM = 100   # 50-100cm = normal desk distance
# > 100cm = far (leaning back/standing)

# GPIO configuration for OT2 presence output
GPIO_PIN_OT2 = 23  # GPIO23 (BCM numbering)

# Posture tracking
POSTURE_TOO_CLOSE_CM = 50  # Distance threshold for "too close"
POSTURE_ALERT_SECONDS = 300  # 5 minutes before alert

# Motion type byte position in binary frame
MOTION_TYPE_OFFSET = 8  # Byte offset for motion type
MOTION_TYPE_MOVING = 0x01
MOTION_TYPE_STATIONARY = 0x02

# Debug mode commands
DEBUG_MODE_ENABLE_CMD = bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0x62, 0x00, 0x04, 0x03, 0x02, 0x01])
DEBUG_MODE_DISABLE_CMD = bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0x63, 0x00, 0x04, 0x03, 0x02, 0x01])


class PresenceDetector:
    def __init__(self):
        self.is_present = False
        self.distance: Optional[float] = None
        self.last_seen = datetime.now()
        self.last_data_time = datetime.now()
        self.serial: Optional[serial.Serial] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.buffer = b""
        # Regex for ASCII mode: "Range XXX" where XXX is distance in cm
        self.ascii_pattern = re.compile(rb"Range\s+(\d+)")
        # Timeout for considering person absent (no data for 3 seconds)
        self.absent_timeout = 3.0

        # New: Motion type detection
        self.motion_type: str = "none"  # "moving" | "stationary" | "none"

        # New: GPIO hybrid mode
        self.gpio_available = False
        self.gpio_present = False

        # New: Posture tracking
        self.too_close_start: Optional[datetime] = None
        self.posture_alert_active = False

        # New: Debug mode (16-gate energy data)
        self.debug_mode = False
        self.gate_energies: List[int] = [0] * 16

        if not MOCK_MODE:
            self._init_serial()
            self._init_gpio()

    def _init_serial(self):
        """Initialize serial connection to HMMD sensor"""
        try:
            self.serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print(
                f"[Presence] Connected to HMMD sensor on {SERIAL_PORT} at {BAUD_RATE} baud"
            )
        except Exception as e:
            print(f"[Presence] Failed to open serial port: {e}")
            self.serial = None

    def _init_gpio(self):
        """Initialize GPIO for OT2 presence output pin (interrupt-driven)"""
        if not GPIO_AVAILABLE:
            print("[Presence] GPIO not available, using UART-only mode")
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(GPIO_PIN_OT2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.add_event_detect(
                GPIO_PIN_OT2,
                GPIO.BOTH,
                callback=self._gpio_callback,
                bouncetime=100
            )
            self.gpio_available = True
            self.gpio_present = GPIO.input(GPIO_PIN_OT2) == GPIO.HIGH
            print(f"[Presence] GPIO OT2 initialized on pin {GPIO_PIN_OT2}")
        except Exception as e:
            print(f"[Presence] GPIO init failed: {e}")
            self.gpio_available = False

    def _gpio_callback(self, channel):
        """Callback for GPIO edge detection - instant presence/absence"""
        if not GPIO_AVAILABLE:
            return
        self.gpio_present = GPIO.input(channel) == GPIO.HIGH
        if self.gpio_present:
            self.last_seen = datetime.now()

    def _parse_motion_type(self, frame: bytes) -> str:
        """Extract motion type from binary frame"""
        if len(frame) <= MOTION_TYPE_OFFSET:
            return "none"
        motion_byte = frame[MOTION_TYPE_OFFSET]
        if motion_byte == MOTION_TYPE_MOVING:
            return "moving"
        elif motion_byte == MOTION_TYPE_STATIONARY:
            return "stationary"
        return "none"

    def _parse_gate_energies(self, frame: bytes) -> List[int]:
        """Parse per-gate energy values from debug frame (16 gates x 70cm each)"""
        energies = []
        # Gate data starts after header, varies by frame type
        gate_data_start = 14
        for i in range(16):
            offset = gate_data_start + (i * 2)
            if len(frame) > offset + 1:
                energy = frame[offset] | (frame[offset + 1] << 8)
                energies.append(min(energy, 1000))  # Cap at 1000
            else:
                energies.append(0)
        return energies

    def _update_posture_tracking(self):
        """Track prolonged too-close periods and trigger alert after threshold"""
        if self.is_present and self.distance is not None and self.distance < POSTURE_TOO_CLOSE_CM:
            if self.too_close_start is None:
                self.too_close_start = datetime.now()
            else:
                elapsed = (datetime.now() - self.too_close_start).total_seconds()
                if elapsed >= POSTURE_ALERT_SECONDS and not self.posture_alert_active:
                    self.posture_alert_active = True
                    print(f"[Presence] Posture alert: too close for {elapsed:.0f}s")
        else:
            # Reset tracking when user moves back or leaves
            self.too_close_start = None
            self.posture_alert_active = False

    def enable_debug_mode(self) -> bool:
        """Switch sensor to debug mode for gate energy readings"""
        if MOCK_MODE:
            self.debug_mode = True
            # Generate mock gate energies
            import random
            self.gate_energies = [random.randint(0, 500) for _ in range(16)]
            return True

        if not self.serial:
            return False

        try:
            self.serial.write(DEBUG_MODE_ENABLE_CMD)
            self.debug_mode = True
            print("[Presence] Debug mode enabled")
            return True
        except Exception as e:
            print(f"[Presence] Failed to enable debug mode: {e}")
            return False

    def disable_debug_mode(self) -> bool:
        """Switch sensor back to normal mode"""
        if MOCK_MODE:
            self.debug_mode = False
            self.gate_energies = [0] * 16
            return True

        if not self.serial:
            return False

        try:
            self.serial.write(DEBUG_MODE_DISABLE_CMD)
            self.debug_mode = False
            self.gate_energies = [0] * 16
            print("[Presence] Debug mode disabled")
            return True
        except Exception as e:
            print(f"[Presence] Failed to disable debug mode: {e}")
            return False

    def dismiss_posture_alert(self):
        """Dismiss active posture alert and reset tracking"""
        self.posture_alert_active = False
        self.too_close_start = None

    def _parse_ascii(self, data: bytes) -> Optional[dict]:
        """
        Parse ASCII mode output: "Range XXX" where XXX is distance in cm
        When the sensor detects presence, it outputs distance readings.
        When no presence, it either outputs nothing or "Range 0"
        """
        match = self.ascii_pattern.search(data)
        if match:
            try:
                distance = int(match.group(1))
                # Only consider present if within max distance threshold
                is_present = 0 < distance <= MAX_PRESENCE_DISTANCE
                return {
                    "is_present": is_present,
                    "distance": distance,
                    "mode": "ascii",
                }
            except ValueError:
                pass
        return None

    def _parse_binary_frame(self, data: bytes) -> Optional[dict]:
        """
        Parse binary frame format with FD FC FB FA header
        Enhanced to extract motion type and gate energies in debug mode
        """
        try:
            # Try Normal Mode header first (FD FC FB FA)
            header_idx = data.find(b"\xfd\xfc\xfb\xfa")

            # Fall back to Report Mode header (F4 F3 F2 F1)
            if header_idx == -1:
                header_idx = data.find(b"\xf4\xf3\xf2\xf1")
                if header_idx == -1:
                    return None

            frame = data[header_idx:]
            if len(frame) < 14:
                return None

            # Target distance (2 bytes, little-endian, in cm)
            distance = None
            distance_pos = 11
            if len(frame) > distance_pos + 1:
                distance = frame[distance_pos] | (frame[distance_pos + 1] << 8)
                if distance > 1600:  # Max ~16 gates * 70cm
                    distance = None

            # Only consider present if within max distance threshold
            detection_byte_pos = 10
            if len(frame) > detection_byte_pos:
                detection_result = frame[detection_byte_pos]
                is_present = (
                    detection_result == 0x01
                    and distance is not None
                    and distance <= MAX_PRESENCE_DISTANCE
                )
            else:
                is_present = False

            # Extract motion type from frame
            motion_type = self._parse_motion_type(frame)

            # Parse gate energies if in debug mode
            gate_energies = None
            if self.debug_mode and len(frame) >= 46:  # Enough data for 16 gates
                gate_energies = self._parse_gate_energies(frame)

            return {
                "is_present": is_present,
                "distance": distance,
                "mode": "binary",
                "motion_type": motion_type,
                "gate_energies": gate_energies,
            }

        except Exception as e:
            print(f"[Presence] Binary parse error: {e}")
            return None

    def _parse_frame(self, data: bytes) -> Optional[dict]:
        """
        Parse sensor data - tries ASCII mode first, then binary mode
        """
        if len(data) < 4:
            return None

        # Try ASCII mode first (simpler format: "Range XXX")
        result = self._parse_ascii(data)
        if result:
            return result

        # Fall back to binary frame parsing
        return self._parse_binary_frame(data)

    def _read_loop(self):
        """Background thread that continuously reads presence data
        Uses GPIO hybrid mode: GPIO for instant presence, UART for details
        """
        while self.running and self.serial:
            try:
                # GPIO hybrid optimization: skip UART polling if GPIO says absent
                if self.gpio_available and not self.gpio_present:
                    self.is_present = False
                    self.distance = None
                    self.motion_type = "none"
                    self._update_posture_tracking()
                    time.sleep(0.5)  # Reduced polling when away
                    continue

                # Read available UART data
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    self.buffer += data

                    # Try to parse accumulated buffer
                    result = self._parse_frame(self.buffer)

                    if result:
                        self.last_data_time = datetime.now()
                        self.is_present = result["is_present"]
                        self.distance = result["distance"]
                        self.motion_type = result.get("motion_type", "none")

                        # Update gate energies if in debug mode
                        if self.debug_mode and result.get("gate_energies"):
                            self.gate_energies = result["gate_energies"]

                        if self.is_present:
                            self.last_seen = datetime.now()

                        # Update posture tracking
                        self._update_posture_tracking()

                        # Clear buffer after successful parse
                        self.buffer = b""
                    elif len(self.buffer) > 256:
                        # Prevent buffer overflow, keep last 128 bytes
                        self.buffer = self.buffer[-128:]

                # Check for absence timeout (no valid data for a while)
                time_since_data = (datetime.now() - self.last_data_time).total_seconds()
                if time_since_data > self.absent_timeout and self.is_present:
                    self.is_present = False
                    self.distance = None
                    self.motion_type = "none"

                time.sleep(0.1)  # 10Hz polling

            except Exception as e:
                print(f"[Presence] Read error: {e}")
                time.sleep(1)

    def start(self):
        """Start presence detection"""
        if MOCK_MODE:
            print("[Presence] Mock mode - simulating presence")
            self.is_present = True
            self.distance = 75  # ~75cm typical desk distance
            self.motion_type = "stationary"
            self.last_seen = datetime.now()
            self.gpio_available = False
            self.gpio_present = True
            return

        if self.serial:
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            print("[Presence] Detection started")

    def stop(self):
        """Stop presence detection"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.serial:
            self.serial.close()
        # Clean up GPIO
        if self.gpio_available and GPIO_AVAILABLE:
            try:
                GPIO.remove_event_detect(GPIO_PIN_OT2)
                GPIO.cleanup(GPIO_PIN_OT2)
            except Exception:
                pass
        print("[Presence] Detection stopped")

    def _get_zone(self) -> str:
        """Classify distance into presence zones for UI/behavior adaptation"""
        if not self.is_present or self.distance is None:
            return "away"
        if self.distance < ZONE_NEAR:
            return "near"
        if self.distance < ZONE_MEDIUM:
            return "medium"
        return "far"

    def get_status(self) -> dict:
        """Get current presence status with extended sensor data"""
        # Calculate too close duration
        too_close_duration = None
        if self.too_close_start:
            too_close_duration = (datetime.now() - self.too_close_start).total_seconds()

        return {
            # Existing fields
            "isPresent": self.is_present,
            "distance": self.distance,
            "zone": self._get_zone(),
            "lastSeen": self.last_seen.isoformat(),
            "sensorOnline": True,
            "mock": MOCK_MODE,
            # New fields
            "motionType": self.motion_type,
            "gpioAvailable": self.gpio_available,
            "gpioPresent": self.gpio_present,
            "postureAlert": self.posture_alert_active,
            "tooCloseDuration": too_close_duration,
            "debugMode": self.debug_mode,
            "gateEnergies": self.gate_energies if self.debug_mode else None,
        }

    def set_mock_presence(self, present: bool, distance: Optional[float] = None,
                          motion_type: str = "stationary"):
        """For testing - set mock presence state with motion type"""
        if MOCK_MODE:
            self.is_present = present
            self.distance = distance if distance is not None else (75 if present else None)
            self.motion_type = motion_type if present else "none"
            self.gpio_present = present
            if present:
                self.last_seen = datetime.now()
            self._update_posture_tracking()


# Singleton instance
_detector: Optional[PresenceDetector] = None


def get_detector() -> PresenceDetector:
    global _detector
    if _detector is None:
        _detector = PresenceDetector()
        _detector.start()
    return _detector
