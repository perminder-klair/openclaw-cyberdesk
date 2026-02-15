#!/usr/bin/env python3
"""
Hardware Sidecar Server
Flask API for controlling NeoPixel LEDs and reading presence sensor
Runs on port 5000, called by Next.js dashboard
"""

# Load .env BEFORE any imports that read env vars (audio.py reads at import time)
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

import os
import signal
import sys
from flask import Flask, jsonify, request
from flask_cors import CORS

from led import get_controller
from presence import get_detector
from audio import get_audio_controller
from backlight import get_backlight_controller
from volume import get_volume_controller

app = Flask(__name__)
CORS(app)  # Allow requests from Next.js on different port

# Get instances
led_controller = get_controller()
presence_detector = get_detector()
audio_controller = get_audio_controller()
backlight_controller = get_backlight_controller()
volume_controller = get_volume_controller()


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "led": led_controller.get_status(),
        "presence": presence_detector.get_status(),
        "voice": audio_controller.get_status(),
        "backlight": backlight_controller.get_status(),
        "volume": volume_controller.get_status(),
    })


# ============ Presence Endpoints ============

@app.route('/presence', methods=['GET'])
def get_presence():
    """Get current presence status"""
    # Allow mock override via query param for testing
    present_param = request.args.get('present')
    if present_param is not None:
        presence_detector.set_mock_presence(present_param.lower() == 'true')

    return jsonify(presence_detector.get_status())


@app.route('/presence/debug', methods=['POST'])
def toggle_debug_mode():
    """
    Toggle sensor debug mode for gate energy readings

    Body:
    {
        "enable": true  // true to enable, false to disable
    }
    """
    data = request.get_json() or {}
    enable = data.get('enable', True)

    if enable:
        success = presence_detector.enable_debug_mode()
    else:
        success = presence_detector.disable_debug_mode()

    return jsonify({
        "debugMode": presence_detector.debug_mode,
        "success": success
    })


@app.route('/presence/posture/dismiss', methods=['POST'])
def dismiss_posture_alert():
    """Dismiss active posture alert and reset tracking"""
    presence_detector.dismiss_posture_alert()
    return jsonify({
        "dismissed": True,
        "postureAlert": presence_detector.posture_alert_active
    })


# ============ LED Endpoints ============

@app.route('/led', methods=['GET'])
def get_led_status():
    """Get current LED status"""
    return jsonify(led_controller.get_status())


