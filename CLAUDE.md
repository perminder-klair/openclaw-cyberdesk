# OpenClaw CyberDeck - DSI Display Edition

Single 7" DSI touchscreen command center for Raspberry Pi 4 with unified cyberpunk UI.

## Hardware

### DSI Display (7" Touchscreen)
- Resolution: 1280x720 (auto-detected at runtime)
- Interface: DSI (Display Serial Interface)
- Touch: Integrated capacitive touch via Pygame/SDL2 events
- Rendering: PIL for graphics, converted to Pygame surface
- Frame rate: 30 FPS (configurable)

### Hardware Server Integration (Optional)
- Endpoint: http://localhost:5000
- LED control for status indication:
  - Idle: Dim blue (RGB 0,0,50)
  - Working: Amber pulse (RGB 255,170,0)
  - Success: Green flash (RGB 0,255,0)
  - Error: Red flash (RGB 255,0,0)
- Presence detection with proximity-based brightness control:
  - **Near** (<50cm): Brightness 255 - at the display
  - **Medium** (50-100cm): Brightness 200 - leaned back
  - **Far** (>100cm): Brightness 80 - stepped away
  - **Away** (not detected): Brightness 30 - very dim
- TTS voice support (optional)

### Display Layout

Unified 1280x720 screen, no header bar. Two panels:

**Left Panel (320px):**
- Molty character sprite (130x130)
- State indicator (IDLE/WORKING/LISTENING/THINKING/SUCCESS/ERROR)
- Connection status and API cost
- Command buttons: 2x3 grid (INBOX, BRIEF, QUEUE, FOCUS, STATUS, RANDOM)
- Status text at bottom

**Right Panel (960px):**
- Activity Feed (full height): Up to 7 recent activities with timestamps

## Hardware Server Endpoints

The display communicates with an optional hardware server at localhost:5000:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| /led | POST | LED control (r, g, b, mode, duration) |
| /presence | GET | Current presence zone (near/medium/far/away) |
| /brightness | POST | Set display brightness (0-255) |
| /voice/speak | POST | Text-to-speech (text, priority) |

LED modes: `static`, `pulse`, `flash`

Display gracefully degrades if hardware server is unavailable.

## Key Files

- `main_dsi.py` - Entry point for DSI display system
- `display_dsi.py` - Unified display renderer (Molty + activity feed + buttons)
- `touch_dsi.py` - Touch handler using Pygame events (tap, long press)
- `config_dsi.py` - DSI display and hardware server configuration
- `hardware_client.py` - HTTP client for LED and presence control
- `websocket_client.py` - OpenClaw WebSocket client with Ed25519 auth
- `openclaw_bridge.py` - Bridge between OpenClaw events and display updates
- `openclaw_config.py` - Configuration loader (.env + defaults)

## Touch Interaction

- **Tap**: Activate buttons, select activity entries for detail view
- **Long Press** (500ms): Cancel current operation or force reconnect
- **Connection Area Tap**: Tap connection/cost area in left panel to reconnect if disconnected
- **Molty Area Long Press**: Long press above buttons in left panel to force reconnect
- Debounce: 100ms

## Notes

- Screen resolution auto-detected at runtime (supports actual hardware resolution)
- Fullscreen mode by default (disable with `--windowed` flag)
- Pygame event-based touch handling (FINGERDOWN/FINGERUP or MOUSEBUTTONDOWN/UP)
- Hardware server runs separately - display gracefully degrades if unavailable

## OpenClaw WebSocket Protocol

### Connection Parameters

```python
{
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
        "id": "cli",
        "version": "1.0.0",
        "platform": "linux",
        "mode": "cli"
    },
    "role": "operator",
    "scopes": ["operator.read", "operator.write", "operator.admin"],
    "device": {
        "id": "<sha256-hex-of-public-key>",
        "publicKey": "<base64-ed25519-public-key>",
        "signature": "<base64-ed25519-signature>",
        "signedAt": <timestamp-ms>,
        "nonce": "<server-provided-nonce>"
    }
}
```

### Device Identity

- `device.id`: Full SHA-256 hex digest (64 chars) of the Ed25519 public key raw bytes
- `publicKey`: Base64-encoded raw Ed25519 public key (32 bytes)
- Keys stored in `~/.openclaw_display_keys.json`

### Signature Format

The signature signs a pipe-delimited auth payload:

```
v2|deviceId|clientId|clientMode|role|scopes|signedAt|token|nonce
```

Example:
```
v2|ac69e489...|cli|cli|operator|chat,sessions|1770151418248|mytoken|uuid-nonce
```

### Handshake Flow

1. Connect to WebSocket (e.g., `wss://hostname:18789`)
2. Server sends `connect.challenge` event with `nonce` and `ts`
3. Client builds auth payload, signs with Ed25519 private key
4. Client sends `connect` request with device object
5. Server validates signature and returns success or pairing request

### Key Files

- `websocket_client.py` - WebSocket client with OpenClaw protocol
- `openclaw_bridge.py` - Bridge interface for displays
- `openclaw_config.py` - Configuration loader
