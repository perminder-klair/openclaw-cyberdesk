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
}

# Presence-based Backlight
PRESENCE_BACKLIGHT = {
    "near_brightness": 255,       # Full brightness - at the display
    "medium_brightness": 200,     # Slightly dimmed - leaned back
    "far_brightness": 80,         # Dim - stepped away
    "away_brightness": 30,        # Very dim - not detected
    "poll_interval": 1.0,         # seconds
}

# Unified Layout (1280x720)
# ┌──────────────────────────────────────────────────────────────────────────────────────┐
# │  OPENCLAW                                                           12:34  WORKING   │  <- Header (60px)
# ├──────────────────────────┬───────────────────────────────────────────────────────────┤
# │                          │  ACTIVITY FEED                                             │
# │         MOLTY            │  ┌──────────────────────────────────────────────────────┐  │
# │        (180x180)         │  │ [cyan] Checked inbox - 3 urgent                14:23 │  │
# │                          │  │ [pink] Running backup...                       14:22 │  │
# │        [STATE]           │  └──────────────────────────────────────────────────────┘  │
# │                          ├───────────────────────────────────────────────────────────┤
# │      ● CONNECTED         │  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
# │      $0.0234             │  │  INBOX   │  │  BRIEF   │  │  QUEUE   │                 │
# │                          │  └──────────┘  └──────────┘  └──────────┘                 │
# │      ▌Status...          │  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
# │                          │  │  FOCUS   │  │  STATUS  │  │  RANDOM  │                 │
# └──────────────────────────┴──┴──────────┴──┴──────────┴──┴──────────┴─────────────────┘

LAYOUT = {
    # Overall structure
    "header_height": 60,
    "content_padding": 16,

    # Left panel (Molty + status)
    "molty_panel_width": 320,
    "molty_sprite_size": (180, 180),
    "molty_position_y": 90,   # Y offset from panel top
    "state_label_offset_y": 210,  # Y offset from panel top for state label
    "connection_status_y": 300,
    "cost_display_y": 338,
    "status_text_y": 390,

    # Right panel split
    "activity_feed_height_ratio": 0.55,  # 55% for activity feed
    "button_panel_height_ratio": 0.45,   # 45% for buttons

    # Activity feed
    "activity_header_height": 45,
    "activity_entry_height": 90,
    "activity_max_visible": 4,

    # Button grid (3x2)
    "button_cols": 3,
    "button_rows": 2,
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

# Button commands (same as original, but 3x2 grid)
BUTTONS = [
    {"id": "inbox", "label": "INBOX", "command": "Check inbox and summarize urgent items"},
    {"id": "brief", "label": "BRIEF", "command": "Give me a briefing of my day"},
    {"id": "queue", "label": "QUEUE", "command": "Execute next queued automation"},
    {"id": "focus", "label": "FOCUS", "command": "Activate focus mode"},
    {"id": "status", "label": "STATUS", "command": "Report your current status"},
    {"id": "random", "label": "RANDOM", "command": "Do something useful"},
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
