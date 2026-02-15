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
from ui.text_utils import clean_response_text
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

        # Overlay state
        self._overlay_entry: Optional[ActivityEntry] = None
        self._overlay_scroll_offset = 0
        self._overlay_total_lines = 0

        # Streaming text state
        self._streaming_msg_id: Optional[str] = None
        self._streaming_text = ""

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

    def get_latest_activity(self) -> Optional[ActivityEntry]:
        """Get the most recent activity entry."""
        with self.lock:
            if self.activity_feed.entries:
                return self.activity_feed.entries[-1]
            return None

    def clear_activity_feed(self):
        """Clear all entries from the activity feed."""
        with self.lock:
            self.activity_feed.entries.clear()
            self._scroll_offset = 0

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

    def get_scroll_offset(self) -> int:
        """Get activity feed scroll offset."""
        with self.lock:
            return self._scroll_offset

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

    # === Overlay ===

    def show_overlay(self, entry: ActivityEntry):
        """Show fullscreen overlay for an activity entry."""
        with self.lock:
            self._overlay_entry = entry
            self._overlay_scroll_offset = 0
            self._overlay_total_lines = 0

    def dismiss_overlay(self):
        """Dismiss the fullscreen overlay."""
        with self.lock:
            self._overlay_entry = None

    def is_overlay_visible(self) -> bool:
        """Check if overlay is currently visible."""
        with self.lock:
            return self._overlay_entry is not None

    def scroll_overlay(self, delta: int):
        """Scroll the overlay content by delta lines."""
        with self.lock:
            if self._overlay_entry is None:
                return
            new_offset = self._overlay_scroll_offset + delta
            max_scroll = max(0, self._overlay_total_lines - 1)
            self._overlay_scroll_offset = max(0, min(new_offset, max_scroll))

    # === Streaming Text ===

    def append_streaming_text(self, msg_id: str, chunk: str):
        """Accumulate streaming text chunks."""
        with self.lock:
            if self._streaming_msg_id != msg_id:
                self._streaming_msg_id = msg_id
                self._streaming_text = ""
            self._streaming_text += chunk
            if len(self._streaming_text) > 2000:
                self._streaming_text = self._streaming_text[-2000:]

    def clear_streaming_text(self):
        """Clear streaming text state."""
        with self.lock:
            self._streaming_msg_id = None
            self._streaming_text = ""

    def is_streaming(self) -> bool:
        """Check if currently streaming text."""
        with self.lock:
            return self._streaming_msg_id is not None

    def find_activity_entry(self, x: int, y: int) -> Optional[ActivityEntry]:
        """Find the activity entry at the given tap coordinates."""
        layout = config.LAYOUT
        molty_panel_w = layout["molty_panel_width"]
        right_x = molty_panel_w
        right_w = self.width - molty_panel_w
        activity_h = self.height  # Full height

        # Activity feed bounds
        feed_x = right_x
        feed_y = 0
        feed_w = right_w

        # Entries start after activity header
        activity_header_h = layout["activity_header_height"]
        entries_y = feed_y + activity_header_h + 2
        entry_h = layout["activity_entry_height"]
        entries_area_h = activity_h - activity_header_h - 25

        # Check if tap is in the entries area
        if x < feed_x + 10 or x > feed_x + feed_w - 10:
            return None
        if y < entries_y or y > entries_y + entries_area_h:
            return None

        # Get visible entries (same logic as _draw_activity_feed)
        with self.lock:
            entries = list(self.activity_feed.entries)
            scroll_offset = self._scroll_offset

        max_visible = layout["activity_max_visible"]
        total = len(entries)
        if total == 0:
            return None

        max_scroll = max(0, total - max_visible)
        scroll_offset = max(0, min(scroll_offset, max_scroll))
        end_idx = total - scroll_offset
        start_idx = max(0, end_idx - max_visible)
        visible = list(reversed(entries[start_idx:end_idx]))

        # Find which entry was tapped
        ey = entries_y
        for entry in visible:
            if ey + entry_h > entries_y + entries_area_h:
                break
            if ey <= y < ey + entry_h:
                return entry
            ey += entry_h

        return None

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

        # Draw left panel (Molty + status + buttons)
        self._draw_left_panel(draw, image, 0, 0, molty_panel_w, self.height)

        # Draw right panel (activity feed - full height)
        right_x = molty_panel_w
        right_w = self.width - molty_panel_w
        self._draw_activity_feed(draw, right_x, 0, right_w, self.height)

        # Overlay (drawn on top of all panels)
        with self.lock:
            overlay_entry = self._overlay_entry
        if overlay_entry is not None:
            self._draw_overlay(draw, overlay_entry)

        # Scanlines effect
        self.theme.draw_scanlines(image, spacing=3, opacity=15)

        return image

    def _draw_left_panel(self, draw: ImageDraw.Draw, image: Image.Image,
                          x: int, y: int, width: int, height: int):
        """Draw the left panel with Molty, status, and buttons."""
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

        # Button panel (in left sidebar below state label)
        btn_panel_y = y + layout["button_panel_y_offset"]
        btn_panel_h = layout["button_panel_height"]
        self._draw_button_panel(draw, x, btn_panel_y, width, btn_panel_h)

        # Connection status bar (below buttons)
        status_y = btn_panel_y + btn_panel_h + 10
        self._draw_connection_bar(draw, x, status_y, width)

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
            streaming_active = self._streaming_msg_id is not None
            streaming_text = self._streaming_text if streaming_active else ""

        max_visible = layout["activity_max_visible"]

        # Reserve first slot for streaming entry if active
        slots_for_regular = max_visible - 1 if streaming_active else max_visible
        total = len(entries)

        if total > 0:
            max_scroll = max(0, total - slots_for_regular)
            scroll_offset = max(0, min(scroll_offset, max_scroll))
            end_idx = total - scroll_offset
            start_idx = max(0, end_idx - slots_for_regular)
            visible = list(reversed(entries[start_idx:end_idx]))
        else:
            visible = []

        entry_y = entries_y

        # Draw streaming entry first if active
        if streaming_active:
            self._draw_streaming_entry(draw, x + 10, entry_y, width - 20, entry_h - 5, streaming_text)
            entry_y += entry_h

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

        text_x = x + 12
        text_w = width - 40

        # Row 1: Title (small, type-colored) + Timestamp (right-aligned)
        title = self._truncate_text(entry.title, self._fonts["small"], text_w - 60)
        draw.text((text_x, y + 6), title, font=self._fonts["small"], fill=bar_color)

        time_str = entry.timestamp.strftime("%H:%M")
        time_bbox = self._fonts["mono"].getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text((x + width - 30 - time_w, y + 6), time_str,
                  font=self._fonts["mono"], fill=config.COLORS["text_dim"])

        # Row 2+3: Detail text (medium, white, word-wrapped up to 2 lines)
        if entry.detail:
            cleaned = clean_response_text(entry.detail)
            wrapped = self._word_wrap(cleaned, self._fonts["medium"], text_w)
            for i, line in enumerate(wrapped[:2]):
                if i == 1 and len(wrapped) > 2:
                    line = self._truncate_text(line, self._fonts["medium"], text_w)
                draw.text((text_x, y + 28 + i * 27), line,
                          font=self._fonts["medium"],
                          fill=config.COLORS["text_primary"])

    def _draw_streaming_entry(self, draw: ImageDraw.Draw, x: int, y: int,
                               width: int, height: int, text: str):
        """Draw a streaming text entry with purple bar and live text."""
        # Background
        draw.rectangle([x, y, x + width, y + height], fill=(20, 20, 28))

        # Purple color bar
        bar_color = config.COLORS["electric_purple"]
        draw.rectangle([x, y, x + 4, y + height], fill=bar_color)

        text_x = x + 12
        text_w = width - 40

        # Row 1: "Streaming..." label
        draw.text((text_x, y + 6), "Streaming...",
                  font=self._fonts["small"], fill=bar_color)

        # Pulsing dot
        pulse = int((time.time() * 3) % 2)
        if pulse:
            dot_x = x + width - 15
            dot_y = y + height // 2
            draw.ellipse([dot_x - 6, dot_y - 6, dot_x + 6, dot_y + 6],
                         fill=(*bar_color[:3], 60))
            draw.ellipse([dot_x - 3, dot_y - 3, dot_x + 3, dot_y + 3],
                         fill=bar_color)

        # Row 2+3: Last 2 lines of streamed text
        if text:
            cleaned = clean_response_text(text)
            wrapped = self._word_wrap(cleaned, self._fonts["medium"], text_w)
            # Show last 2 lines
            last_lines = wrapped[-2:] if len(wrapped) >= 2 else wrapped
            for i, line in enumerate(last_lines):
                line = self._truncate_text(line, self._fonts["medium"], text_w)
                draw.text((text_x, y + 28 + i * 27), line,
                          font=self._fonts["medium"],
                          fill=config.COLORS["text_primary"])

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
            "listening": {
                "bg": (25, 0, 35),
                "border": config.COLORS["electric_purple"],
                "text": config.COLORS["electric_purple"],
                "glow": True,
            },
        }

        # Auto-reset flash states
        flash_duration = config.TOUCH.get("button_flash_duration", 2.0)
        current_time = time.time()
        with self.lock:
            for btn_id, flash_time in list(self._button_flash_times.items()):
                state = self._button_states.get(btn_id)
                if state in ("success", "error") and current_time - flash_time > flash_duration:
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
        label_bbox = self._fonts["medium"].getbbox(label)
        label_w = label_bbox[2] - label_bbox[0]
        label_h = label_bbox[3] - label_bbox[1]
        label_x = x + (width - label_w) // 2
        label_y = y + (height - label_h) // 2 - 2

        draw.text((label_x, label_y), label, font=self._fonts["medium"], fill=style["text"])

    def _draw_connection_bar(self, draw: ImageDraw.Draw, x: int, y: int, width: int):
        """Draw connection status, model name, and API cost."""
        with self.lock:
            connected = self._connection_status
            model = self._model_name
            cost = self._api_cost

        padding = 12

        # Connection dot
        dot_color = config.COLORS["neon_green"] if connected else config.COLORS["neon_red"]
        dot_x = x + padding + 6
        dot_y = y + 8
        draw.ellipse([dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5], fill=dot_color)

        # ONLINE/OFFLINE text
        status_text = "ONLINE" if connected else "OFFLINE"
        draw.text((dot_x + 10, y + 1), status_text,
                  font=self._fonts["small"], fill=dot_color)

        # Model name (second row, truncated)
        if model:
            model_display = self._truncate_text(model, self._fonts["small"], width - 2 * padding)
            draw.text((x + padding, y + 22), model_display,
                      font=self._fonts["small"], fill=config.COLORS["text_dim"])

        # API cost (third row)
        if cost > 0:
            cost_str = f"${cost:.4f}"
            draw.text((x + padding, y + 42), cost_str,
                      font=self._fonts["mono"], fill=config.COLORS["text_dim"])

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

    def _word_wrap(self, text: str, font, max_width: int) -> List[str]:
        """Word-wrap text to fit within max_width pixels."""
        lines = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split(" ")
            current_line = ""
            for word in words:
                test = f"{current_line} {word}".strip() if current_line else word
                bbox = font.getbbox(test)
                if bbox[2] - bbox[0] <= max_width:
                    current_line = test
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
            if current_line:
                lines.append(current_line)
        return lines

    def _draw_overlay(self, draw: ImageDraw.Draw, entry: ActivityEntry):
        """Draw fullscreen overlay showing full entry content with scroll support."""
        # Dark background fill
        draw.rectangle([0, 0, self.width, self.height], fill=(5, 5, 10, 230))

        # Content panel with margins
        margin_x, margin_y = 60, 50
        panel_x1 = margin_x
        panel_y1 = margin_y
        panel_x2 = self.width - margin_x
        panel_y2 = self.height - margin_y

        # Panel background
        draw.rectangle([panel_x1, panel_y1, panel_x2, panel_y2], fill=(12, 12, 20))

        # Cyberpunk border
        self.theme.draw_panel_border(draw, (panel_x1, panel_y1, panel_x2, panel_y2))

        # Type color bar at top
        type_colors = {
            "tool": config.COLORS["neon_cyan"],
            "message": config.COLORS["hot_pink"],
            "status": config.COLORS["electric_purple"],
            "error": config.COLORS["neon_red"],
            "notification": config.COLORS["amber"],
        }
        bar_color = type_colors.get(entry.type, config.COLORS["neon_cyan"])
        draw.rectangle([panel_x1, panel_y1, panel_x2, panel_y1 + 4], fill=bar_color)

        # Content area
        content_x = panel_x1 + 25
        content_y = panel_y1 + 20
        content_w = (panel_x2 - panel_x1) - 50

        # Title with neon glow
        self.theme.draw_neon_text(
            draw, (content_x, content_y),
            entry.title,
            self._fonts["medium"],
            bar_color,
            glow_layers=1
        )

        # Timestamp right-aligned
        time_str = entry.timestamp.strftime("%H:%M:%S")
        time_bbox = self._fonts["mono"].getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text(
            (panel_x2 - 25 - time_w, content_y + 5),
            time_str,
            font=self._fonts["mono"],
            fill=config.COLORS["text_dim"]
        )

        # Separator line
        sep_y = content_y + 35
        draw.line([(content_x, sep_y), (panel_x2 - 25, sep_y)],
                  fill=config.COLORS["panel_border"], width=1)

        # Word-wrapped detail text with scroll support
        text_y = sep_y + 12
        line_height = 34
        max_text_y = panel_y2 - 55  # Leave room for hint
        visible_lines = max(1, (max_text_y - text_y) // line_height)

        if entry.detail:
            cleaned = clean_response_text(entry.detail)
            wrapped = self._word_wrap(cleaned, self._fonts["medium"], content_w)
            total_lines = len(wrapped)

            # Update total lines for scroll bounds
            with self.lock:
                self._overlay_total_lines = total_lines
                scroll_offset = self._overlay_scroll_offset
                # Clamp scroll offset
                max_scroll = max(0, total_lines - visible_lines)
                if scroll_offset > max_scroll:
                    self._overlay_scroll_offset = max_scroll
                    scroll_offset = max_scroll

            # Render windowed slice
            start_line = scroll_offset
            end_line = min(start_line + visible_lines, total_lines)
            for i, line in enumerate(wrapped[start_line:end_line]):
                draw.text((content_x, text_y + i * line_height), line,
                          font=self._fonts["medium"],
                          fill=config.COLORS["text_primary"])

            # Scroll indicators
            scrollable = total_lines > visible_lines
            if scrollable:
                indicator_x = panel_x2 - 20
                if scroll_offset > 0:
                    # Up arrow
                    draw.text((indicator_x, text_y), "^",
                              font=self._fonts["small"],
                              fill=config.COLORS["neon_cyan"])
                if scroll_offset < total_lines - visible_lines:
                    # Down arrow
                    draw.text((indicator_x, max_text_y - 20), "v",
                              font=self._fonts["small"],
                              fill=config.COLORS["neon_cyan"])

        # Hint at bottom
        with self.lock:
            scrollable = self._overlay_total_lines > visible_lines
        hint = "SWIPE / TAP TO CLOSE" if scrollable else "TAP TO CLOSE"
        hint_bbox = self._fonts["mono"].getbbox(hint)
        hint_w = hint_bbox[2] - hint_bbox[0]
        hint_x = (panel_x1 + panel_x2 - hint_w) // 2
        draw.text((hint_x, panel_y2 - 35), hint,
                  font=self._fonts["mono"],
                  fill=config.COLORS["text_dim"])

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
