"""
Centralized configuration for Hardware Sidecar.
Loads .env and exposes all environment variables and constants.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# Load .env from dashboard directory (shared with Next.js dashboard)
_env_path = Path('/home/klair/Projects/dashboard/.env')
load_dotenv(_env_path)

# ============ Server ============
PORT = int(os.environ.get('PORT', 5000))
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

# ============ Audio / Voice ============
MOCK_AUDIO = os.environ.get('MOCK_AUDIO', 'false').lower() == 'true'
WHISPER_URL = os.environ.get('WHISPER_URL')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY')
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://localhost:3000')
SYNC_API_KEY = os.environ.get('SYNC_API_KEY', '')
AUDIO_DEVICE = os.environ.get('AUDIO_DEVICE')  # None = auto-detect
AUDIO_GAIN = float(os.environ.get('AUDIO_GAIN', '1.0'))
ENABLE_SPEEX_NOISE_SUPPRESSION = os.environ.get('ENABLE_SPEEX_NOISE_SUPPRESSION', 'false').lower() == 'true'

# Wake word settings
WAKE_WORD = os.environ.get('WAKE_WORD', 'hey_jarvis')
WAKE_WORD_THRESHOLD = float(os.environ.get('WAKE_WORD_THRESHOLD', '0.40'))
WAKE_WORD_DEBUG = os.environ.get('WAKE_WORD_DEBUG', 'false').lower() == 'true'
DISABLE_WAKE_WORD = os.environ.get('DISABLE_WAKE_WORD', 'false').lower() == 'true'

# Piper TTS
PIPER_VOICE = os.environ.get('PIPER_VOICE', 'en_US-lessac-medium')

# Audio constants
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.16  # 160ms = 2x80ms for optimal OWW frame alignment
COMMAND_TIMEOUT = 10.0  # Max seconds to listen for command
SILENCE_THRESHOLD = 0.01  # RMS threshold for silence detection
SILENCE_DURATION = 1.5  # Seconds of silence to end command
COMMAND_COOLDOWN = 5.0  # Seconds to wait after command before listening again
MAX_NOTES_DURATION = 120.0  # 2 min max for notes mode

# Model paths
MODELS_DIR = Path(__file__).parent / "models"

# ============ Presence ============
SERIAL_PORT = "/dev/ttyS0"
BAUD_RATE = 115200
MAX_PRESENCE_DISTANCE = 140  # cm
ZONE_NEAR = 50  # cm
ZONE_MEDIUM = 100  # cm
GPIO_PIN_OT2 = 23  # BCM numbering
POSTURE_TOO_CLOSE_CM = 50
POSTURE_ALERT_SECONDS = 300  # 5 minutes

# ============ LED ============
LED_COUNT = 8
LED_PIN = 10  # GPIO10 (SPI MOSI)
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False
LED_CHANNEL = 0