@app.route('/led', methods=['POST'])
def set_led():
    """
    Set LED color and mode

    Body:
    {
        "color": "#FFF4E0",
        "mode": "static",  // static, pulse, flash, fade, breathe, off
        "brightness": 100  // 0-100
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    color = data.get('color', '#000000')
    mode = data.get('mode', 'static')
    brightness = data.get('brightness', 100)

    # Validate color format
    if not color.startswith('#') or len(color) != 7:
        return jsonify({"error": "Invalid color format. Use hex like #FFF4E0"}), 400

    # Validate mode
    valid_modes = ['static', 'pulse', 'flash', 'fade', 'breathe', 'off']
    if mode not in valid_modes:
        return jsonify({"error": f"Invalid mode. Use one of: {valid_modes}"}), 400

    # Clamp brightness
    brightness = max(0, min(100, int(brightness)))

    led_controller.set_color(color, mode, brightness)

    return jsonify(led_controller.get_status())


# ============ Brightness Endpoints ============

@app.route('/brightness', methods=['GET'])
def get_brightness():
    """Get current screen brightness"""
    return jsonify(backlight_controller.get_status())


@app.route('/brightness', methods=['POST'])
def set_brightness():
    """
    Set screen brightness

    Body:
    {
        "brightness": 75  // 0-100 (minimum 10%)
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    brightness = data.get('brightness', 100)

    # Clamp brightness (min 10% to avoid black screen)
    brightness = max(10, min(100, int(brightness)))

    backlight_controller.set_brightness(brightness)

    return jsonify(backlight_controller.get_status())


# ============ Volume Endpoints ============

@app.route('/volume', methods=['GET'])
def get_volume():
    """Get current system volume"""
    return jsonify(volume_controller.get_status())


@app.route('/volume', methods=['POST'])
def set_volume():
    """
    Set system volume

    Body:
    {
        "volume": 75,  // 0-100
        "muted": false  // optional
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    # Handle volume
    if 'volume' in data:
        volume = max(0, min(100, int(data.get('volume', 100))))
        volume_controller.set_volume(volume)

    # Handle mute
    if 'muted' in data:
        volume_controller.set_muted(bool(data.get('muted')))

    return jsonify(volume_controller.get_status())


# ============ Voice Endpoints ============

@app.route('/voice/status', methods=['GET'])
def get_voice_status():
    """Get current voice system state"""
    return jsonify(audio_controller.get_status())


@app.route('/voice/speak', methods=['POST'])
def speak():
    """
    TTS playback request

    Body:
    {
        "text": "Good morning",
        "priority": 0
    }
    """
    data = request.get_json()

    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data.get('text')
    priority = data.get('priority', 0)

    # Run in background thread to not block HTTP response
    import threading
    threading.Thread(
        target=audio_controller.speak,
        args=(text, priority),
        daemon=True
    ).start()

    return jsonify({
        "status": "speaking",
        "text": text,
    })


@app.route('/voice/enable', methods=['POST'])
def enable_voice():
    """Enable or disable voice system"""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)

    if enabled:
        audio_controller.start()
    else:
        audio_controller.stop()

    return jsonify(audio_controller.get_status())


@app.route('/voice/mock-wake', methods=['POST'])
def mock_wake():
    """
    Mock wake word trigger for testing without hardware.

    Body:
    {
        "transcript": "show news"
    }
    """
    data = request.get_json() or {}
    transcript = data.get('transcript', 'show news')

    result = audio_controller.trigger_mock_wake(transcript)

    return jsonify(result)


@app.route('/voice/listen', methods=['POST'])
def start_listen():
    """
    Start listening for a voice command (bypass wake word detection).
    Used for manual trigger via UI button.

    Body (optional):
    {
        "mode": "assistant"  // 'assistant' (silence detection) or 'notes' (manual stop)
    }
    """
    data = request.get_json() or {}
    mode = data.get('mode', 'assistant')
    result = audio_controller.start_listening(mode=mode)
    return jsonify(result)


@app.route('/voice/stop-recording', methods=['POST'])
def stop_recording():
    """
    Stop recording and proceed to transcription (for notes mode).
    Different from cancel - this keeps the audio and transcribes it.
    """
    audio_controller.stop_recording()
    return jsonify({'status': 'stopped'})


@app.route('/voice/volume', methods=['GET'])
def get_tts_volume():
    """Get current TTS volume"""
    return jsonify({
        "volume": audio_controller.get_tts_volume(),
    })


@app.route('/voice/volume', methods=['POST'])
def set_tts_volume():
    """
    Set TTS voice volume

    Body:
    {
        "volume": 75  // 0-100
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    if 'volume' not in data:
        return jsonify({"error": "Missing 'volume' field"}), 400

    volume = max(0, min(100, int(data.get('volume', 100))))
    audio_controller.set_tts_volume(volume)

    return jsonify({
        "volume": audio_controller.get_tts_volume(),
    })


@app.route('/voice/pause', methods=['POST'])
def pause_voice():
    """
    Pause wake word detection (for frontend TTS playback).
    Call this before playing TTS audio to prevent feedback loop.
    """
    audio_controller.pause_detection()
    return jsonify({'status': 'paused'})


@app.route('/voice/resume', methods=['POST'])
def resume_voice():
    """
    Resume wake word detection (after frontend TTS ends).
    Call this after TTS audio finishes playing.
    """
    audio_controller.resume_detection()
    return jsonify({'status': 'resumed'})


@app.route('/voice/cancel', methods=['POST'])
def cancel_voice():
    """
    Cancel current listening/processing operation.
    Call this when the dialog closes mid-recording.
    """
    audio_controller.cancel_listening()
    return jsonify({'status': 'cancelled'})


@app.route('/voice/clear-transcript', methods=['POST'])
def clear_transcript():
    """
    Clear the last transcript.
    Call this after consuming a transcript (e.g., after saving a voice note).
    Prevents the old transcript from triggering the dialog again.
    """
    audio_controller.last_transcript = None
    return jsonify({'status': 'cleared'})


# ============ Shutdown Handler ============

def shutdown_handler(signum, frame):
    """Clean shutdown"""
    print("\n[Server] Shutting down...")
    led_controller.cleanup()
    presence_detector.stop()
    audio_controller.cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


# ============ Main ============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'

    # Start voice detection on launch
    audio_controller.start()

    print(f"""
╔════════════════════════════════════════════════════╗
║         Dashboard Hardware Sidecar                 ║
╠════════════════════════════════════════════════════╣
║  LED Controller:  {"Mock" if led_controller.get_status().get('mock') else "Active":>9}                       ║
║  Presence Sensor: {"Mock" if presence_detector.get_status().get('mock') else "Active":>9}                       ║
║  Voice System:    {"Mock" if audio_controller.get_status().get('mock') else "Active":>9}                       ║
║  Backlight:       {"Mock" if backlight_controller.get_status().get('mock') else "Active":>9}                       ║
║  Volume:          {"Mock" if volume_controller.get_status().get('mock') else "Active":>9}                       ║
║  Port: {port}                                        ║
╚════════════════════════════════════════════════════╝
    """)

    app.run(host='0.0.0.0', port=port, debug=debug)
