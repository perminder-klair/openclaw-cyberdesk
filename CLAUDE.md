# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hardware Sidecar — a Python Flask API that controls GPIO hardware (LEDs, presence sensor, audio/voice) on a Raspberry Pi. It serves as the backend for a Next.js dashboard UI running on the same device.

## Running the Project

```bash
source venv/bin/activate
python server.py
```

Environment variables are centralized in `config.py` (loaded from `../.env`). See `.env.example` for all available variables.

## Testing

```bash
# Run against live server (must be running on localhost:5000)
python test_endpoints.py

# Run against custom host
python test_endpoints.py http://host:port
```

47 endpoint tests covering all routes, validation, error handlers, and snake_case response format.

## Architecture

All hardware is abstracted into singleton controller modules, initialized at startup in `server.py`. Each module auto-detects whether it's running on a Pi and falls back to **mock mode** for local development.

| Module | Purpose | Key Detail |
|---|---|---|
| `config.py` | Centralized env vars and constants | Loads `../.env` via `python-dotenv`; imported by all modules |
| `log.py` | Logging setup | `setup_logging()` called once in `server.py`; `get_logger(name)` per module |
| `led.py` | NeoPixel Stick (8 WS2812B) on GPIO10 | Thread-based animations with per-animation stop events (fresh `threading.Event()` per animation) |
| `presence.py` | HMMD 24GHz mmWave radar via UART + GPIO23 | Dual protocol parsing (ASCII + binary); posture tracking alerts after 5min at <50cm |
| `audio.py` | WM8960 Audio HAT (I2S + I2C) | Wake word → STT → TTS pipeline; `_state_lock` protects all shared fields; `speak_lock` serializes TTS |
| `backlight.py` | Display backlight via `/sys/class/backlight/` | 10-100% range (minimum prevents black screen) |
| `volume.py` | WM8960 speakers via ALSA `amixer` | Checks amixer return codes; auto-detects sound card |

`server.py` exposes all controllers via Flask REST endpoints (CORS enabled) grouped under: `/health`, `/presence`, `/led`, `/brightness`, `/volume`, `/voice/*`.

## Key Patterns

- **Singletons**: Each controller uses `get_controller()` factory functions that return a cached instance.
- **Thread safety**: `audio.py` uses `_state_lock` for shared state, `speak_lock` for TTS serialization. `led.py` creates fresh `threading.Event` per animation to avoid race conditions.
- **Thread concurrency**: LED animations, UART polling (10Hz), and audio I/O each run in daemon threads.
- **Graceful degradation**: Every module independently detects missing hardware and switches to mock mode with logged warnings.
- **Audio feedback prevention**: Detection pauses during TTS, mic buffers are cleared after playback, 5-second cooldown between commands.
- **GPIO hybrid mode**: Presence uses both fast GPIO edge detection (OT2 pin) for instant response and UART for detailed distance/motion data.
- **Input validation**: All POST endpoints validate inputs via `_parse_int()` helper. Errors return 400 JSON.
- **API convention**: All response keys use snake_case. Error responses use `{"error": "message"}`.

## Service Management

```bash
sudo systemctl restart klair-hardware
sudo systemctl status klair-hardware
journalctl -u klair-hardware -f
```

## Hardware Wiring Reference

Detailed pinout and soldering guide in `docs/hardware-wiring-guide.md`. Key pins: GPIO10 (LED data), GPIO23 (presence OT2), UART TX/RX (pins 8/10), I2S/I2C (GPIO2/3/17/18/19/20/21 for audio HAT).
