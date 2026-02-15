# Hardware Sidecar

Python Flask API that controls GPIO hardware on the Raspberry Pi.

## Components

- **HLK-LD2410** - mmWave presence sensor (UART)
- **NeoPixel Stick** - 8x WS2812B RGB LEDs (GPIO18)

## Wiring

```
Raspberry Pi GPIO Header
┌─────────────────────────────┐
│ Pin 2  (5V)    → NeoPixel VCC, LD2410 VCC
│ Pin 6  (GND)   → NeoPixel GND, LD2410 GND
│ Pin 8  (TXD)   → LD2410 RX
│ Pin 10 (RXD)   → LD2410 TX
│ Pin 12 (GPIO18)→ NeoPixel DIN
└─────────────────────────────┘
```

## Setup

```bash
cd hardware

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run server
python server.py
```

## API Endpoints

### GET /health
Check server status

### GET /presence
Get presence detection status
```json
{
  "isPresent": true,
  "distance": 75,
  "lastSeen": "2025-12-26T14:30:00.000Z",
  "sensorOnline": true
}
```

### GET /led
Get current LED status

### POST /led
Set LED color and mode
```json
{
  "color": "#FFF4E0",
  "mode": "static",
  "brightness": 30
}
```

**Modes:** `static`, `pulse`, `flash`, `fade`, `breathe`, `off`

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

When running on a non-Pi system (e.g., macOS for development), the sidecar automatically runs in mock mode:

- Presence is simulated as "present"
- LED commands are logged but not executed

Override mock presence for testing:
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
