"""
Unified Display Renderer for DSI 7" Touchscreen.
Combines Molty panel, activity feed, and command buttons into single view.
Uses PIL for rendering, converts to pygame surface for display.
"""

import threading
import time
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

import config_dsi as config
from ui.cyberpunk_theme import CyberpunkTheme, COLORS
from ui.molty import Molty, MoltyState
from ui.activity_feed import ActivityFeed, ActivityEntry
from touch_dsi import ButtonHitTester


class DSIDisplay:
    """
    Unified display renderer for DSI 7" touchscreen.
    Renders Molty panel, activity feed, and command buttons at actual screen resolution.
    """

    def __init__(self, demo_mode: bool = False, screen_size: Tuple[int, int] = None):
        self.demo_mode = demo_mode
        self.width = screen_size[0] if screen_size else config.DSI_DISPLAY["width"]
        self.height = screen_size[1] if screen_size else config.DSI_DISPLAY["height"]

        # UI components
        self.theme = CyberpunkTheme()
        self.molty = Molty(
            sprite_dir=config.SPRITES.get("molty_dir"),
            sprite_size=config.LAYOUT["molty_sprite_size"]
        )
        self.activity_feed = ActivityFeed(
            theme=self.theme,
            max_visible=config.LAYOUT["activity_max_visible"],
            entry_height=config.LAYOUT["activity_entry_height"]
        )
        self.button_tester = ButtonHitTester(screen_size=(self.width, self.height))

        # State
        self.lock = threading.Lock()
        self._status_text = "Waiting for commands..."
        self._connection_status = False
        self._model_name = ""
        self._api_cost = 0.0
        self._scroll_offset = 0

        # Button states
        self._button_states: Dict[str, str] = {}  # id -> state
        self._button_flash_times: Dict[str, float] = {}

        # Fonts (scaled for larger display)
        self._fonts = {}
        self._load_fonts()

        # Pre-rendered button rects
        self._button_rects = []

    def _load_fonts(self):
        """Load fonts at appropriate sizes for DSI display."""
        try:
            self._fonts["header"] = ImageFont.truetype(
                config.FONTS["bold_path"],
                config.FONTS["size_header"]
            )
            self._fonts["title"] = ImageFont.truetype(
                config.FONTS["bold_path"],
                config.FONTS["size_title"]
            )
            self._fonts["large"] = ImageFont.truetype(
                config.FONTS["bold_path"],
                config.FONTS["size_large"]
            )
            self._fonts["medium"] = ImageFont.truetype(
                config.FONTS["default_path"],
                config.FONTS["size_medium"]
            )
            self._fonts["small"] = ImageFont.truetype(
                config.FONTS["default_path"],
                config.FONTS["size_small"]
            )
            self._fonts["mono"] = ImageFont.truetype(
                config.FONTS["mono_path"],
                config.FONTS["size_small"]
            )
            self._fonts["mono_medium"] = ImageFont.truetype(
                config.FONTS["mono_path"],
                config.FONTS["size_medium"]
            )
        except (IOError, OSError):
            default = ImageFont.load_default()
            for key in ["header", "title", "large", "medium", "small", "mono", "mono_medium"]:
                self._fonts[key] = default

    # === State Setters ===

    def set_molty_state(self, state: MoltyState):
        """Set Molty's current state."""
        with self.lock:
            self.molty.set_state(state)

    def get_molty_state(self) -> MoltyState:
        """Get Molty's current state."""
        return self.molty.state

    def add_activity(self, type_: str, title: str, detail: str = "", status: str = "done"):
        """Add activity to feed."""
        with self.lock:
            self.activity_feed.add_entry(type_, title, detail, status)

    def update_latest_activity_status(self, status: str):
        """Update status of most recent activity."""
        with self.lock:
            self.activity_feed.update_latest_status(status)

    def set_status_text(self, text: str):
        """Set footer status text."""
        with self.lock:
            self._status_text = text

    def set_connection_status(self, connected: bool, model: str = "", cost: float = 0.0):
        """Set connection status display."""
        with self.lock:
            self._connection_status = connected
            self._model_name = model
            self._api_cost = cost

    def set_scroll_offset(self, offset: int):
        """Set activity feed scroll offset."""
        with self.lock:
            self._scroll_offset = max(0, offset)

    def set_button_state(self, button_id: str, state: str):
        """Set button visual state."""
        with self.lock:
            self._button_states[button_id] = state
            if state in ("pressed", "success", "error"):
                self._button_flash_times[button_id] = time.time()

    def reset_button(self, button_id: str):
        """Reset button to normal state."""
        self.set_button_state(button_id, "normal")

    def reset_all_buttons(self):
        """Reset all buttons to normal state."""
        with self.lock:
            self._button_states.clear()
            self._button_flash_times.clear()

    def find_button(self, x: int, y: int) -> Optional[dict]:
        """Find button at coordinates."""
        return self.button_tester.find_button(x, y)

    # === Rendering ===

    def render(self) -> Image.Image:
        """
        Render the complete unified display.

        Returns:
            PIL Image at screen resolution (RGB)
        """
        image = Image.new("RGB", (self.width, self.height), config.COLORS["background"])
        draw = ImageDraw.Draw(image, 'RGBA')

        layout = config.LAYOUT
        molty_panel_w = layout["molty_panel_width"]
        header_h = layout["header_height"]

        # Draw header
        self._draw_header(draw, 0, 0, self.width, header_h)

        # Draw left panel (Molty)
        self._draw_molty_panel(draw, image, 0, header_h, molty_panel_w, self.height - header_h)

        # Draw right panel (activity feed + buttons)
        right_x = molty_panel_w
        right_w = self.width - molty_panel_w
        content_h = self.height - header_h

        activity_h = int(content_h * layout["activity_feed_height_ratio"])
        button_h = content_h - activity_h

        # Activity feed
        self._draw_activity_feed(draw, right_x, header_h, right_w, activity_h)

        # Button panel
        self._draw_button_panel(draw, right_x, header_h + activity_h, right_w, button_h)

        # Scanlines effect
        self.theme.draw_scanlines(image, spacing=3, opacity=15)

        return image

    def _draw_header(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int):
        """Draw the header bar."""
        # Background
        draw.rectangle([x, y, x + width, y + height], fill=config.COLORS["panel_bg"])

        # Title
        self.theme.draw_neon_text(
            draw, (x + 15, y + 8),
            "OPENCLAW",
            self._fonts["title"],
            config.COLORS["neon_cyan"],
            glow_layers=1
        )

        # Timestamp
        time_str = datetime.now().strftime("%H:%M")
        time_bbox = self._fonts["mono_medium"].getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text(
            (x + width - time_w - 120, y + 10),
            time_str,
            font=self._fonts["mono_medium"],
            fill=config.COLORS["text_dim"]
        )

        # Current state label
        with self.lock:
            state_label = self.molty.get_state_label()
            state_color = self.molty.get_state_color()

        state_bbox = self._fonts["header"].getbbox(state_label)
        state_w = state_bbox[2] - state_bbox[0]
        self.theme.draw_neon_text(
            draw, (x + width - state_w - 15, y + 10),
            state_label.upper(),
            self._fonts["header"],
            state_color,
            glow_layers=1
        )

        # Bottom border
        draw.line(
            [(x, y + height - 1), (x + width, y + height - 1)],
            fill=config.COLORS["neon_cyan"],
            width=2
        )

    def _draw_molty_panel(self, draw: ImageDraw.Draw, image: Image.Image,
                          x: int, y: int, width: int, height: int):
        """Draw the left Molty panel."""
        layout = config.LAYOUT

        # Background
        draw.rectangle([x, y, x + width, y + height], fill=config.COLORS["panel_bg"])

        # Right border
        draw.line(
            [(x + width - 1, y), (x + width - 1, y + height)],
            fill=config.COLORS["panel_border"],
            width=1
        )

        # Molty character (centered horizontally)
        sprite_w, sprite_h = layout["molty_sprite_size"]
        molty_x = x + (width - sprite_w) // 2
        molty_y = y + layout["molty_position_y"]

        with self.lock:
            self.molty.render(image, (molty_x, molty_y))
            state_label = self.molty.get_state_label()
            state_color = self.molty.get_state_color()

        # State label
        label_bbox = self._fonts["large"].getbbox(state_label)
        label_w = label_bbox[2] - label_bbox[0]
        label_x = x + (width - label_w) // 2
        label_y = y + layout["state_label_offset_y"]

        self.theme.draw_neon_text(
            draw, (label_x, label_y),
            state_label,
            self._fonts["large"],
            state_color,
            glow_layers=1
        )

        # Connection status
        status_y = y + layout["connection_status_y"]
        with self.lock:
            connected = self._connection_status
            model = self._model_name
            cost = self._api_cost

        # Status dot
        dot_color = config.COLORS["neon_green"] if connected else config.COLORS["neon_red"]
        dot_x = x + 20
        dot_y = status_y + 8

        # Glow
        draw.ellipse([dot_x - 6, dot_y - 6, dot_x + 6, dot_y + 6],
                     fill=(*dot_color[:3], 60))
        draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4],
                     fill=dot_color)

        # Status text
        status_text = "CONNECTED" if connected else "DISCONNECTED"
        draw.text((dot_x + 12, status_y),
                  status_text,
                  font=self._fonts["small"],
                  fill=config.COLORS["text_primary"] if connected else config.COLORS["text_dim"])

        # Cost display
        cost_y = y + layout["cost_display_y"]
        cost_text = f"${cost:.4f}"
        cost_color = config.COLORS["neon_green"] if cost < 1.0 else config.COLORS["neon_red"]
        draw.text((x + 20, cost_y),
                  cost_text,
                  font=self._fonts["mono_medium"],
                  fill=cost_color)

        # Status text
        footer_y = y + layout["status_text_y"]
        with self.lock:
            status_text = self._status_text

        # Cursor block
        draw.rectangle([x + 15, footer_y + 2, x + 19, footer_y + 16],
                       fill=config.COLORS["neon_cyan"])

        # Truncate status text
        max_status_w = width - 30
        truncated = self._truncate_text(status_text, self._fonts["small"], max_status_w)
        draw.text((x + 25, footer_y),
                  truncated,
                  font=self._fonts["small"],
                  fill=config.COLORS["text_secondary"])

        # Corner accents
        self._draw_corner_accents(draw, x + 5, y + 5, width - 10, height - 10)

    def _draw_activity_feed(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int):
        """Draw the activity feed panel."""
        layout = config.LAYOUT

        # Background
        draw.rectangle([x, y, x + width, y + height], fill=config.COLORS["panel_bg"])

        # Header
        header_h = layout["activity_header_height"]
        draw.text((x + 15, y + 6),
                  "ACTIVITY",
                  font=self._fonts["header"],
                  fill=config.COLORS["neon_cyan"])

        # Timestamp
        time_str = datetime.now().strftime("%H:%M:%S")
        time_bbox = self._fonts["mono"].getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text((x + width - time_w - 15, y + 8),
                  time_str,
                  font=self._fonts["mono"],
                  fill=config.COLORS["text_dim"])

        # Header separator
        draw.line([(x, y + header_h - 1), (x + width, y + header_h - 1)],
                  fill=config.COLORS["neon_cyan"], width=1)

        # Entries area
        entry_h = layout["activity_entry_height"]
        entries_y = y + header_h + 2
        entries_area_h = height - header_h - 25  # Leave room for footer

        with self.lock:
            entries = list(self.activity_feed.entries)
            scroll_offset = self._scroll_offset

        max_visible = layout["activity_max_visible"]
        total = len(entries)

        if total > 0:
            max_scroll = max(0, total - max_visible)
            scroll_offset = max(0, min(scroll_offset, max_scroll))
            end_idx = total - scroll_offset
            start_idx = max(0, end_idx - max_visible)
            visible = list(reversed(entries[start_idx:end_idx]))
        else:
            visible = []

        entry_y = entries_y
        for entry in visible:
            if entry_y + entry_h > entries_y + entries_area_h:
                break
            self._draw_activity_entry(draw, entry, x + 10, entry_y, width - 20, entry_h - 5)
            entry_y += entry_h

        # Bottom border
        draw.line([(x, y + height - 1), (x + width, y + height - 1)],
                  fill=config.COLORS["panel_border"], width=1)

    def _draw_activity_entry(self, draw: ImageDraw.Draw, entry: ActivityEntry,
                             x: int, y: int, width: int, height: int):
        """Draw a single activity entry."""
        # Type colors
        type_colors = {
            "tool": config.COLORS["neon_cyan"],
            "message": config.COLORS["hot_pink"],
            "status": config.COLORS["electric_purple"],
            "error": config.COLORS["neon_red"],
            "notification": config.COLORS["amber"],
        }
        status_colors = {
            "done": config.COLORS["neon_green"],
            "running": config.COLORS["amber"],
            "fail": config.COLORS["neon_red"],
        }

        # Background
        draw.rectangle([x, y, x + width, y + height], fill=(20, 20, 28))

        # Color bar
        bar_color = type_colors.get(entry.type, config.COLORS["neon_cyan"])
        draw.rectangle([x, y, x + 4, y + height], fill=bar_color)

        # Status dot
        status_color = status_colors.get(entry.status, config.COLORS["text_dim"])
        dot_x = x + width - 15
        dot_y = y + height // 2

        if entry.status == "running":
            draw.ellipse([dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8],
                         fill=(*status_color[:3], 60))

        draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=status_color)

        # Title
        text_x = x + 12
        text_w = width - 40
        title = self._truncate_text(entry.title, self._fonts["medium"], text_w)
        draw.text((text_x, y + 5), title, font=self._fonts["medium"],
                  fill=config.COLORS["text_primary"])

        # Detail
        if entry.detail:
            detail = self._truncate_text(entry.detail, self._fonts["small"], text_w)
            draw.text((text_x, y + 25), detail, font=self._fonts["small"],
                      fill=config.COLORS["text_dim"])

        # Timestamp
        time_str = entry.timestamp.strftime("%H:%M")
        draw.text((text_x, y + height - 18), time_str, font=self._fonts["mono"],
                  fill=config.COLORS["text_dim"])

    def _draw_button_panel(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int):
        """Draw the command button panel."""
        layout = config.LAYOUT
        padding = layout["button_padding"]
        gap = layout["button_gap"]
        cols = layout["button_cols"]
        rows = layout["button_rows"]

        # Calculate button sizes
        usable_w = width - 2 * padding - (cols - 1) * gap
        usable_h = height - 2 * padding - (rows - 1) * gap
        btn_w = usable_w // cols
        btn_h = usable_h // rows

        # Button state colors
        state_colors = {
            "normal": {
                "bg": (20, 20, 30),
                "border": config.COLORS["neon_cyan"],
                "text": config.COLORS["text_primary"],
                "glow": False,
            },
            "pressed": {
                "bg": (40, 0, 25),
                "border": config.COLORS["hot_pink"],
                "text": config.COLORS["hot_pink"],
                "glow": True,
            },
            "running": {
                "bg": (30, 25, 0),
                "border": config.COLORS["amber"],
                "text": config.COLORS["amber"],
                "glow": True,
            },
            "success": {
                "bg": (0, 30, 15),
                "border": config.COLORS["neon_green"],
                "text": config.COLORS["neon_green"],
                "glow": True,
            },
            "error": {
                "bg": (30, 0, 0),
                "border": config.COLORS["neon_red"],
                "text": config.COLORS["neon_red"],
                "glow": True,
            },
        }

        # Auto-reset flash states
        current_time = time.time()
        with self.lock:
            for btn_id, flash_time in list(self._button_flash_times.items()):
                state = self._button_states.get(btn_id)
                if state in ("success", "error") and current_time - flash_time > 1.0:
                    self._button_states[btn_id] = "normal"

        # Draw each button
        for i, btn_def in enumerate(config.BUTTONS):
            col = i % cols
            row = i // cols

            btn_x = x + padding + col * (btn_w + gap)
            btn_y = y + padding + row * (btn_h + gap)

            with self.lock:
                state = self._button_states.get(btn_def["id"], "normal")

            style = state_colors.get(state, state_colors["normal"])
            self._draw_button(draw, btn_x, btn_y, btn_w, btn_h, btn_def["label"], style)

    def _draw_button(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int,
                     label: str, style: dict):
        """Draw a single button."""
        # Background
        draw.rectangle([x, y, x + width, y + height], fill=style["bg"])

        # Glow effect
        if style["glow"]:
            for glow_offset in range(3, 0, -1):
                glow_alpha = 30 * glow_offset
                draw.rectangle(
                    [x - glow_offset, y - glow_offset,
                     x + width + glow_offset, y + height + glow_offset],
                    outline=(*style["border"][:3], glow_alpha),
                    width=1
                )

        # Border
        draw.rectangle([x, y, x + width, y + height], outline=style["border"], width=2)

        # Corner accents
        accent_len = 8
        corners = [
            (x, y, x + accent_len, y),
            (x, y, x, y + accent_len),
            (x + width - accent_len, y, x + width, y),
            (x + width, y, x + width, y + accent_len),
            (x, y + height - accent_len, x, y + height),
            (x, y + height, x + accent_len, y + height),
            (x + width - accent_len, y + height, x + width, y + height),
            (x + width, y + height - accent_len, x + width, y + height),
        ]
        for i in range(0, len(corners), 2):
            draw.line([corners[i][:2], corners[i][2:4]], fill=style["border"], width=3)
            draw.line([corners[i+1][:2], corners[i+1][2:4]], fill=style["border"], width=3)

        # Label
        label_bbox = self._fonts["large"].getbbox(label)
        label_w = label_bbox[2] - label_bbox[0]
        label_h = label_bbox[3] - label_bbox[1]
        label_x = x + (width - label_w) // 2
        label_y = y + (height - label_h) // 2 - 2

        draw.text((label_x, label_y), label, font=self._fonts["large"], fill=style["text"])

    def _draw_corner_accents(self, draw: ImageDraw.Draw, x: int, y: int, width: int, height: int):
        """Draw corner accent marks."""
        accent_len = 12
        color = config.COLORS["neon_cyan"]

        # Top-left
        draw.line([(x, y), (x + accent_len, y)], fill=color, width=2)
        draw.line([(x, y), (x, y + accent_len)], fill=color, width=2)

        # Bottom-left
        draw.line([(x, y + height), (x + accent_len, y + height)], fill=color, width=2)
        draw.line([(x, y + height - accent_len), (x, y + height)], fill=color, width=2)

    def _truncate_text(self, text: str, font, max_width: int) -> str:
        """Truncate text to fit within max_width."""
        if not text:
            return ""

        bbox = font.getbbox(text)
        if bbox[2] - bbox[0] <= max_width:
            return text

        for i in range(len(text), 0, -1):
            truncated = text[:i] + "..."
            bbox = font.getbbox(truncated)
            if bbox[2] - bbox[0] <= max_width:
                return truncated

        return "..."

    # === Pygame Integration ===

    def render_to_surface(self) -> 'pygame.Surface':
        """
        Render to pygame surface.

        Returns:
            pygame.Surface ready for display
        """
        if not PYGAME_AVAILABLE:
            raise RuntimeError("Pygame not available")

        pil_image = self.render()

        # Convert PIL image to pygame surface
        # PIL is RGB, pygame expects same
        raw_data = pil_image.tobytes()
        surface = pygame.image.fromstring(raw_data, pil_image.size, 'RGB')

        return surface

    def cleanup(self):
        """Clean up resources."""
        print("[Display DSI] Cleanup complete")
