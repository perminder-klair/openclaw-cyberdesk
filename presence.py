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

import random
import re
import threading
import time
from datetime import datetime
from typing import Optional, List

from config import (
    SERIAL_PORT, BAUD_RATE, MAX_PRESENCE_DISTANCE,
    ZONE_NEAR, ZONE_MEDIUM, GPIO_PIN_OT2,
    POSTURE_TOO_CLOSE_CM, POSTURE_ALERT_SECONDS,
)
from log import get_logger

logger = get_logger('presence')

# Try to import serial, fall back to mock for development
try:
    import serial
    MOCK_MODE = False
except ImportError:
    MOCK_MODE = True
    logger.warning("Running in mock mode - pyserial not available")

# Try to import GPIO, fall back if not on Raspberry Pi
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    logger.warning("RPi.GPIO not available - GPIO features disabled")

# Motion type byte position in binary frame
MOTION_TYPE_OFFSET = 8
MOTION_TYPE_MOVING = 0x01
MOTION_TYPE_STATIONARY = 0x02

# Debug mode commands
DEBUG_MODE_ENABLE_CMD = bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0x62, 0x00, 0x04, 0x03, 0x02, 0x01])
DEBUG_MODE_DISABLE_CMD = bytes([0xFD, 0xFC, 0xFB, 0xFA, 0x02, 0x00, 0x63, 0x00, 0x04, 0x03, 0x02, 0x01])

