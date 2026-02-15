#!/usr/bin/env python3
"""
Hardware Sidecar Server
Flask API for controlling NeoPixel LEDs and reading presence sensor
Runs on port 5000, called by Next.js dashboard
"""

# Setup logging before any controller imports (they call get_logger at import time)
from config import PORT, DEBUG
from log import setup_logging, get_logger

setup_logging('DEBUG' if DEBUG else 'INFO')
logger = get_logger('server')

import signal
import sys
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS

from led import get_controller
from presence import get_detector
from audio import get_audio_controller
from backlight import get_backlight_controller
from volume import get_volume_controller

app = Flask(__name__)
CORS(app)

# Get instances
led_controller = get_controller()
presence_detector = get_detector()
audio_controller = get_audio_controller()
backlight_controller = get_backlight_controller()
volume_controller = get_volume_controller()


# ============ Helpers ============

def _parse_int(value, name: str, min_val: int, max_val: int):
    """
    Parse and validate an integer value from request data.
    Returns (parsed_value, None) on success or (None, error_response_tuple) on failure.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None, (jsonify({"error": f"'{name}' must be an integer"}), 400)
    if value < min_val or value > max_val:
        return None, (jsonify({"error": f"'{name}' must be between {min_val} and {max_val}"}), 400)
    return value, None


# ============ Global Error Handlers ============

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.error("Internal server error: %s", e, exc_info=True)
    return jsonify({"error": "Internal server error"}), 500


# ============ Health ============

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
    present_param = request.args.get('present')
    if present_param is not None:
        presence_detector.set_mock_presence(present_param.lower() == 'true')

    return jsonify(presence_detector.get_status())


@app.route('/presence/debug', methods=['POST'])
def toggle_debug_mode():
    """Toggle sensor debug mode for gate energy readings"""
    data = request.get_json() or {}
    enable = data.get('enable', True)

    if not isinstance(enable, bool):
        return jsonify({"error": "'enable' must be a boolean"}), 400

    if enable:
        success = presence_detector.enable_debug_mode()
    else:
        success = presence_detector.disable_debug_mode()

    return jsonify({
        "debug_mode": presence_detector.debug_mode,
        "success": success
    })


@app.route('/presence/posture/dismiss', methods=['POST'])
def dismiss_posture_alert():
    """Dismiss active posture alert and reset tracking"""
    presence_detector.dismiss_posture_alert()
    return jsonify({
        "dismissed": True,
        "posture_alert": presence_detector.posture_alert_active
    })


# ============ LED Endpoints ============

@app.route('/led', methods=['GET'])
def get_led_status():
    """Get current LED status"""
    return jsonify(led_controller.get_status())


@app.route('/led', methods=['POST'])
def set_led():
    """Set LED color and mode"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    color = data.get('color', '#000000')
    mode = data.get('mode', 'static')

    # Validate brightness
    if 'brightness' in data:
        brightness, err = _parse_int(data['brightness'], 'brightness', 0, 100)
        if err:
            return err
    else:
        brightness = 100

    # Validate color format
    if not color.startswith('#') or len(color) != 7:
        return jsonify({"error": "Invalid color format. Use hex like #FFF4E0"}), 400

    # Validate mode
    valid_modes = ['static', 'pulse', 'flash', 'fade', 'breathe', 'rainbow', 'disco', 'chase', 'gradient', 'off']
    if mode not in valid_modes:
        return jsonify({"error": f"Invalid mode. Use one of: {valid_modes}"}), 400

    ambient = data.get('ambient', True)

    led_controller.set_color(color, mode, brightness, ambient=ambient)

    return jsonify(led_controller.get_status())


@app.route('/led/restore', methods=['POST'])
def restore_led():
    """Restore LED to saved ambient (resting) state."""
    led_controller.restore_ambient()
    return jsonify(led_controller.get_status())


# ============ Brightness Endpoints ============

@app.route('/brightness', methods=['GET'])
def get_brightness():
    """Get current screen brightness"""
    return jsonify(backlight_controller.get_status())


