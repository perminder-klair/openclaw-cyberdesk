# Hardware Sidecar — Changelog

## 2026-02-15: Full Improvement Pass

### Breaking: API response keys changed to snake_case

All camelCase response keys have been renamed to snake_case. The Next.js dashboard must be updated to match.

#### `/presence` (GET), `/health` → `presence`

| Before | After |
|---|---|
| `isPresent` | `is_present` |
| `lastSeen` | `last_seen` |
| `sensorOnline` | `sensor_online` |
| `motionType` | `motion_type` |
| `gpioAvailable` | `gpio_available` |
| `gpioPresent` | `gpio_present` |
| `postureAlert` | `posture_alert` |
| `tooCloseDuration` | `too_close_duration` |
| `debugMode` | `debug_mode` |
| `gateEnergies` | `gate_energies` |

#### `/presence/debug` (POST)

| Before | After |
|---|---|
| `debugMode` | `debug_mode` |

#### `/presence/posture/dismiss` (POST)

| Before | After |
|---|---|
| `postureAlert` | `posture_alert` |

#### `/led` (GET/POST), `/health` → `led`

| Before | After |
|---|---|
| `currentColor` | `color` |
| `currentMode` | `mode` |
| `currentBrightness` | `brightness` |

#### `/voice/status` (GET), `/health` → `voice`

| Before | After |
|---|---|
| `lastTranscript` | `last_transcript` |
| `ttsVolume` | `tts_volume` |
| `wakeWordDisabled` | `wake_word_disabled` |
| `capabilities.wakeWord` | `capabilities.wake_word` |

### Breaking: Stricter input validation

POST endpoints now reject invalid input with HTTP 400 instead of silently clamping values.

| Endpoint | Field | Valid range | Before | After |
|---|---|---|---|---|
| `POST /brightness` | `brightness` | 10–100 int | Clamped silently | 400 if out of range or non-integer |
| `POST /volume` | `volume` | 0–100 int | Clamped silently | 400 if out of range or non-integer |
| `POST /led` | `brightness` | 0–100 int | Clamped silently | 400 if out of range or non-integer |
| `POST /voice/volume` | `volume` | 0–100 int | Clamped silently | 400 if out of range or non-integer |
| `POST /voice/speak` | `text` | Non-empty, max 5000 chars | No length check | 400 if empty or too long |
| `POST /voice/listen` | `mode` | `"assistant"` or `"notes"` | Accepted anything | 400 if invalid |
| `POST /presence/debug` | `enable` | Boolean | Accepted truthy values | 400 if not boolean |

### Breaking: Controller errors now return proper HTTP status

| Endpoint | Condition | Before | After |
|---|---|---|---|
| `POST /voice/mock-wake` | Already processing | 200 with `{"error": "..."}` | 409 with `{"error": "..."}` |
| `POST /voice/listen` | Already processing | 200 with `{"error": "..."}` | 409 with `{"error": "..."}` |

### Changed: Error responses are always JSON

| Route | Before | After |
|---|---|---|
| Unknown path (404) | HTML error page | `{"error": "Not found"}` |
| Wrong HTTP method (405) | HTML error page | `{"error": "Method not allowed"}` |
| Server error (500) | HTML error page | `{"error": "Internal server error"}` |

### Unchanged endpoints

These endpoints have the same request/response format as before:

- `GET /health` (structure unchanged, nested objects use new keys above)
- `GET /brightness`
- `GET /volume`
- `GET /voice/volume`, `POST /voice/volume`
- `POST /voice/speak` (response body unchanged)
- `POST /voice/enable`
- `POST /voice/pause`
- `POST /voice/resume`
- `POST /voice/cancel`
- `POST /voice/clear-transcript`
- `POST /voice/stop-recording`

---

### Internal improvements (no API impact)

#### Crash fixes
- `volume.py`: `_run_amixer` now checks amixer exit code before parsing output
- `audio.py`: Added `threading.Lock` (`_state_lock`) protecting all shared fields read/written across threads
- `audio.py`: Added `clear_transcript()` method (replaces direct attribute assignment from `server.py`)
- `led.py`: Fixed animation thread race condition — each animation now gets a fresh `threading.Event` instead of reusing/clearing the old one

#### Infrastructure
- New `config.py`: All `os.environ.get()` calls and magic constants consolidated into one module
- New `log.py`: Stdlib `logging` replaces 70+ `print()` calls across all modules
- New `.env.example`: Documents all 15 environment variables

#### Shutdown
- Each controller cleanup wrapped in `try/except` so one failure doesn't skip the rest
- Backlight restored to 100% on shutdown
- Each cleanup step logged

#### Temp file cleanup
- `audio.py`: `os.unlink(temp_path)` moved to single `finally` block in `_transcribe` instead of scattered across `_transcribe_whisper` and `_transcribe_elevenlabs`

#### Code quality
- `import random` moved to module top in `led.py` and `presence.py`
- Regex patterns compiled at module level: `_ASCII_PATTERN` in `presence.py`, `_WAKE_WORD_PATTERNS` in `audio.py`

#### Dependencies
- `requirements.txt`: Core packages pinned to exact versions from working Pi environment

#### Testing
- New `test_endpoints.py`: 47 tests covering all 21 endpoints (validation, error handling, snake_case keys)