# Module-level compiled regex
_ASCII_PATTERN = re.compile(rb"Range\s+(\d+)")


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
        # Timeout for considering person absent (no data for 3 seconds)
        self.absent_timeout = 3.0

        # Motion type detection
        self.motion_type: str = "none"  # "moving" | "stationary" | "none"

        # GPIO hybrid mode
        self.gpio_available = False
        self.gpio_present = False

        # Posture tracking
        self.too_close_start: Optional[datetime] = None
        self.posture_alert_active = False

        # Debug mode (16-gate energy data)
        self.debug_mode = False
        self.gate_energies: List[int] = [0] * 16

        if not MOCK_MODE:
            self._init_serial()
            self._init_gpio()

    def _init_serial(self):
        """Initialize serial connection to HMMD sensor"""
        try:
            self.serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            logger.info("Connected to HMMD sensor on %s at %d baud", SERIAL_PORT, BAUD_RATE)
        except Exception as e:
            logger.error("Failed to open serial port: %s", e)
            self.serial = None

    def _init_gpio(self):
        """Initialize GPIO for OT2 presence output pin (interrupt-driven)"""
        if not GPIO_AVAILABLE:
            logger.info("GPIO not available, using UART-only mode")
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
            logger.info("GPIO OT2 initialized on pin %d", GPIO_PIN_OT2)
        except Exception as e:
            logger.error("GPIO init failed: %s", e)
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
        gate_data_start = 14
        for i in range(16):
            offset = gate_data_start + (i * 2)
            if len(frame) > offset + 1:
                energy = frame[offset] | (frame[offset + 1] << 8)
                energies.append(min(energy, 1000))
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
                    logger.warning("Posture alert: too close for %.0fs", elapsed)
        else:
            self.too_close_start = None
            self.posture_alert_active = False

    def enable_debug_mode(self) -> bool:
        """Switch sensor to debug mode for gate energy readings"""
        if MOCK_MODE:
            self.debug_mode = True
            self.gate_energies = [random.randint(0, 500) for _ in range(16)]
            return True

        if not self.serial:
            return False

        try:
            self.serial.write(DEBUG_MODE_ENABLE_CMD)
            self.debug_mode = True
            logger.info("Debug mode enabled")
            return True
        except Exception as e:
            logger.error("Failed to enable debug mode: %s", e)
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
            logger.info("Debug mode disabled")
            return True
        except Exception as e:
            logger.error("Failed to disable debug mode: %s", e)
            return False

    def dismiss_posture_alert(self):
        """Dismiss active posture alert and reset tracking"""
        self.posture_alert_active = False
        self.too_close_start = None

    def _parse_ascii(self, data: bytes) -> Optional[dict]:
        """Parse ASCII mode output: "Range XXX" where XXX is distance in cm"""
        match = _ASCII_PATTERN.search(data)
        if match:
            try:
                distance = int(match.group(1))
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
        """Parse binary frame format with FD FC FB FA header"""
        try:
            header_idx = data.find(b"\xfd\xfc\xfb\xfa")

            if header_idx == -1:
                header_idx = data.find(b"\xf4\xf3\xf2\xf1")
                if header_idx == -1:
                    return None

            frame = data[header_idx:]
            if len(frame) < 14:
                return None

            distance = None
            distance_pos = 11
            if len(frame) > distance_pos + 1:
                distance = frame[distance_pos] | (frame[distance_pos + 1] << 8)
                if distance > 1600:
                    distance = None

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

            motion_type = self._parse_motion_type(frame)

            gate_energies = None
            if self.debug_mode and len(frame) >= 46:
                gate_energies = self._parse_gate_energies(frame)

            return {
                "is_present": is_present,
                "distance": distance,
                "mode": "binary",
                "motion_type": motion_type,
                "gate_energies": gate_energies,
            }

        except Exception as e:
            logger.error("Binary parse error: %s", e)
            return None

    def _parse_frame(self, data: bytes) -> Optional[dict]:
        """Parse sensor data - tries ASCII mode first, then binary mode"""
        if len(data) < 4:
            return None

        result = self._parse_ascii(data)
        if result:
            return result

        return self._parse_binary_frame(data)

    def _read_loop(self):
        """Background thread that continuously reads presence data"""
        while self.running and self.serial:
            try:
                if self.gpio_available and not self.gpio_present:
                    self.is_present = False
                    self.distance = None
                    self.motion_type = "none"
                    self._update_posture_tracking()
                    time.sleep(0.5)
                    continue

                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    self.buffer += data

                    result = self._parse_frame(self.buffer)

                    if result:
                        self.last_data_time = datetime.now()
                        self.is_present = result["is_present"]
                        self.distance = result["distance"]
                        self.motion_type = result.get("motion_type", "none")

                        if self.debug_mode and result.get("gate_energies"):
                            self.gate_energies = result["gate_energies"]

                        if self.is_present:
                            self.last_seen = datetime.now()

                        self._update_posture_tracking()
                        self.buffer = b""
                    elif len(self.buffer) > 256:
                        self.buffer = self.buffer[-128:]

                time_since_data = (datetime.now() - self.last_data_time).total_seconds()
                if time_since_data > self.absent_timeout and self.is_present:
                    self.is_present = False
                    self.distance = None
                    self.motion_type = "none"

                time.sleep(0.1)

            except Exception as e:
                logger.error("Read error: %s", e, exc_info=True)
                time.sleep(1)

    def start(self):
        """Start presence detection"""
        if MOCK_MODE:
            logger.info("Mock mode - simulating presence")
            self.is_present = True
            self.distance = 75
            self.motion_type = "stationary"
            self.last_seen = datetime.now()
            self.gpio_available = False
            self.gpio_present = True
            return

        if self.serial:
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            logger.info("Detection started")

    def stop(self):
        """Stop presence detection"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.serial:
            self.serial.close()
        if self.gpio_available and GPIO_AVAILABLE:
            try:
                GPIO.remove_event_detect(GPIO_PIN_OT2)
                GPIO.cleanup(GPIO_PIN_OT2)
            except Exception:
                pass
        logger.info("Detection stopped")

    def _get_zone(self) -> str:
        """Classify distance into presence zones"""
        if not self.is_present or self.distance is None:
            return "away"
        if self.distance < ZONE_NEAR:
            return "near"
        if self.distance < ZONE_MEDIUM:
            return "medium"
        return "far"

    def get_status(self) -> dict:
        """Get current presence status with extended sensor data"""
        too_close_duration = None
        if self.too_close_start:
            too_close_duration = (datetime.now() - self.too_close_start).total_seconds()

        return {
            "is_present": self.is_present,
            "distance": self.distance,
            "zone": self._get_zone(),
            "last_seen": self.last_seen.isoformat(),
            "sensor_online": True,
            "mock": MOCK_MODE,
            "motion_type": self.motion_type,
            "gpio_available": self.gpio_available,
            "gpio_present": self.gpio_present,
            "posture_alert": self.posture_alert_active,
            "too_close_duration": too_close_duration,
            "debug_mode": self.debug_mode,
            "gate_energies": self.gate_energies if self.debug_mode else None,
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
