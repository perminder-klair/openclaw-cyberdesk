# OpenClaw Display

A 7" DSI touchscreen command center for Raspberry Pi 4, designed as a physical dashboard for [OpenClaw](https://github.com/openclawai/openclaw) AI agents. Features a unified cyberpunk-themed UI with Molty the space lobster mascot, activity feed, and touch-enabled command buttons.

[![Watch the video](https://img.youtube.com/vi/Pq3205RoOsI/maxresdefault.jpg)](https://www.youtube.com/watch?v=Pq3205RoOsI)

> **Need a server for OpenClaw?** Launch your own instance with [Hostinger](https://www.hostinger.com/codingwithlewis)

![Main Display](preview_cyberpunk_main.png)
![Status Display](preview_cyberpunk_status.png)

## Parts List

| Part | Description | Qty |
|------|-------------|-----|
| Raspberry Pi 4 | Any RAM variant (2GB+) | 1 |
| 7" DSI Touchscreen | 1280x720 capacitive touch display with DSI ribbon cable | 1 |
| Micro SD card | 16GB+ with Raspberry Pi OS | 1 |
| USB-C power supply | 5V 3A for Raspberry Pi 4 | 1 |

**Optional Hardware Server Components:**
| Part | Description | Qty |
|------|-------------|-----|
| RGB LED | WS2812B or similar for status indication | 1 |
| VL53L0X Sensor | Time-of-Flight proximity sensor for presence detection | 1 |

The 7" DSI touchscreen connects directly to the Raspberry Pi's DSI port via ribbon cable. Look for "Raspberry Pi 7 inch Display" or compatible DSI touchscreens (many include official case mounting hardware).

**Hardware Server:** The optional LED and proximity sensor require a separate hardware server running at `localhost:5000`. The display gracefully degrades if the hardware server is unavailable.

## Wiring

### DSI Display Connection

The 7" DSI touchscreen connects to the Raspberry Pi 4 via:
1. **DSI ribbon cable** - connects to DSI port (between HDMI ports)
2. **Power jumpers** (optional) - 5V and GND from GPIO header to display board

No additional wiring required for display or touch functionality.

### Optional Hardware Server Components

If using the hardware server for LED status and presence detection:

**RGB LED (WS2812B/NeoPixel):**
| LED Pin | Pi GPIO | Pi Physical Pin |
|---------|---------|-----------------|
| VCC | 5V | 2 or 4 |
| GND | GND | 6 or 9 |
| DIN | GPIO 18 (PWM) | 12 |

**VL53L0X Proximity Sensor (I2C):**
| Sensor Pin | Pi Pin | Pi Physical Pin |
|------------|--------|-----------------|
| VCC | 3.3V | 1 or 17 |
| GND | GND | 6 or 9 |
| SDA | GPIO 2 (SDA1) | 3 |
| SCL | GPIO 3 (SCL1) | 5 |

### Assembly Tips

1. **Enable DSI Display:**
   - Connect DSI ribbon cable to Pi's DSI port
   - Boot the Pi - display should initialize automatically
   - If needed, configure in `/boot/config.txt` (usually auto-detected)

2. **Enable I2C** (if using hardware server):
   - Run `sudo raspi-config` → Interface Options → enable I2C

3. **Test Display:**
   - DSI display should show desktop after boot
   - Verify touch works by tapping desktop icons

4. **Optional Hardware Server:**
   - Set up hardware server with LED and/or proximity sensor
   - Run server on port 5000
   - Display will connect automatically if available

## Installation

```bash
git clone https://github.com/lewismenelaws/openclaw-display.git
cd openclaw-display

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example environment file and fill in your OpenClaw server details:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
OPENCLAW_URL=wss://your-server:18789
OPENCLAW_PASSWORD=your_password
OPENCLAW_AUTO_RECONNECT=true
```

## Usage

```bash
# Run the full display system (connects to OpenClaw)
python main_dsi.py

# Demo mode (no server connection required)
python main_dsi.py --demo

# Windowed mode (not fullscreen)
python main_dsi.py --windowed

# Custom OpenClaw URL
python main_dsi.py --url wss://your-server:18789
```

**Keyboard Controls:**
- `ESC` or `Q` - Exit application
- Touch interactions handled via touchscreen

## Running as a Service

To run the CyberDeck display automatically on boot:

### Initial Setup

1. **Enable user service persistence:**
   ```bash
   sudo loginctl enable-linger $USER
   ```

2. **Reload systemd and enable the service:**
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable openclaw-cyberdeck.service
   systemctl --user start openclaw-cyberdeck.service
   ```

### Service Management

Use the included helper script for quick control:

```bash
# Start the service
./service-control.sh start

# Stop the service
./service-control.sh stop

# Restart the service
./service-control.sh restart

# Check status
./service-control.sh status

# View live logs
./service-control.sh logs

# Disable auto-start
./service-control.sh disable

# Re-enable auto-start
./service-control.sh enable
```

Or use systemctl directly:

```bash
# Check if service is running
systemctl --user status openclaw-cyberdeck.service

# View logs (live tail)
journalctl --user -u openclaw-cyberdeck.service -f

# View last 100 log lines
journalctl --user -u openclaw-cyberdeck.service -n 100
```

### How It Works

- Service file located at: `~/.config/systemd/user/openclaw-cyberdeck.service`
- Starts automatically after graphical environment is ready
- Auto-restarts on failure (5 second delay)
- Handles graceful shutdown when stopped
- Logs to systemd journal (accessible via `journalctl`)

### Troubleshooting

**Service won't start:**
```bash
# Check for errors in logs
journalctl --user -u openclaw-cyberdeck.service -n 50

# Check if X11 display is available
echo $DISPLAY  # Should show :0

# Verify virtual environment exists
ls -la /home/klair/Projects/OpenClaw-CyberDeck/.venv/bin/python
```

**Service starts but display is black:**
- Check hardware connections
- Verify DSI display is connected and powered
- Run manually to see detailed errors: `./venv/bin/python main_dsi.py`

**Display shows black screen or "No signal":**
- Verify DSI ribbon cable is firmly seated in both connectors
- Check `/boot/config.txt` for display settings (usually auto-detected)
- Test with `tvservice -s` to see display status
- Try HDMI output first to verify Pi is booting

**Touch not working:**
- DSI touchscreens with capacitive touch work automatically via Pygame
- Check `dmesg | grep -i touch` for touch device detection
- Run `python main_dsi.py --demo --windowed` and try mouse clicks

**Hardware server not connecting:**
- Verify server is running: `curl http://localhost:5000/presence`
- Display works without hardware server (no LED/presence features)
- Check hardware server logs for I2C or GPIO errors

**Want to run manually while service is enabled:**
```bash
# Stop the service first to avoid conflicts
./service-control.sh stop

# Run manually
source .venv/bin/activate
python main_dsi.py

# Restart service when done
./service-control.sh start
```

## Architecture

| Module | Description |
|--------|-------------|
| `main_dsi.py` | Entry point - coordinates display, touch, and OpenClaw bridge |
| `display_dsi.py` | Unified display renderer (Molty + activity feed + command buttons) |
| `touch_dsi.py` | Touch handler using Pygame events (tap, long press detection) |
| `hardware_client.py` | HTTP client for hardware server (LED, presence, brightness) |
| `config_dsi.py` | DSI display and hardware server configuration |
| `websocket_client.py` | OpenClaw WebSocket client with Ed25519 authentication |
| `openclaw_bridge.py` | Bridge between OpenClaw events and display updates |
| `openclaw_config.py` | Configuration loader (.env + defaults) |
| `ui/` | UI components (activity feed, command panel, cyberpunk theme, Molty renderer) |

**Legacy Files (dual SPI version - not in active use):**
- `main.py`, `config.py`, `display_main.py`, `display_status.py`
- `touch_handler.py`, `rotary_handler.py`, `lcd_ticker.py`, `spi_lock.py`

## Hardware Server (Optional)

The DSI display can integrate with a hardware server for enhanced features:

**Features:**
- RGB LED status indication (idle/working/success/error states)
- VL53L0X proximity-based backlight dimming
- TTS voice notifications (optional)

**Setup:**
```bash
# Example setup (adjust to your hardware server implementation)
cd ~/Projects
git clone <your-hardware-server-repo>
cd hardware-server

# Install dependencies
pip install flask gpiozero adafruit-circuitpython-vl53l0x

# Run server
python server.py
```

**Endpoints:**
- `GET /presence` - Returns current proximity zone (near/medium/far/away)
- `POST /led` - Set LED color and mode (static/pulse/flash)
- `POST /brightness` - Set display brightness (0-255)
- `POST /voice/speak` - TTS output (requires pyttsx3 or espeak)

The display gracefully degrades if hardware server is unavailable.

## License

[MIT](LICENSE)