@app.route('/brightness', methods=['POST'])
def set_brightness():
    """Set screen brightness"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    if 'brightness' not in data:
        return jsonify({"error": "Missing 'brightness' field"}), 400

    brightness, err = _parse_int(data['brightness'], 'brightness', 10, 100)
    if err:
        return err

    backlight_controller.set_brightness(brightness)

    return jsonify(backlight_controller.get_status())


# ============ Volume Endpoints ============

@app.route('/volume', methods=['GET'])
def get_volume():
    """Get current system volume"""
    return jsonify(volume_controller.get_status())


@app.route('/volume', methods=['POST'])
def set_volume():
    """Set system volume"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    if 'volume' in data:
        volume, err = _parse_int(data['volume'], 'volume', 0, 100)
        if err:
            return err
        volume_controller.set_volume(volume)

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
    """TTS playback request"""
    data = request.get_json()

    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data.get('text', '')
    if not text or not text.strip():
        return jsonify({"error": "'text' must be non-empty"}), 400

    if len(text) > 5000:
        return jsonify({"error": "'text' must be 5000 characters or fewer"}), 400

    priority = data.get('priority', 0)

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
    """Mock wake word trigger for testing without hardware."""
    data = request.get_json() or {}
    transcript = data.get('transcript', 'show news')

    result = audio_controller.trigger_mock_wake(transcript)

    if 'error' in result:
        return jsonify(result), 409

    return jsonify(result)


@app.route('/voice/listen', methods=['POST'])
def start_listen():
    """Start listening for a voice command (bypass wake word detection)."""
    data = request.get_json() or {}
    mode = data.get('mode', 'assistant')

    if mode not in ('assistant', 'notes'):
        return jsonify({"error": "'mode' must be 'assistant' or 'notes'"}), 400

    result = audio_controller.start_listening(mode=mode)

    if 'error' in result:
        return jsonify(result), 409

    return jsonify(result)


@app.route('/voice/stop-recording', methods=['POST'])
def stop_recording():
    """Stop recording and proceed to transcription (for notes mode)."""
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
    """Set TTS voice volume"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    if 'volume' not in data:
        return jsonify({"error": "Missing 'volume' field"}), 400

    volume, err = _parse_int(data['volume'], 'volume', 0, 100)
    if err:
        return err

    audio_controller.set_tts_volume(volume)

    return jsonify({
        "volume": audio_controller.get_tts_volume(),
    })


@app.route('/voice/pause', methods=['POST'])
def pause_voice():
    """Pause wake word detection (for frontend TTS playback)."""
    audio_controller.pause_detection()
    return jsonify({'status': 'paused'})


@app.route('/voice/resume', methods=['POST'])
def resume_voice():
    """Resume wake word detection (after frontend TTS ends)."""
    audio_controller.resume_detection()
    return jsonify({'status': 'resumed'})


@app.route('/voice/cancel', methods=['POST'])
def cancel_voice():
    """Cancel current listening/processing operation."""
    audio_controller.cancel_listening()
    return jsonify({'status': 'cancelled'})


@app.route('/voice/clear-transcript', methods=['POST'])
def clear_transcript():
    """Clear the last transcript."""
    audio_controller.clear_transcript()
    return jsonify({'status': 'cleared'})


# ============ Shutdown Handler ============

def shutdown_handler(signum, frame):
    """Clean shutdown - each controller wrapped in try/except"""
    logger.info("Shutting down...")

    for name, cleanup in [
        ("LED", led_controller.cleanup),
        ("Presence", presence_detector.stop),
        ("Audio", audio_controller.cleanup),
        ("Backlight", lambda: backlight_controller.set_brightness(100)),
    ]:
        try:
            cleanup()
            logger.info("%s cleanup complete", name)
        except Exception as e:
            logger.error("%s cleanup failed: %s", name, e)

    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


# ============ Main ============

if __name__ == '__main__':
    # Start voice detection on launch
    audio_controller.start()

    print(f"""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551         Dashboard Hardware Sidecar                 \u2551
\u2560\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2563
\u2551  LED Controller:  {"Mock" if led_controller.get_status().get('mock') else "Active":>9}                       \u2551
\u2551  Presence Sensor: {"Mock" if presence_detector.get_status().get('mock') else "Active":>9}                       \u2551
\u2551  Voice System:    {"Mock" if audio_controller.get_status().get('mock') else "Active":>9}                       \u2551
\u2551  Backlight:       {"Mock" if backlight_controller.get_status().get('mock') else "Active":>9}                       \u2551
\u2551  Volume:          {"Mock" if volume_controller.get_status().get('mock') else "Active":>9}                       \u2551
\u2551  Port: {PORT}                                        \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d
    """)

    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
