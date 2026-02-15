"""
Audio Controller for Voice Commands
Handles wake word detection (OpenWakeWord), STT (ElevenLabs API), TTS (Piper), and audio I/O
"""

import os
import re
import time
import wave
import threading
import tempfile
from typing import Optional, Callable
from pathlib import Path

from config import (
    MOCK_AUDIO, WHISPER_URL, ELEVENLABS_API_KEY,
    DASHBOARD_URL, SYNC_API_KEY, AUDIO_DEVICE as AUDIO_DEVICE_ENV,
    AUDIO_GAIN, ENABLE_SPEEX_NOISE_SUPPRESSION,
    WAKE_WORD, WAKE_WORD_THRESHOLD, WAKE_WORD_DEBUG, DISABLE_WAKE_WORD,
    PIPER_VOICE, SAMPLE_RATE, CHANNELS, CHUNK_DURATION,
    COMMAND_TIMEOUT, SILENCE_THRESHOLD, SILENCE_DURATION,
    COMMAND_COOLDOWN, MAX_NOTES_DURATION, MODELS_DIR,
)
from log import get_logger

logger = get_logger('audio')

# Try to import audio dependencies, fall back to mock for development
try:
    import numpy as np
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    logger.warning("sounddevice/numpy not available - running in mock mode")

# Wake word detection
try:
    from openwakeword.model import Model as WakeWordModel
    WAKEWORD_AVAILABLE = True
except ImportError:
    WAKEWORD_AVAILABLE = False
    logger.warning("openwakeword not available - wake word disabled")

# Speech-to-text via Whisper API (self-hosted) or ElevenLabs fallback
import requests

# Text-to-speech
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logger.warning("piper-tts not available - TTS disabled")

# Determine mock mode
MOCK_MODE = MOCK_AUDIO or not AUDIO_AVAILABLE

# Module-level compiled wake word cleanup patterns
_WAKE_WORD_PATTERNS = [
    re.compile(r'^hey,?\s*jarvis[.,]?\s*', re.IGNORECASE),
    re.compile(r'^hi,?\s*jarvis[.,]?\s*', re.IGNORECASE),
    re.compile(r'^okay,?\s*jarvis[.,]?\s*', re.IGNORECASE),
]


def _detect_wm8960_device() -> Optional[str]:
    """Auto-detect WM8960 audio device for sounddevice"""
    if not AUDIO_AVAILABLE:
        return None
    try:
        for device in sd.query_devices():
            if 'wm8960' in device['name'].lower():
                logger.info("Auto-detected WM8960: %s", device['name'])
                return device['name']
    except Exception as e:
        logger.warning("Device detection error: %s", e)
    return None

# Use env var if set, otherwise auto-detect WM8960
AUDIO_DEVICE = AUDIO_DEVICE_ENV or _detect_wm8960_device()

# Voice states
VOICE_STATES = {
    'idle': 'Waiting for wake word',
    'listening': 'Listening for command',
    'processing': 'Processing speech',
    'speaking': 'Playing audio response',
}


