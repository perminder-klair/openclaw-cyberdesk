"""
System Volume Controller
Handles audio volume via ALSA amixer for WM8960 Audio HAT
"""

import subprocess
import re
from typing import Optional, Tuple

# Try to detect WM8960 sound card
SOUND_CARD: Optional[int] = None
MOCK_MODE = True
DEVICE_NAME: Optional[str] = None

def _detect_wm8960_card() -> Tuple[Optional[int], Optional[str]]:
    """Auto-detect WM8960 sound card number"""
    try:
        result = subprocess.run(
            ['aplay', '-l'],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'wm8960' in line.lower():
                # Extract card number from "card N:"
                match = re.search(r'card (\d+):', line)
                if match:
                    card_num = int(match.group(1))
                    # Extract device name
                    name_match = re.search(r'card \d+: ([^[]+)', line)
                    device_name = name_match.group(1).strip() if name_match else 'WM8960'
                    return card_num, device_name
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        print(f"[Volume] Could not detect sound card: {e}")
    return None, None


# Auto-detect on module load
SOUND_CARD, DEVICE_NAME = _detect_wm8960_card()
if SOUND_CARD is not None:
    MOCK_MODE = False
    print(f"[Volume] Found WM8960 at card {SOUND_CARD}: {DEVICE_NAME}")
else:
    print("[Volume] Running in mock mode - no WM8960 device available")


class VolumeController:
    def __init__(self):
        self.current_volume = 100  # Percentage 0-100
        self.muted = False
        self._read_current_volume()

    def _run_amixer(self, args: list) -> Optional[str]:
        """Run amixer command and return output"""
        if MOCK_MODE or SOUND_CARD is None:
            return None
        try:
            cmd = ['amixer', '-c', str(SOUND_CARD)] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            print(f"[Volume] amixer command failed: {e}")
            return None

    def _parse_volume(self, output: str) -> Tuple[int, bool]:
        """Parse amixer output to get volume and mute state"""
        # Look for pattern like "[75%]" and "[on]" or "[off]"
        volume = 100
        muted = False

        volume_match = re.search(r'\[(\d+)%\]', output)
        if volume_match:
            volume = int(volume_match.group(1))

        mute_match = re.search(r'\[(on|off)\]', output)
        if mute_match:
            muted = mute_match.group(1) == 'off'

        return volume, muted

    def _read_current_volume(self):
        """Read current volume from hardware"""
        if MOCK_MODE:
            return

        output = self._run_amixer(['sget', 'Speaker'])
        if output:
            self.current_volume, self.muted = self._parse_volume(output)
            print(f"[Volume] Current: {self.current_volume}%, muted: {self.muted}")

    def set_volume(self, volume: int):
        """
        Set system volume

        Args:
            volume: Volume percentage 0-100
        """
        # Clamp to valid range
        volume = max(0, min(100, int(volume)))
        self.current_volume = volume

        if MOCK_MODE:
            print(f"[Volume Mock] Volume: {volume}%")
            return

        # Set both Speaker and Headphone for WM8960
        self._run_amixer(['sset', 'Speaker', f'{volume}%'])
        self._run_amixer(['sset', 'Headphone', f'{volume}%'])
        print(f"[Volume] Set to {volume}%")

    def set_muted(self, muted: bool):
        """
        Set mute state

        Args:
            muted: True to mute, False to unmute
        """
        self.muted = muted

        if MOCK_MODE:
            print(f"[Volume Mock] Muted: {muted}")
            return

        state = 'off' if muted else 'on'
        self._run_amixer(['sset', 'Speaker', state])
        self._run_amixer(['sset', 'Headphone', state])
        print(f"[Volume] Muted: {muted}")

    def get_volume(self) -> int:
        """Get current volume percentage"""
        return self.current_volume

    def is_muted(self) -> bool:
        """Get current mute state"""
        return self.muted

    def get_status(self) -> dict:
        """Get current volume status"""
        return {
            "volume": self.current_volume,
            "muted": self.muted,
            "device": DEVICE_NAME,
            "online": not MOCK_MODE,
            "mock": MOCK_MODE,
            "card": SOUND_CARD,
        }


# Singleton instance
_controller: Optional[VolumeController] = None


def get_volume_controller() -> VolumeController:
    global _controller
    if _controller is None:
        _controller = VolumeController()
    return _controller
