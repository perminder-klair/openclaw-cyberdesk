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

# Try to import audio dependencies, fall back to mock for development
try:
    import numpy as np
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("[Audio] sounddevice/numpy not available - running in mock mode")

# Wake word detection
try:
    from openwakeword.model import Model as WakeWordModel
    WAKEWORD_AVAILABLE = True
except ImportError:
    WAKEWORD_AVAILABLE = False
    print("[Audio] openwakeword not available - wake word disabled")

# Speech-to-text via Whisper API (self-hosted) or ElevenLabs fallback
import requests
WHISPER_URL = os.environ.get('WHISPER_URL')  # e.g., https://llama.zeiq.dev/whisper
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY')

# Text-to-speech
try:
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    print("[Audio] piper-tts not available - TTS disabled")

# Configuration
MOCK_MODE = os.environ.get('MOCK_AUDIO', 'false').lower() == 'true' or not AUDIO_AVAILABLE
DASHBOARD_URL = os.environ.get('DASHBOARD_URL', 'http://localhost:3000')
SYNC_API_KEY = os.environ.get('SYNC_API_KEY', '')
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.16  # 160ms = 2×80ms for optimal OWW frame alignment
COMMAND_TIMEOUT = 10.0  # Max seconds to listen for command
SILENCE_THRESHOLD = 0.01  # RMS threshold for silence detection
SILENCE_DURATION = 1.5  # Seconds of silence to end command
COMMAND_COOLDOWN = 5.0  # Seconds to wait after command before listening again

# Wake word tuning
WAKE_WORD_THRESHOLD = float(os.environ.get('WAKE_WORD_THRESHOLD', '0.40'))
AUDIO_GAIN = float(os.environ.get('AUDIO_GAIN', '1.0'))
WAKE_WORD_DEBUG = os.environ.get('WAKE_WORD_DEBUG', 'false').lower() == 'true'
DISABLE_WAKE_WORD = os.environ.get('DISABLE_WAKE_WORD', 'false').lower() == 'true'

def _detect_wm8960_device() -> Optional[str]:
    """Auto-detect WM8960 audio device for sounddevice"""
    if not AUDIO_AVAILABLE:
        return None
    try:
        for device in sd.query_devices():
            if 'wm8960' in device['name'].lower():
                print(f"[Audio] Auto-detected WM8960: {device['name']}")
                return device['name']
    except Exception as e:
        print(f"[Audio] Device detection error: {e}")
    return None

# Use env var if set, otherwise auto-detect WM8960
AUDIO_DEVICE = os.environ.get('AUDIO_DEVICE') or _detect_wm8960_device()
ENABLE_SPEEX_NOISE_SUPPRESSION = os.environ.get('ENABLE_SPEEX_NOISE_SUPPRESSION', 'false').lower() == 'true'