class AudioController:
    """
    Handles all audio processing: wake word detection, STT, TTS, and playback.
    Follows singleton pattern matching led.py and presence.py.
    """

    def __init__(self):
        self._state_lock = threading.Lock()

        self.state = 'idle'
        self.last_transcript: Optional[str] = None
        self.error: Optional[str] = None
        self.enabled = True
        self.running = False
        self.tts_volume = 100  # TTS volume percentage 0-100

        # Thread management
        self.listen_thread: Optional[threading.Thread] = None
        self.speak_lock = threading.Lock()  # Only one TTS at a time
        self.stop_event = threading.Event()
        self.manual_listen_event = threading.Event()
        self.cancel_event = threading.Event()
        self.stop_recording_event = threading.Event()
        self.recording_mode = 'assistant'
        self.tts_playing = False
        self._tts_just_ended = False
        self.detection_paused = False

        # Callback for notifying frontend of state changes
        self.on_state_change: Optional[Callable[[dict], None]] = None

        # Cooldown tracking to prevent cascade triggers
        self.last_command_time: float = 0

        # Rolling detection window for more reliable wake word triggering
        self.detection_history: list[float] = []

        # Initialize components
        self._init_models()

    def _init_models(self):
        """Initialize AI models"""
        self.wakeword_model = None
        self.piper_voice = None

        if MOCK_MODE:
            logger.info("Running in mock mode")
            return

        # Wake word model
        if WAKEWORD_AVAILABLE:
            try:
                import openwakeword
                oww_dir = Path(openwakeword.__file__).parent
                model_path = oww_dir / "resources" / "models" / f"{WAKE_WORD}_v0.1.onnx"

                if model_path.exists():
                    self.wakeword_model = WakeWordModel(
                        wakeword_model_paths=[str(model_path)],
                        enable_speex_noise_suppression=ENABLE_SPEEX_NOISE_SUPPRESSION,
                    )
                    logger.info("Wake word model loaded: %s (speex=%s)", WAKE_WORD, ENABLE_SPEEX_NOISE_SUPPRESSION)
                else:
                    logger.warning("Wake word model not found: %s", model_path)
            except Exception as e:
                logger.error("Failed to load wake word model: %s", e)

        # STT via Whisper API (preferred) or ElevenLabs fallback
        if WHISPER_URL:
            logger.info("Whisper STT API configured: %s", WHISPER_URL)
        elif ELEVENLABS_API_KEY:
            logger.info("ElevenLabs STT API configured (fallback)")
        else:
            logger.warning("No WHISPER_URL or ELEVENLABS_API_KEY - STT disabled")

        # Piper TTS
        if PIPER_AVAILABLE:
            try:
                voice_path = MODELS_DIR / f"{PIPER_VOICE}.onnx"
                config_path = MODELS_DIR / f"{PIPER_VOICE}.onnx.json"

                if voice_path.exists():
                    self.piper_voice = PiperVoice.load(str(voice_path), str(config_path))
                    logger.info("Piper voice loaded: %s", PIPER_VOICE)
                else:
                    logger.warning("Piper voice not found at %s", voice_path)
            except Exception as e:
                logger.error("Failed to load Piper voice: %s", e)

    def _set_state(self, state: str):
        """Update state and notify listeners"""
        with self._state_lock:
            self.state = state
        if self.on_state_change:
            try:
                self.on_state_change(self.get_status())
            except Exception as e:
                logger.error("State change callback error: %s", e)
        self._notify_dashboard(state)

    def _notify_dashboard(self, state: str):
        """POST state change to dashboard webhook (non-blocking)"""
        def send():
            try:
                headers = {'Content-Type': 'application/json'}
                if SYNC_API_KEY:
                    headers['Authorization'] = f'Bearer {SYNC_API_KEY}'
                requests.post(
                    f'{DASHBOARD_URL}/api/sync/voice',
                    json={'state': state},
                    headers=headers,
                    timeout=2
                )
            except Exception:
                pass  # Fire-and-forget
        threading.Thread(target=send, daemon=True).start()

    def start(self):
        """Start wake word detection loop"""
        with self._state_lock:
            if self.running:
                return
            self.running = True
            self.enabled = True

        self.stop_event.clear()

        self.listen_thread = threading.Thread(
            target=self._wake_word_loop,
            daemon=True
        )
        self.listen_thread.start()
        if DISABLE_WAKE_WORD:
            logger.info("Audio loop started (wake word DISABLED, manual trigger only)")
        else:
            logger.info("Wake word detection started")

    def stop(self):
        """Stop wake word detection"""
        with self._state_lock:
            self.running = False
            self.enabled = False
        self.stop_event.set()

        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=2)

        self._set_state('idle')
        logger.info("Wake word detection stopped")

    def pause_detection(self):
        """Pause wake word detection (called when frontend TTS starts)"""
        with self._state_lock:
            self.detection_paused = True
        logger.debug("Detection paused for frontend TTS")

    def resume_detection(self):
        """Resume wake word detection (called when frontend TTS ends)"""
        with self._state_lock:
            self._tts_just_ended = True
            self.detection_paused = False
            self.last_command_time = time.time()
        logger.debug("Detection resumed after frontend TTS")

    def cancel_listening(self):
        """Cancel current listening/processing operation"""
        with self._state_lock:
            if self.state in ('listening', 'processing'):
                self.cancel_event.set()
                self.state = 'idle'
                self.last_transcript = None
                logger.info("Listening cancelled")

    def stop_recording(self):
        """Stop recording but proceed to transcription (for notes mode)"""
        with self._state_lock:
            if self.state == 'listening':
                self.stop_recording_event.set()
                logger.debug("Stop recording requested")

    def clear_transcript(self):
        """Clear the last transcript (thread-safe)"""
        with self._state_lock:
            self.last_transcript = None

    def _wake_word_loop(self):
        """Main loop for wake word detection"""
        logger.info("Wake word loop started (MOCK_MODE=%s)", MOCK_MODE)

        if MOCK_MODE:
            while self.running and not self.stop_event.is_set():
                time.sleep(0.5)
            return

        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)
        logger.debug("Opening audio stream (chunk_size=%d)...", chunk_size)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='float32',
                blocksize=chunk_size,
                device=AUDIO_DEVICE
            ) as stream:
                logger.info("Listening for wake word (device=%s)...", AUDIO_DEVICE)

                while self.running and not self.stop_event.is_set():
                    with self._state_lock:
                        current_state = self.state
                        tts_playing = self.tts_playing
                        paused = self.detection_paused
                        tts_just_ended = self._tts_just_ended

                    if current_state != 'idle' or tts_playing or paused:
                        time.sleep(0.1)
                        continue

                    # Clear mic buffer after TTS ends
                    if tts_just_ended:
                        with self._state_lock:
                            self._tts_just_ended = False
                        try:
                            stream.read(int(SAMPLE_RATE * 1.0))
                            logger.debug("Cleared mic buffer after TTS")
                        except Exception:
                            pass
                        continue

                    # Skip during cooldown
                    with self._state_lock:
                        last_cmd_time = self.last_command_time
                    if time.time() - last_cmd_time < COMMAND_COOLDOWN:
                        time.sleep(0.1)
                        continue

                    # Check for manual listen trigger
                    if self.manual_listen_event.is_set():
                        self.manual_listen_event.clear()
                        logger.debug("Manual listen triggered via wake word stream")
                        self._on_wake_word_detected(stream)
                        continue

                    # Read audio chunk
                    audio_chunk, _ = stream.read(chunk_size)
                    audio_chunk = audio_chunk.flatten()

                    # Check for wake word
                    if not DISABLE_WAKE_WORD and self._detect_wake_word(audio_chunk):
                        self._on_wake_word_detected(stream)

        except Exception as e:
            with self._state_lock:
                self.error = str(e)
            logger.error("Wake word loop error: %s", e, exc_info=True)

    def _detect_wake_word(self, audio_chunk: 'np.ndarray') -> bool:
        """Check if audio chunk contains wake word"""
        if not self.wakeword_model:
            return False

        try:
            if AUDIO_GAIN != 1.0:
                audio_chunk = audio_chunk * AUDIO_GAIN
                audio_chunk = np.clip(audio_chunk, -1.0, 1.0)

            audio_int16 = (audio_chunk * 32767).astype('int16')
            prediction = self.wakeword_model.predict(audio_int16)

            for ww_name, score in prediction.items():
                if WAKE_WORD_DEBUG and score > 0.3:
                    logger.debug("Wake word score %s: %.2f", ww_name, score)

                self.detection_history.append(score)
                self.detection_history = self.detection_history[-5:]

                if score > WAKE_WORD_THRESHOLD:
                    logger.info("Wake word detected: %s (score: %.2f)", ww_name, score)
                    self.detection_history = []
                    return True

                if len(self.detection_history) >= 3:
                    avg = sum(self.detection_history[-3:]) / 3
                    if avg > WAKE_WORD_THRESHOLD * 0.8:
                        logger.info("Wake word detected (rolling avg): %s (avg: %.2f)", ww_name, avg)
                        self.detection_history = []
                        return True

        except Exception as e:
            logger.error("Wake word detection error: %s", e)

        return False

    def _is_valid_transcript(self, text: str) -> bool:
        """Check if transcript is actual speech, not noise descriptions"""
        if not text:
            return False
        if text.startswith('(') and text.endswith(')'):
            return False
        if len(text.strip()) < 3:
            return False
        return True

    def _clean_transcript(self, text: str) -> str:
        """Remove wake word from start of transcript"""
        cleaned = text
        for pattern in _WAKE_WORD_PATTERNS:
            cleaned = pattern.sub('', cleaned)
        return cleaned.strip()

    def _on_wake_word_detected(self, stream):
        """Handle wake word detection - record and transcribe command"""
        self._set_state('listening')
        with self._state_lock:
            mode = self.recording_mode
        logger.info("Wake word triggered - now listening (mode=%s)...", mode)

        try:
            if mode == 'notes':
                audio_data = self._record_until_stopped(stream)
            else:
                audio_data = self._record_until_silence(stream)

            if audio_data is None:
                logger.debug("No audio recorded")
                self._set_state('idle')
                return

            duration = len(audio_data) / SAMPLE_RATE
            logger.info("Recorded %.2fs of audio", duration)

            if duration < 0.5:
                logger.debug("Recording too short, ignoring")
                self._set_state('idle')
                return

            if self.cancel_event.is_set():
                self.cancel_event.clear()
                logger.info("Cancelled before transcription")
                self._set_state('idle')
                return

            self._set_state('processing')
            logger.info("Transcribing with %s...", 'Whisper' if WHISPER_URL else 'ElevenLabs')
            transcript = self._transcribe(audio_data)

            logger.debug("Raw transcript: '%s'", transcript)

            if transcript:
                transcript = self._clean_transcript(transcript)

                if self._is_valid_transcript(transcript):
                    with self._state_lock:
                        self.last_transcript = transcript
                    logger.info("Transcript ready: '%s'", transcript)
                else:
                    logger.debug("Filtered noise transcript: '%s'", transcript)
                    with self._state_lock:
                        self.last_transcript = None
            else:
                logger.debug("No transcript returned")
                with self._state_lock:
                    self.last_transcript = None

        except Exception as e:
            with self._state_lock:
                self.error = str(e)
            logger.error("Command processing error: %s", e, exc_info=True)

        finally:
            try:
                stream.read(int(SAMPLE_RATE * 0.5))
            except Exception:
                pass

            with self._state_lock:
                self.recording_mode = 'assistant'
            self._set_state('idle')
            with self._state_lock:
                self.last_command_time = time.time()

    def _record_until_silence(self, stream) -> Optional['np.ndarray']:
        """Record audio until silence is detected or timeout"""
        chunks = []
        silence_start = None
        start_time = time.time()
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)

        while time.time() - start_time < COMMAND_TIMEOUT:
            if self.cancel_event.is_set():
                self.cancel_event.clear()
                return None

            audio_chunk, _ = stream.read(chunk_size)
            audio_chunk = audio_chunk.flatten()
            chunks.append(audio_chunk)

            rms = np.sqrt(np.mean(audio_chunk ** 2))

            if rms < SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > SILENCE_DURATION:
                    break
            else:
                silence_start = None

        if chunks:
            return np.concatenate(chunks)
        return None

    def _record_until_stopped(self, stream) -> Optional['np.ndarray']:
        """Record audio until manually stopped (no silence detection, for notes mode)"""
        chunks = []
        start_time = time.time()
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)

        while time.time() - start_time < MAX_NOTES_DURATION:
            if self.stop_recording_event.is_set():
                self.stop_recording_event.clear()
                logger.debug("Recording stopped by user")
                break

            if self.cancel_event.is_set():
                self.cancel_event.clear()
                return None

            audio_chunk, _ = stream.read(chunk_size)
            chunks.append(audio_chunk.flatten())

        if chunks:
            return np.concatenate(chunks)
        return None

    def _transcribe(self, audio_data: 'np.ndarray') -> Optional[str]:
        """Transcribe audio using Whisper API (preferred) or ElevenLabs fallback"""
        if not WHISPER_URL and not ELEVENLABS_API_KEY:
            logger.warning("No WHISPER_URL or ELEVENLABS_API_KEY set")
            return None

        temp_path = None
        try:
            # Save audio to temp WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
                audio_int16 = (audio_data * 32767).astype('int16')
                with wave.open(temp_path, 'wb') as wav:
                    wav.setnchannels(CHANNELS)
                    wav.setsampwidth(2)  # 16-bit
                    wav.setframerate(SAMPLE_RATE)
                    wav.writeframes(audio_int16.tobytes())

            if WHISPER_URL:
                return self._transcribe_whisper(temp_path)
            else:
                return self._transcribe_elevenlabs(temp_path)

        except Exception as e:
            logger.error("Transcription error: %s", e, exc_info=True)
            return None
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

    def _transcribe_whisper(self, audio_path: str) -> Optional[str]:
        """Transcribe audio using self-hosted Whisper API"""
        try:
            with open(audio_path, 'rb') as audio_file:
                response = requests.post(
                    f'{WHISPER_URL}/asr',
                    files={'audio_file': ('audio.wav', audio_file, 'audio/wav')},
                    params={'output': 'json'},
                    timeout=30
                )

            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '').strip()
                return transcript if transcript else None
            else:
                logger.error("Whisper API error: %d - %s", response.status_code, response.text)
                return None

        except Exception as e:
            logger.error("Whisper transcription error: %s", e)
            return None

    def _transcribe_elevenlabs(self, audio_path: str) -> Optional[str]:
        """Transcribe audio using ElevenLabs API (fallback)"""
        try:
            with open(audio_path, 'rb') as audio_file:
                response = requests.post(
                    'https://api.elevenlabs.io/v1/speech-to-text',
                    headers={'xi-api-key': ELEVENLABS_API_KEY},
                    files={'file': ('audio.wav', audio_file, 'audio/wav')},
                    data={'model_id': 'scribe_v1', 'language_code': 'en'},
                    timeout=30
                )

            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '').strip()
                return transcript if transcript else None
            else:
                logger.error("ElevenLabs API error: %d - %s", response.status_code, response.text)
                return None

        except Exception as e:
            logger.error("ElevenLabs transcription error: %s", e)
            return None

    def speak(self, text: str, priority: int = 0) -> bool:
        """Speak text using TTS. Blocks until complete."""
        with self._state_lock:
            if not self.enabled:
                return False

        with self.speak_lock:
            self._set_state('speaking')
            with self._state_lock:
                self.tts_playing = True

            try:
                if MOCK_MODE:
                    logger.debug("Mock speaking: %s", text)
                    time.sleep(len(text) * 0.05)
                    return True

                if not self.piper_voice:
                    logger.warning("TTS unavailable, would say: %s", text)
                    return False

                audio_data = []
                sample_rate = 22050
                for chunk in self.piper_voice.synthesize(text):
                    audio_data.append(chunk.audio_int16_array)
                    sample_rate = chunk.sample_rate

                if audio_data:
                    with self._state_lock:
                        volume = self.tts_volume
                    audio = np.concatenate(audio_data).astype('float32') / 32767
                    audio = audio * (volume / 100.0)
                    sd.play(audio, samplerate=sample_rate)
                    sd.wait()

                return True

            except Exception as e:
                with self._state_lock:
                    self.error = str(e)
                logger.error("TTS error: %s", e, exc_info=True)
                return False

            finally:
                time.sleep(0.3)
                with self._state_lock:
                    self._tts_just_ended = True
                    self.tts_playing = False
                self._set_state('idle')
                with self._state_lock:
                    self.last_command_time = time.time()

    def trigger_mock_wake(self, transcript: str = "test"):
        """Mock wake word trigger for testing without hardware."""
        with self._state_lock:
            if self.state != 'idle':
                return {'error': 'Already processing'}

        self._set_state('listening')
        time.sleep(0.5)

        self._set_state('processing')
        time.sleep(0.3)

        with self._state_lock:
            self.last_transcript = transcript

        self._set_state('idle')

        return {
            'transcript': transcript,
        }

    def start_listening(self, mode: str = 'assistant') -> dict:
        """Start listening for a voice command (bypass wake word detection)."""
        with self._state_lock:
            if self.state != 'idle':
                return {'error': 'Already processing', 'state': self.state}
            self.recording_mode = mode

        logger.info("Starting listening in %s mode", mode)

        if MOCK_MODE:
            return self.trigger_mock_wake('test command')

        self.manual_listen_event.set()

        return {'status': 'listening', 'mode': mode}

    def get_tts_volume(self) -> int:
        """Get current TTS volume percentage"""
        with self._state_lock:
            return self.tts_volume

    def set_tts_volume(self, volume: int):
        """Set TTS volume percentage (0-100)"""
        with self._state_lock:
            self.tts_volume = max(0, min(100, int(volume)))
            vol = self.tts_volume
        logger.info("TTS volume set to %d%%", vol)

    def get_status(self) -> dict:
        """Get current audio system status"""
        with self._state_lock:
            return {
                'state': self.state,
                'last_transcript': self.last_transcript,
                'error': self.error,
                'enabled': self.enabled,
                'tts_volume': self.tts_volume,
                'mock': MOCK_MODE,
                'capabilities': {
                    'wake_word': WAKEWORD_AVAILABLE and self.wakeword_model is not None and not DISABLE_WAKE_WORD,
                    'stt': bool(WHISPER_URL or ELEVENLABS_API_KEY),
                    'tts': PIPER_AVAILABLE and self.piper_voice is not None,
                },
                'wake_word_disabled': DISABLE_WAKE_WORD,
            }

    def cleanup(self):
        """Clean shutdown"""
        self.stop()


# Singleton instance
_controller: Optional[AudioController] = None


def get_audio_controller() -> AudioController:
    """Get singleton AudioController instance"""
    global _controller
    if _controller is None:
        _controller = AudioController()
    return _controller
