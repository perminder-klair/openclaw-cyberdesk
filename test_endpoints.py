"""
Endpoint tests for Hardware Sidecar API.
Runs against the live server (default http://localhost:5000).

Usage:
    python test_endpoints.py               # test against localhost:5000
    python test_endpoints.py http://host:port  # test against custom URL
"""

import sys
import json
import time
import urllib.request
import urllib.error

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"

passed = 0
failed = 0


def req(method, path, body=None, expected_status=200):
    """Make an HTTP request and return (status_code, parsed_json)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test(name, status, body, expected_status, checks=None):
    """Assert status code and optional key checks."""
    global passed, failed
    ok = True

    if status != expected_status:
        print(f"  FAIL {name}: expected {expected_status}, got {status}")
        ok = False

    if checks:
        for desc, result in checks:
            if not result:
                print(f"  FAIL {name}: {desc}")
                ok = False

    if ok:
        print(f"  PASS {name}")
        passed += 1
    else:
        print(f"       Response: {json.dumps(body, indent=2)[:200]}")
        failed += 1


# ============ Health ============
print("\n--- Health ---")
s, b = req("GET", "/health")
test("GET /health", s, b, 200, [
    ("has status key", "status" in b),
    ("status is ok", b.get("status") == "ok"),
    ("has led key", "led" in b),
    ("has presence key", "presence" in b),
    ("has voice key", "voice" in b),
    ("has backlight key", "backlight" in b),
    ("has volume key", "volume" in b),
])

# ============ Presence ============
print("\n--- Presence ---")
s, b = req("GET", "/presence")
test("GET /presence", s, b, 200, [
    ("snake_case: is_present", "is_present" in b),
    ("snake_case: last_seen", "last_seen" in b),
    ("snake_case: motion_type", "motion_type" in b),
    ("snake_case: sensor_online", "sensor_online" in b),
    ("snake_case: gpio_available", "gpio_available" in b),
    ("snake_case: posture_alert", "posture_alert" in b),
    ("snake_case: debug_mode", "debug_mode" in b),
    ("no camelCase: isPresent", "isPresent" not in b),
    ("no camelCase: lastSeen", "lastSeen" not in b),
])

s, b = req("GET", "/presence?present=true")
test("GET /presence?present=true", s, b, 200, [
    ("is_present is true", b.get("is_present") is True),
])

s, b = req("POST", "/presence/debug", {"enable": True})
test("POST /presence/debug enable", s, b, 200, [
    ("snake_case: debug_mode", "debug_mode" in b),
    ("has success", "success" in b),
])

s, b = req("POST", "/presence/debug", {"enable": False})
test("POST /presence/debug disable", s, b, 200, [
    ("debug_mode is false", b.get("debug_mode") is False),
])

s, b = req("POST", "/presence/debug", {"enable": "yes"})
test("POST /presence/debug bad bool", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/presence/posture/dismiss")
test("POST /presence/posture/dismiss", s, b, 200, [
    ("snake_case: posture_alert", "posture_alert" in b),
    ("dismissed is true", b.get("dismissed") is True),
])

# ============ LED ============
print("\n--- LED ---")
s, b = req("GET", "/led")
test("GET /led", s, b, 200, [
    ("snake_case: color", "color" in b),
    ("snake_case: mode", "mode" in b),
    ("snake_case: brightness", "brightness" in b),
    ("no camelCase: currentColor", "currentColor" not in b),
    ("no camelCase: currentMode", "currentMode" not in b),
])

s, b = req("POST", "/led", {"color": "#FF0000", "mode": "static", "brightness": 50})
test("POST /led valid", s, b, 200, [
    ("color is #FF0000", b.get("color") == "#FF0000"),
    ("mode is static", b.get("mode") == "static"),
    ("brightness is 50", b.get("brightness") == 50),
])

s, b = req("POST", "/led", {"color": "#FF0000", "mode": "invalid"})
test("POST /led bad mode", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/led", {"color": "red", "mode": "static"})
test("POST /led bad color", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/led", {"color": "#FF0000", "brightness": "abc"})
test("POST /led bad brightness", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/led", {"color": "#FF0000", "brightness": 150})
test("POST /led brightness out of range", s, b, 400, [
    ("has error", "error" in b),
])

# Turn off after tests
req("POST", "/led", {"color": "#000000", "mode": "off", "brightness": 0})

# ============ Brightness ============
print("\n--- Brightness ---")
s, b = req("GET", "/brightness")
test("GET /brightness", s, b, 200, [
    ("has brightness", "brightness" in b),
    ("has mock", "mock" in b),
])

s, b = req("POST", "/brightness", {"brightness": 50})
test("POST /brightness valid", s, b, 200, [
    ("brightness is 50", b.get("brightness") == 50),
])

s, b = req("POST", "/brightness", {"brightness": "abc"})
test("POST /brightness bad value", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/brightness", {"brightness": 5})
test("POST /brightness too low", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/brightness", {"brightness": 150})
test("POST /brightness too high", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/brightness", {})
test("POST /brightness missing field", s, b, 400, [
    ("has error", "error" in b),
])

# ============ Volume ============
print("\n--- Volume ---")
s, b = req("GET", "/volume")
test("GET /volume", s, b, 200, [
    ("has volume", "volume" in b),
    ("has muted", "muted" in b),
    ("has mock", "mock" in b),
])

s, b = req("POST", "/volume", {"volume": 75})
test("POST /volume valid", s, b, 200, [
    ("volume is 75", b.get("volume") == 75),
])

s, b = req("POST", "/volume", {"volume": "abc"})
test("POST /volume bad value", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/volume", {"volume": -5})
test("POST /volume too low", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/volume", {"volume": 200})
test("POST /volume too high", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/volume", {"muted": True})
test("POST /volume mute", s, b, 200, [
    ("muted is true", b.get("muted") is True),
])

s, b = req("POST", "/volume", {"muted": False})
test("POST /volume unmute", s, b, 200, [
    ("muted is false", b.get("muted") is False),
])

# ============ Voice ============
print("\n--- Voice ---")
s, b = req("GET", "/voice/status")
test("GET /voice/status", s, b, 200, [
    ("snake_case: last_transcript", "last_transcript" in b),
    ("snake_case: tts_volume", "tts_volume" in b),
    ("snake_case: wake_word_disabled", "wake_word_disabled" in b),
    ("no camelCase: lastTranscript", "lastTranscript" not in b),
    ("no camelCase: ttsVolume", "ttsVolume" not in b),
    ("has state", "state" in b),
    ("has capabilities", "capabilities" in b),
    ("capabilities snake_case", "wake_word" in b.get("capabilities", {})),
])

s, b = req("POST", "/voice/speak", {"text": "hi"})
test("POST /voice/speak valid", s, b, 200, [
    ("status is speaking", b.get("status") == "speaking"),
    ("has text", b.get("text") == "hi"),
])
# Wait for mock TTS to finish before testing other voice endpoints
time.sleep(2)

s, b = req("POST", "/voice/speak", {"text": ""})
test("POST /voice/speak empty text", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/speak", {})
test("POST /voice/speak missing text", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/speak", {"text": "x" * 5001})
test("POST /voice/speak too long", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/enable", {"enabled": True})
test("POST /voice/enable", s, b, 200, [
    ("has state", "state" in b),
])

s, b = req("POST", "/voice/listen", {"mode": "assistant"})
test("POST /voice/listen valid", s, b, 200)

# Wait for mock listen to complete
time.sleep(2)

s, b = req("POST", "/voice/listen", {"mode": "invalid"})
test("POST /voice/listen bad mode", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/mock-wake", {"transcript": "hello"})
test("POST /voice/mock-wake", s, b, 200, [
    ("has transcript", b.get("transcript") == "hello"),
])

s, b = req("GET", "/voice/volume")
test("GET /voice/volume", s, b, 200, [
    ("has volume", "volume" in b),
])

s, b = req("POST", "/voice/volume", {"volume": 80})
test("POST /voice/volume valid", s, b, 200, [
    ("volume is 80", b.get("volume") == 80),
])

s, b = req("POST", "/voice/volume", {"volume": "abc"})
test("POST /voice/volume bad value", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/volume", {"volume": 150})
test("POST /voice/volume too high", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/volume", {})
test("POST /voice/volume missing", s, b, 400, [
    ("has error", "error" in b),
])

s, b = req("POST", "/voice/pause")
test("POST /voice/pause", s, b, 200, [
    ("status is paused", b.get("status") == "paused"),
])

s, b = req("POST", "/voice/resume")
test("POST /voice/resume", s, b, 200, [
    ("status is resumed", b.get("status") == "resumed"),
])

s, b = req("POST", "/voice/cancel")
test("POST /voice/cancel", s, b, 200, [
    ("status is cancelled", b.get("status") == "cancelled"),
])

s, b = req("POST", "/voice/clear-transcript")
test("POST /voice/clear-transcript", s, b, 200, [
    ("status is cleared", b.get("status") == "cleared"),
])

s, b = req("POST", "/voice/stop-recording")
test("POST /voice/stop-recording", s, b, 200, [
    ("status is stopped", b.get("status") == "stopped"),
])

# ============ Error Handlers ============
print("\n--- Error Handlers ---")
s, b = req("GET", "/nonexistent")
test("GET /nonexistent → 404", s, b, 404, [
    ("has error", "error" in b),
])

s, b = req("DELETE", "/health")
test("DELETE /health → 405", s, b, 405, [
    ("has error", "error" in b),
])

# ============ Summary ============
print(f"\n{'='*40}")
total = passed + failed
print(f"Results: {passed}/{total} passed, {failed} failed")
if failed:
    sys.exit(1)
else:
    print("All tests passed!")