# Model paths
MODELS_DIR = Path(__file__).parent / "models"
PIPER_VOICE = os.environ.get('PIPER_VOICE', 'en_US-lessac-medium')
WAKE_WORD = os.environ.get('WAKE_WORD', 'hey_jarvis')  # Use pretrained or custom 'hey_klair'

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
        self.manual_listen_event = threading.Event()  # Signal for manual listen trigger
        self.cancel_event = threading.Event()  # Signal to cancel current listening
        self.stop_recording_event = threading.Event()  # Signal to stop recording (but keep audio)
        self.recording_mode = 'assistant'  # 'assistant' (silence detection) or 'notes' (manual stop)
        self.tts_playing = False  # Prevents mic pickup during TTS playback
        self._tts_just_ended = False  # Signal to clear audio buffer after TTS
        self.detection_paused = False  # Pause detection during frontend TTS

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
            print("[Audio] Running in mock mode")
            return

        # Wake word model
        if WAKEWORD_AVAILABLE:
            try:
                # openwakeword 0.4+ uses wakeword_model_paths instead of wakeword_models
                import openwakeword
                oww_dir = Path(openwakeword.__file__).parent
                model_path = oww_dir / "resources" / "models" / f"{WAKE_WORD}_v0.1.onnx"

                if model_path.exists():
                    self.wakeword_model = WakeWordModel(
                        wakeword_model_paths=[str(model_path)],
                        enable_speex_noise_suppression=ENABLE_SPEEX_NOISE_SUPPRESSION,
                    )
                    print(f"[Audio] Wake word model loaded: {WAKE_WORD} (speex={ENABLE_SPEEX_NOISE_SUPPRESSION})")
                else:
                    print(f"[Audio] Wake word model not found: {model_path}")
            except Exception as e:
                print(f"[Audio] Failed to load wake word model: {e}")

        # STT via Whisper API (preferred) or ElevenLabs fallback
        if WHISPER_URL:
            print(f"[Audio] Whisper STT API configured: {WHISPER_URL}")
        elif ELEVENLABS_API_KEY:
            print("[Audio] ElevenLabs STT API configured (fallback)")
        else:
            print("[Audio] No WHISPER_URL or ELEVENLABS_API_KEY - STT disabled")

        # Piper TTS
        if PIPER_AVAILABLE:
            try:
                voice_path = MODELS_DIR / f"{PIPER_VOICE}.onnx"
                config_path = MODELS_DIR / f"{PIPER_VOICE}.onnx.json"

                if voice_path.exists():
                    self.piper_voice = PiperVoice.load(str(voice_path), str(config_path))
                    print(f"[Audio] Piper voice loaded: {PIPER_VOICE}")
                else:
                    print(f"[Audio] Piper voice not found at {voice_path}")
            except Exception as e:
                print(f"[Audio] Failed to load Piper voice: {e}")

    def _set_state(self, state: str):
        """Update state and notify listeners"""
        self.state = state
        if self.on_state_change:
            try:
                self.on_state_change(self.get_status())
            except Exception as e:
                print(f"[Audio] State change callback error: {e}")
        # Notify dashboard via webhook (fire-and-forget)
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
                pass  # Fire-and-forget, don't block audio processing
        threading.Thread(target=send, daemon=True).start()

    def start(self):
        """Start wake word detection loop"""
        if self.running:
            return

        self.running = True
        self.stop_event.clear()
        self.enabled = True

        self.listen_thread = threading.Thread(
            target=self._wake_word_loop,
            daemon=True
        )
        self.listen_thread.start()
        if DISABLE_WAKE_WORD:
            print("[Audio] Audio loop started (wake word DISABLED, manual trigger only)")
        else:
            print("[Audio] Wake word detection started")

    def stop(self):
        """Stop wake word detection"""
        self.running = False
        self.enabled = False
        self.stop_event.set()

        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=2)

        self._set_state('idle')
        print("[Audio] Wake word detection stopped")

    def pause_detection(self):
        """Pause wake word detection (called when frontend TTS starts)"""
        self.detection_paused = True
        print("[Audio] Detection paused for frontend TTS")

    def resume_detection(self):
        """Resume wake word detection (called when frontend TTS ends)"""
        self._tts_just_ended = True  # Clear buffer before resuming
        self.detection_paused = False
        self.last_command_time = time.time()  # Reset cooldown
        print("[Audio] Detection resumed after frontend TTS")

    def cancel_listening(self):
        """Cancel current listening/processing operation (called when dialog closes)"""
        if self.state in ('listening', 'processing'):
            self.cancel_event.set()
            self._set_state('idle')
            self.last_transcript = None
            print("[Audio] Listening cancelled")

    def stop_recording(self):
        """Stop recording but proceed to transcription (for notes mode)"""
        if self.state == 'listening':
            self.stop_recording_event.set()
            print("[Audio] Stop recording requested")

    def _wake_word_loop(self):
        """Main loop for wake word detection"""
        print(f"[Audio] Wake word loop started (MOCK_MODE={MOCK_MODE})", flush=True)

        if MOCK_MODE:
            # In mock mode, just sleep and check for stop
            while self.running and not self.stop_event.is_set():
                time.sleep(0.5)
            return

        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)
        print(f"[Audio] Opening audio stream (chunk_size={chunk_size})...", flush=True)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype='float32',
                blocksize=chunk_size,
                device=AUDIO_DEVICE
            ) as stream:
                print(f"[Audio] Listening for wake word (device={AUDIO_DEVICE})...", flush=True)

                while self.running and not self.stop_event.is_set():
                    # Skip during TTS playback to prevent feedback loop
                    if self.state != 'idle' or self.tts_playing or self.detection_paused:
                        time.sleep(0.1)
                        continue

                    # Clear mic buffer after TTS ends to remove captured speaker audio
                    if self._tts_just_ended:
                        self._tts_just_ended = False
                        try:
                            stream.read(int(SAMPLE_RATE * 1.0))  # Discard 1s of buffered audio
                            print("[Audio] Cleared mic buffer after TTS")
                        except Exception:
                            pass
                        continue

                    # Skip detection during cooldown period
                    if time.time() - self.last_command_time < COMMAND_COOLDOWN:
                        time.sleep(0.1)
                        continue

                    # Check for manual listen trigger (reuses this stream)
                    if self.manual_listen_event.is_set():
                        self.manual_listen_event.clear()
                        print("[Audio] Manual listen triggered via wake word stream")
                        self._on_wake_word_detected(stream)
                        continue

                    # Read audio chunk
                    audio_chunk, _ = stream.read(chunk_size)
                    audio_chunk = audio_chunk.flatten()

                    # Check for wake word (skip if disabled)
                    if not DISABLE_WAKE_WORD and self._detect_wake_word(audio_chunk):
                        self._on_wake_word_detected(stream)

        except Exception as e:
            self.error = str(e)
            print(f"[Audio] Wake word loop error: {e}")

    def _detect_wake_word(self, audio_chunk: 'np.ndarray') -> bool:
        """Check if audio chunk contains wake word"""
        if not self.wakeword_model:
            return False

        try:
            # Apply audio gain for quiet microphones
            if AUDIO_GAIN != 1.0:
                audio_chunk = audio_chunk * AUDIO_GAIN
                audio_chunk = np.clip(audio_chunk, -1.0, 1.0)  # Prevent clipping

            # OpenWakeWord expects int16
            audio_int16 = (audio_chunk * 32767).astype('int16')
            prediction = self.wakeword_model.predict(audio_int16)

            # Check if any wake word triggered (openwakeword 0.4+ returns single float per word)
            for ww_name, score in prediction.items():
                # Debug logging to help tune threshold
                if WAKE_WORD_DEBUG and score > 0.3:
                    print(f"[Audio Debug] {ww_name}: {score:.2f}")

                # Track scores for rolling window detection
                self.detection_history.append(score)
                self.detection_history = self.detection_history[-5:]  # Keep last 5 for gradual detection

                # Trigger on single high score OR average of last 2 scores
                if score > WAKE_WORD_THRESHOLD:
                    print(f"[Audio] Wake word detected: {ww_name} (score: {score:.2f})")
                    self.detection_history = []  # Reset history on detection
                    return True

                # Also trigger if rolling average is above 80% threshold (catches gradual buildup)
                if len(self.detection_history) >= 3:
                    avg = sum(self.detection_history[-3:]) / 3
                    if avg > WAKE_WORD_THRESHOLD * 0.8:
                        print(f"[Audio] Wake word detected (rolling avg): {ww_name} (avg: {avg:.2f})")
                        self.detection_history = []  # Reset history on detection
                        return True

        except Exception as e:
            print(f"[Audio] Wake word detection error: {e}")

        return False

    def _is_valid_transcript(self, text: str) -> bool:
        """Check if transcript is actual speech, not noise descriptions"""
        if not text:
            return False
        # ElevenLabs returns noise in parentheses: (white noise), (click), etc.
        if text.startswith('(') and text.endswith(')'):
            return False
        # Too short to be a real command
        if len(text.strip()) < 3:
            return False
        return True

    def _clean_transcript(self, text: str) -> str:
        """Remove wake word from start of transcript"""
        # Match common wake word variations at start
        patterns = [
            r'^hey,?\s*jarvis[.,]?\s*',
            r'^hi,?\s*jarvis[.,]?\s*',
            r'^okay,?\s*jarvis[.,]?\s*',
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    def _on_wake_word_detected(self, stream):
        """Handle wake word detection - record and transcribe command"""
        self._set_state('listening')
        print(f"[Audio] Wake word triggered - now listening for command (mode={self.recording_mode})...")

        try:
            # Record command - use appropriate method based on mode
            if self.recording_mode == 'notes':
                audio_data = self._record_until_stopped(stream)
            else:
                audio_data = self._record_until_silence(stream)

            if audio_data is None:
                print("[Audio] No audio recorded")
                self._set_state('idle')
                return

            duration = len(audio_data) / SAMPLE_RATE
            print(f"[Audio] Recorded {duration:.2f}s of audio")

            if duration < 0.5:  # Min 0.5s
                print("[Audio] Recording too short, ignoring")
                self._set_state('idle')
                return

            # Check for cancel before transcription
            if self.cancel_event.is_set():
                self.cancel_event.clear()
                print("[Audio] Cancelled before transcription")
                self._set_state('idle')
                return

            # Transcribe
            self._set_state('processing')
            print(f"[Audio] Transcribing with {'Whisper' if WHISPER_URL else 'ElevenLabs'}...")
            transcript = self._transcribe(audio_data)

            print(f"[Audio] Raw transcript: '{transcript}'")

            if transcript:
                # Clean wake word from transcript
                transcript = self._clean_transcript(transcript)

                # Validate transcript is actual speech
                if self._is_valid_transcript(transcript):
                    self.last_transcript = transcript
                    print(f"[Audio] Transcript ready: '{transcript}'")
                else:
                    print(f"[Audio] Filtered noise transcript: '{transcript}'")
                    self.last_transcript = None
            else:
                print("[Audio] No transcript returned")
                self.last_transcript = None

        except Exception as e:
            self.error = str(e)
            print(f"[Audio] Command processing error: {e}")

        finally:
            # Clear audio buffer to prevent echo/noise triggering wake word again
            try:
                stream.read(int(SAMPLE_RATE * 0.5))  # Discard 0.5s of audio
            except Exception:
                pass

            # Reset recording mode to default
            self.recording_mode = 'assistant'
            self._set_state('idle')
            self.last_command_time = time.time()

    def _record_until_silence(self, stream) -> Optional['np.ndarray']:
        """Record audio until silence is detected or timeout"""
        chunks = []
        silence_start = None
        start_time = time.time()
        chunk_size = int(SAMPLE_RATE * CHUNK_DURATION)

        while time.time() - start_time < COMMAND_TIMEOUT:
            # Check for cancel signal
            if self.cancel_event.is_set():
                self.cancel_event.clear()
                return None

            audio_chunk, _ = stream.read(chunk_size)
            audio_chunk = audio_chunk.flatten()
            chunks.append(audio_chunk)

            # Check for silence
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
        MAX_DURATION = 120.0  # 2 min max for notes

        while time.time() - start_time < MAX_DURATION:
            # Check for stop signal (keep audio)
            if self.stop_recording_event.is_set():
                self.stop_recording_event.clear()
                print("[Audio] Recording stopped by user")
                break

            # Check for cancel signal (discard audio)
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
            print("[Audio] No WHISPER_URL or ELEVENLABS_API_KEY set")
            return None

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

            # Use Whisper API if configured, otherwise fall back to ElevenLabs
            if WHISPER_URL:
                return self._transcribe_whisper(temp_path)
            else:
                return self._transcribe_elevenlabs(temp_path)

        except Exception as e:
            print(f"[Audio] Transcription error: {e}")
            return None

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

            # Cleanup temp file
            os.unlink(audio_path)

            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '').strip()
                return transcript if transcript else None
            else:
                print(f"[Audio] Whisper API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"[Audio] Whisper transcription error: {e}")
            # Cleanup temp file on error
            try:
                os.unlink(audio_path)
            except Exception:
                pass
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

            # Cleanup temp file
            os.unlink(audio_path)

            if response.status_code == 200:
                result = response.json()
                transcript = result.get('text', '').strip()
                return transcript if transcript else None
            else:
                print(f"[Audio] ElevenLabs API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"[Audio] ElevenLabs transcription error: {e}")
            # Cleanup temp file on error
            try:
                os.unlink(audio_path)
            except Exception:
                pass
            return None

    def speak(self, text: str, priority: int = 0) -> bool:
        """
        Speak text using TTS.
        Blocks until complete. Uses lock to prevent overlapping speech.

        Args:
            text: Text to speak
            priority: Higher priority interrupts lower priority speech

        Returns:
            True if spoken successfully
        """
        if not self.enabled:
            return False

        with self.speak_lock:
            self._set_state('speaking')
            self.tts_playing = True  # Pause wake word detection during TTS

            try:
                if MOCK_MODE:
                    print(f"[Audio Mock] Speaking: {text}")
                    time.sleep(len(text) * 0.05)  # Simulate speech duration
                    return True

                if not self.piper_voice:
                    print(f"[Audio] TTS unavailable, would say: {text}")
                    return False

                # Generate audio with Piper (piper-tts 1.2+ API)
                audio_data = []
                sample_rate = 22050  # Default, will be updated from chunk
                for chunk in self.piper_voice.synthesize(text):
                    audio_data.append(chunk.audio_int16_array)
                    sample_rate = chunk.sample_rate

                if audio_data:
                    audio = np.concatenate(audio_data).astype('float32') / 32767
                    # Apply TTS volume scaling
                    audio = audio * (self.tts_volume / 100.0)
                    sd.play(audio, samplerate=sample_rate)
                    sd.wait()

                return True

            except Exception as e:
                self.error = str(e)
                print(f"[Audio] TTS error: {e}")
                return False

            finally:
                # Let audio hardware settle before resuming detection
                time.sleep(0.3)
                self._tts_just_ended = True  # Signal to clear mic buffer
                self.tts_playing = False  # Resume wake word detection
                self._set_state('idle')
                # Reset cooldown AFTER speaking to prevent wake word triggering on TTS output
                self.last_command_time = time.time()

    def trigger_mock_wake(self, transcript: str = "test"):
        """
        Mock wake word trigger for testing without hardware.
        Simulates wake word detection with given transcript.
        """
        if self.state != 'idle':
            return {'error': 'Already processing'}

        self._set_state('listening')
        time.sleep(0.5)  # Simulate listening

        self._set_state('processing')
        time.sleep(0.3)  # Simulate processing

        self.last_transcript = transcript

        self._set_state('idle')

        return {
            'transcript': self.last_transcript,
        }

    def start_listening(self, mode: str = 'assistant') -> dict:
        """
        Start listening for a voice command (bypass wake word detection).
        Used for manual trigger via UI button.

        Args:
            mode: 'assistant' (silence detection) or 'notes' (manual stop only)
        """
        if self.state != 'idle':
            return {'error': 'Already processing', 'state': self.state}

        # Set recording mode
        self.recording_mode = mode
        print(f"[Audio] Starting listening in {mode} mode")

        if MOCK_MODE:
            # In mock mode, simulate listening
            return self.trigger_mock_wake('test command')

        # Signal wake word loop to start recording (reuses existing stream)
        self.manual_listen_event.set()

        return {'status': 'listening', 'mode': mode}

    def get_tts_volume(self) -> int:
        """Get current TTS volume percentage"""
        return self.tts_volume

    def set_tts_volume(self, volume: int):
        """Set TTS volume percentage (0-100)"""
        self.tts_volume = max(0, min(100, int(volume)))
        print(f"[Audio] TTS volume set to {self.tts_volume}%")

    def get_status(self) -> dict:
        """Get current audio system status"""
        return {
            'state': self.state,
            'lastTranscript': self.last_transcript,
            'error': self.error,
            'enabled': self.enabled,
            'ttsVolume': self.tts_volume,
            'mock': MOCK_MODE,
            'capabilities': {
                'wakeWord': WAKEWORD_AVAILABLE and self.wakeword_model is not None and not DISABLE_WAKE_WORD,
                'stt': bool(WHISPER_URL or ELEVENLABS_API_KEY),
                'tts': PIPER_AVAILABLE and self.piper_voice is not None,
            },
            'wakeWordDisabled': DISABLE_WAKE_WORD,
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
