"""
Configuration for OpenClaw CyberDeck DSI Display.
7" DSI touchscreen (1280x720) with unified layout.

Integrates with hardware server at localhost:5000 for:
- LED control (status indication)
- Presence detection (backlight dimming)
- Brightness control
"""

# DSI Display Configuration
DSI_DISPLAY = {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "fullscreen": True,
}

# Hardware Server Configuration
HARDWARE_SERVER = {
    "base_url": "http://localhost:5000",
    "timeout": 2.0,  # seconds
    "retry_delay": 1.0,
    "endpoints": {
        "led": "/led",
        "presence": "/presence",
        "brightness": "/brightness",
        "voice_speak": "/voice/speak",
        "voice_status": "/voice/status",
        "voice_listen": "/voice/listen",
        "voice_cancel": "/voice/cancel",
        "voice_clear": "/voice/clear-transcript",
    },
}

# LED Colors for States
LED_STATES = {
    "idle": {"r": 0, "g": 0, "b": 50},       # Dim blue
    "working": {"r": 255, "g": 170, "b": 0},  # Amber pulse
    "success": {"r": 0, "g": 255, "b": 0},    # Green flash
    "error": {"r": 255, "g": 0, "b": 0},      # Red flash
    "connected": {"r": 0, "g": 100, "b": 0},  # Dim green
    "disconnected": {"r": 50, "g": 0, "b": 0}, # Dim red
    "listening": {"r": 191, "g": 0, "b": 255},  # Purple
}

# Presence-based Backlight
PRESENCE_BACKLIGHT = {
    "near_brightness": 255,       # Full brightness - at the display
    "medium_brightness": 200,     # Slightly dimmed - leaned back
    "far_brightness": 80,         # Dim - stepped away
    "away_brightness": 30,        # Very dim - not detected
    "poll_interval": 1.0,         # seconds
}

# Unified Layout (1280x720) - No header, buttons in left panel
# ┌──────────────────────────┬──────────────────────────────────────────────────────────┐
# │                          │  ACTIVITY                                        14:32   │
# │    +─── 130x130 ───+    │ ─────────────────────────────────────────────────────────│
# │    │     MOLTY      │    │  [cyan] Checked inbox                          14:23    │
# │    +────────────────+    │  [pink] Running backup                         14:22    │
# │        "Ready"           │  [purple] Focus activated                      14:21    │
# │                          │  [amber] Reminder                              14:20    │
# │  +──────+ +──────+       │  [cyan] Status check                           14:19    │
# │  | INBOX| | BRIEF|       │  [red] Error detected                          14:18    │
# │  +──────+ +──────+       │  [cyan] System startup                         14:17    │
# │  +──────+ +──────+       │                                                          │
# │  | QUEUE| | FOCUS|       │                                                          │
# │  +──────+ +──────+       │                                                          │
# │  +──────+ +──────+       │                                                          │
# │  |STATUS| |VOICE |       │                                                          │
# │  +──────+ +──────+       │                                                          │
# │  +──────+ +──────+       │                                                          │
# │  | NEW  | |      |       │                                                          │
# │  +──────+ +──────+       │                                                          │
# └──────────────────────────┴──────────────────────────────────────────────────────────┘

LAYOUT = {
    # Overall structure
    "header_height": 0,
    "content_padding": 16,

    # Left panel (Molty + status + buttons)
    "molty_panel_width": 320,
    "molty_sprite_size": (130, 130),
    "molty_position_y": 8,   # Y offset from panel top
    "state_label_offset_y": 148,  # Y offset from panel top for state label
    # Button panel in left sidebar
    "button_panel_y_offset": 195,  # Where buttons start in left panel
    "button_panel_height": 336,

    # Right panel (activity feed uses full height)
    "activity_feed_height_ratio": 1.0,

    # Activity feed
    "activity_header_height": 45,
    "activity_entry_height": 105,
    "activity_max_visible": 6,

    # Button grid (2x4 in left panel)
    "button_cols": 2,
    "button_rows": 4,
    "button_gap": 16,
    "button_padding": 24,
}

# Font sizes (scaled for 7" 1280x720 display)
FONTS = {
    "default_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "bold_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "mono_path": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "size_small": 21,
    "size_medium": 27,
    "size_large": 36,
    "size_title": 42,
    "size_header": 30,
}

# Color Scheme (same as original)
COLORS = {
    "background": (10, 10, 15),
    "panel_bg": (15, 15, 25),
    "panel_border": (30, 30, 45),
    "neon_cyan": (0, 255, 255),
    "hot_pink": (255, 0, 102),
    "electric_purple": (191, 0, 255),
    "amber": (255, 170, 0),
    "neon_green": (0, 255, 102),
    "neon_red": (255, 0, 51),
    "text_primary": (238, 238, 255),
    "text_dim": (68, 119, 119),
    "text_secondary": (100, 150, 150),
}

# Button commands (2x4 grid in left panel)
BUTTONS = [
    {"id": "inbox", "label": "INBOX", "command": "Check inbox and summarize urgent items"},
    {"id": "brief", "label": "BRIEF", "command": "Give me a briefing of my day"},
    {"id": "queue", "label": "QUEUE", "command": "Execute next queued automation"},
    {"id": "focus", "label": "FOCUS", "command": "Activate focus mode"},
    {"id": "status", "label": "STATUS", "command": "Report your current status"},
    {"id": "voice", "label": "VOICE", "command": "__voice__"},
    {"id": "new_session", "label": "NEW", "command": "/new"},
]

# OpenClaw Connection (inherited from original config)
OPENCLAW = {
    "default_url": "ws://localhost:18789",
    "connection_timeout": 30.0,
    "reconnect_delay": 1.0,
    "max_reconnect_delay": 60.0,
    "auto_reconnect": True,
}

# Refresh rates
REFRESH = {
    "normal_fps": 30,
    "streaming_fps": 60,  # Higher FPS during streaming
    "idle_fps": 15,       # Lower FPS when idle (save power)
}

# Demo mode settings
DEMO = {
    "message_interval": 3.0,
    "status_change_interval": 2.0,
}

# Touch settings
TOUCH = {
    "debounce_ms": 100,
    "long_press_ms": 500,
    "tap_threshold_px": 15,  # Movement threshold to still count as tap
}

# Sprites
SPRITES = {
    "molty_dir": "assets/sprites",
}
