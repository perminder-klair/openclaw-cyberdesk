# Hardware Sidecar

Python Flask API that controls GPIO hardware on the Raspberry Pi. Serves as the backend for a Next.js dashboard UI.

## Components

| Module | Hardware | Interface |
|---|---|---|
| `led.py` | NeoPixel Stick (8 WS2812B) | GPIO10 (SPI MOSI) |
| `presence.py` | HMMD 24GHz mmWave radar | UART `/dev/ttyS0` + GPIO23 (OT2) |
| `audio.py` | WM8960 Audio HAT | I2S + I2C |
| `backlight.py` | Display backlight | `/sys/class/backlight/` |
| `volume.py` | WM8960 speakers | ALSA `amixer` |
| `config.py` | Centralized env vars and constants | - |
| `log.py` | Logging setup | stdlib `logging` |

## Setup

```bash
cd hardware
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `../.env` and edit. See that file for all available environment variables.

## Running

```bash
source venv/bin/activate
python server.py
```

## API Endpoints

All responses are JSON. Error responses use `{"error": "message"}`.

### Health

#### `GET /health`
Returns status of all controllers.

### Presence

#### `GET /presence`
Get current presence status.
```json
{
  "is_present": true,
  "distance": 75,
  "zone": "medium",
  "last_seen": "2025-12-26T14:30:00.000000",
  "sensor_online": true,
  "mock": false,
  "motion_type": "stationary",
  "gpio_available": true,
  "gpio_present": true,
  "posture_alert": false,
  "too_close_duration": null,
  "debug_mode": false,
  "gate_energies": null
}
```

#### `POST /presence/debug`
Toggle sensor debug mode.
```json
{ "enable": true }
```

#### `POST /presence/posture/dismiss`
Dismiss active posture alert.

### LED

#### `GET /led`
Get current LED status.
```json
{
  "color": "#FFF4E0",
  "mode": "static",
  "brightness": 100,
  "online": true,
  "mock": false
}
```

#### `POST /led`
Set LED color and mode.
```json
{
  "color": "#FFF4E0",
  "mode": "static",
  "brightness": 30
}
```
**Modes:** `static`, `pulse`, `flash`, `fade`, `breathe`, `rainbow`, `disco`, `chase`, `gradient`, `off`

### Brightness

#### `GET /brightness`
Get current screen brightness.

#### `POST /brightness`
Set screen brightness (10-100).
```json
{ "brightness": 75 }
```

### Volume

#### `GET /volume`
Get current system volume.

#### `POST /volume`
Set system volume (0-100) and/or mute state.
```json
{ "volume": 75, "muted": false }
```

### Voice

#### `GET /voice/status`
Get voice system state.
```json
{
  "state": "idle",
  "last_transcript": null,
  "error": null,
  "enabled": true,
  "tts_volume": 100,
  "mock": false,
  "capabilities": {
    "wake_word": true,
    "stt": true,
    "tts": true
  },
  "wake_word_disabled": false
}
```

#### `POST /voice/speak`
TTS playback (max 5000 chars).
```json
{ "text": "Good morning", "priority": 0 }
```

#### `POST /voice/enable`
Enable or disable voice system.
```json
{ "enabled": true }
```

#### `POST /voice/mock-wake`
Mock wake word trigger for testing.
```json
{ "transcript": "show news" }
```

#### `POST /voice/listen`
Start listening (bypass wake word). Mode: `assistant` (silence detection) or `notes` (manual stop).
```json
{ "mode": "assistant" }
```

#### `POST /voice/stop-recording`
Stop recording and transcribe (for notes mode).

#### `GET /voice/volume`
Get TTS volume.

#### `POST /voice/volume`
Set TTS volume (0-100).
```json
{ "volume": 75 }
```

#### `POST /voice/pause`
Pause wake word detection (during frontend TTS).

#### `POST /voice/resume`
Resume wake word detection (after frontend TTS).

#### `POST /voice/cancel`
Cancel current listening/processing.

#### `POST /voice/clear-transcript`
Clear the last transcript.

## Running as Service

```bash
sudo tee /etc/systemd/system/dashboard-hardware.service << 'EOF'
[Unit]
Description=Dashboard Hardware Sidecar
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/dashboard/hardware
ExecStart=/home/pi/dashboard/hardware/venv/bin/python server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dashboard-hardware
sudo systemctl start dashboard-hardware
```

## Mock Mode

When running on a non-Pi system, each controller automatically falls back to mock mode. Override mock presence for testing:
```
GET /presence?present=false
```

## LED States

| State | Color | Mode |
|-------|-------|------|
| Normal | Warm white `#FFF4E0` | Static |
| Meeting soon | Soft blue `#60A5FA` | Pulse |
| Meeting now | Blue `#3B82F6` | Static |
| Download complete | Green `#22C55E` | Flash |
| Server warning | Amber `#F59E0B` | Pulse |
| Critical alert | Red `#EF4444` | Pulse |
| Away | Off | Off |
| Idle | Warm white `#FFF4E0` | Breathe |
