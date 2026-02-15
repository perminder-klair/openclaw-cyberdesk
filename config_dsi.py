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
        "led_restore": "/led/restore",
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
    "near_brightness": 100,      # Full brightness - at the display
    "medium_brightness": 78,     # Slightly dimmed - leaned back
    "far_brightness": 31,        # Dim - stepped away
    "away_brightness": 12,       # Very dim - not detected
    "poll_interval": 1.0,         # seconds
}

# Unified Layout (1280x720) - No header, buttons in left panel
LAYOUT = {
    # Overall structure
    "header_height": 0,
    "top_bar_height": 38,
    "content_padding": 16,

    # Left panel (Molty + status + buttons)
    "molty_panel_width": 320,
    "molty_sprite_size": (110, 110),
    "molty_position_y": 16,
    "state_label_offset_y": 128,

    # Button panel in left sidebar
    "button_panel_y_offset": 170,
    "button_panel_height": 380,

    # Right panel (activity feed uses full height)
    "activity_feed_height_ratio": 1.0,

    # Activity feed
    "activity_header_height": 45,
    "activity_entry_height": 105,
    "activity_max_visible": 6,
    "activity_entry_gap": 6,

    # Button grid (2x4 in left panel)
    "button_cols": 2,
    "button_rows": 4,
    "button_gap": 10,
    "button_padding": 16,

    # Glass styling
    "button_radius": 10,
    "card_radius": 10,
    "panel_radius": 12,
}

# Font paths - Custom fonts with fallbacks
FONTS = {
    # Custom fonts
    "rajdhani_bold": "assets/fonts/Rajdhani-Bold.ttf",
    "rajdhani_semibold": "assets/fonts/Rajdhani-SemiBold.ttf",
    "inter": "assets/fonts/Inter-Regular.ttf",
    "jetbrains_mono": "assets/fonts/JetBrainsMono-Regular.ttf",

    # Fallback system fonts
    "default_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "bold_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "mono_path": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",

    # Size hierarchy
    "size_header_large": 38,
    "size_header": 30,
    "size_button": 26,
    "size_body": 22,
    "size_body_small": 18,
    "size_mono": 20,
    "size_mono_small": 16,

    # Legacy sizes (backward compat)
    "size_small": 21,
    "size_medium": 27,
    "size_large": 36,
    "size_title": 42,
}

# Color Scheme — Glassmorphism Dark
COLORS = {
    # Backgrounds
    "background": (14, 12, 22),
    "background_top": (14, 12, 22),
    "background_bottom": (10, 8, 18),
    "panel_bg": (18, 16, 28),
    "panel_border": (35, 32, 50),

    # Accent colors (softened neons)
    "accent_cyan": (70, 210, 230),
    "accent_pink": (230, 60, 120),
    "accent_purple": (160, 80, 220),

    # Status colors (softened)
    "status_amber": (235, 160, 40),
    "status_green": (60, 220, 120),
    "status_red": (220, 50, 70),

    # Text colors
    "text_primary": (230, 232, 245),
    "text_secondary": (140, 150, 175),
    "text_dim": (75, 85, 110),

    # Glass RGBA tints (used with alpha compositing)
    "glass_panel": (20, 18, 35, 160),
    "glass_button": (25, 22, 40, 180),
    "glass_card": (22, 20, 38, 160),
    "glass_border": (80, 75, 120, 80),
    "glass_border_glow": (80, 75, 120, 40),
    "glass_highlight": (255, 255, 255, 20),

    # Backward-compat aliases (old names → new values)
    "neon_cyan": (70, 210, 230),
    "hot_pink": (230, 60, 120),
    "electric_purple": (160, 80, 220),
    "amber": (235, 160, 40),
    "neon_green": (60, 220, 120),
    "neon_red": (220, 50, 70),

    # Activity type colors (use accent colors)
    "type_tool": (70, 210, 230),
    "type_message": (230, 60, 120),
    "type_status": (160, 80, 220),
    "type_error": (220, 50, 70),
    "type_notification": (235, 160, 40),

    # Button states
    "button_normal": (25, 22, 40),
    "button_border": (70, 210, 230),
    "button_pressed": (230, 60, 120),
    "button_running": (235, 160, 40),
    "button_success": (60, 220, 120),
    "button_error": (220, 50, 70),
}

# Button commands (2x4 grid in left panel)
BUTTONS = [
    {"id": "new_session", "label": "NEW", "command": "/new"},
    {"id": "voice", "label": "VOICE", "command": "__voice__"},
    {"id": "inbox", "label": "INBOX", "command": "Check inbox and summarize urgent items",
     "timeout": 45, "long_press_command": "Check inbox and list ALL items with full details"},
    {"id": "tasks", "label": "TASKS", "command": "Check my Vikunja tasks and list what needs to be done today",
     "timeout": 45, "long_press_command": "Check my Vikunja tasks and give a detailed breakdown of everything due this week"},
    {"id": "brief", "label": "BRIEF", "command": "Give me a briefing of my day", "timeout": 45},
    {"id": "focus", "label": "FOCUS", "command": "Activate focus mode"},
    {"id": "queue", "label": "QUEUE", "command": "Execute next queued automation"},
    {"id": "status", "label": "STATUS", "command": "Report your current status", "timeout": 10},
]

# Default command timeout in seconds
COMMAND_TIMEOUT = 45.0

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
    "button_flash_duration": 2.0,  # seconds for success/error flash
}

# Sprites
SPRITES = {
    "molty_dir": "assets/sprites",
}
