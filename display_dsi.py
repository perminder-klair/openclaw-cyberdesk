"""
Unified Display Renderer for DSI 7" Touchscreen.
Combines Molty panel, activity feed, and command buttons into single view.
Uses PIL for rendering, converts to pygame surface for display.

Glassmorphism dark theme: frosted glass panels, rounded corners,
soft neon glows, gradient background, scanline overlay.
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
from ui.glass_theme import GlassRenderer
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

        # Glass renderer (pre-renders gradient, scanlines, loads fonts)
        self.glass = GlassRenderer(self.width, self.height)

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
        self._button_states: Dict[str, str] = {}
        self._button_flash_times: Dict[str, float] = {}

        # Fonts from glass renderer
        self._fonts = self.glass._fonts

        # Overlay state
        self._overlay_entry: Optional[ActivityEntry] = None
        self._overlay_scroll_offset = 0
        self._overlay_total_lines = 0

        # Streaming text state
        self._streaming_msg_id: Optional[str] = None
        self._streaming_text = ""

        # Pre-rendered button rects
        self._button_rects = []

    # === State Setters ===

    def set_molty_state(self, state: MoltyState):
        with self.lock:
            self.molty.set_state(state)

    def get_molty_state(self) -> MoltyState:
        return self.molty.state

    def add_activity(self, type_: str, title: str, detail: str = "", status: str = "done"):
        with self.lock:
            self.activity_feed.add_entry(type_, title, detail, status)

    def update_latest_activity_status(self, status: str):
        with self.lock:
            self.activity_feed.update_latest_status(status)

    def get_latest_activity(self) -> Optional[ActivityEntry]:
        with self.lock:
            if self.activity_feed.entries:
                return self.activity_feed.entries[-1]
            return None

    def clear_activity_feed(self):
        with self.lock:
            self.activity_feed.entries.clear()
            self._scroll_offset = 0

    def set_status_text(self, text: str):
        with self.lock:
            self._status_text = text

    def set_connection_status(self, connected: bool, model: str = "", cost: float = 0.0):
        with self.lock:
            self._connection_status = connected
            self._model_name = model
            self._api_cost = cost

    def set_scroll_offset(self, offset: int):
        with self.lock:
            self._scroll_offset = max(0, offset)

    def get_scroll_offset(self) -> int:
        with self.lock:
            return self._scroll_offset

    def set_button_state(self, button_id: str, state: str):
        with self.lock:
            self._button_states[button_id] = state
            if state in ("pressed", "success", "error"):
                self._button_flash_times[button_id] = time.time()

    def reset_button(self, button_id: str):
        self.set_button_state(button_id, "normal")

    def reset_all_buttons(self):
        with self.lock:
            self._button_states.clear()
            self._button_flash_times.clear()

    def find_button(self, x: int, y: int) -> Optional[dict]:
        return self.button_tester.find_button(x, y)

    # === Overlay ===

    def show_overlay(self, entry: ActivityEntry):
        with self.lock:
            self._overlay_entry = entry
            self._overlay_scroll_offset = 0
            self._overlay_total_lines = 0

    def dismiss_overlay(self):
        with self.lock:
            self._overlay_entry = None

    def is_overlay_visible(self) -> bool:
        with self.lock:
            return self._overlay_entry is not None

    def scroll_overlay(self, delta: int):
        with self.lock:
            if self._overlay_entry is None:
                return
            new_offset = self._overlay_scroll_offset + delta
            max_scroll = max(0, self._overlay_total_lines - 1)
            self._overlay_scroll_offset = max(0, min(new_offset, max_scroll))

    # === Streaming Text ===

    def append_streaming_text(self, msg_id: str, chunk: str):
        with self.lock:
            if self._streaming_msg_id != msg_id:
                self._streaming_msg_id = msg_id
                self._streaming_text = ""
            self._streaming_text += chunk
            if len(self._streaming_text) > 2000:
                self._streaming_text = self._streaming_text[-2000:]

    def clear_streaming_text(self):
        with self.lock:
            self._streaming_msg_id = None
            self._streaming_text = ""

    def is_streaming(self) -> bool:
        with self.lock:
            return self._streaming_msg_id is not None

    def find_activity_entry(self, x: int, y: int) -> Optional[ActivityEntry]:
        layout = config.LAYOUT
        molty_panel_w = layout["molty_panel_width"]
        right_x = molty_panel_w
        right_w = self.width - molty_panel_w

        feed_x = right_x
        activity_header_h = layout["activity_header_height"]
        entries_y = feed_x and (0 + activity_header_h + 2)
        entry_h = layout["activity_entry_height"]
        entries_area_h = self.height - activity_header_h - 25

        if x < feed_x + 10 or x > feed_x + right_w - 10:
            return None
        if y < entries_y or y > entries_y + entries_area_h:
            return None

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

        entry_gap = layout.get("activity_entry_gap", 6)
        ey = entries_y
        for entry in visible:
            if ey + entry_h > entries_y + entries_area_h:
                break
            if ey <= y < ey + entry_h:
                return entry
            ey += entry_h + entry_gap

        return None

    # === Rendering ===

    def render(self) -> Image.Image:
        """
        Render the complete unified display.
        Returns PIL Image at screen resolution (RGB).
        """
        layout = config.LAYOUT
        molty_panel_w = layout["molty_panel_width"]

        # 1. Compose frame: gradient bg + frosted panel areas (RGB)
        frame = self.glass.compose_frame(molty_panel_w)
        draw = ImageDraw.Draw(frame)

        # 2. Draw left panel content
        self._draw_left_panel(draw, frame, 0, 0, molty_panel_w, self.height)

        # 3. Draw right panel content (activity feed)
        right_x = molty_panel_w
        right_w = self.width - molty_panel_w
        self._draw_activity_feed(draw, right_x, 0, right_w, self.height)

        # 4. Overlay (drawn on top of all panels)
        with self.lock:
            overlay_entry = self._overlay_entry
        if overlay_entry is not None:
            self._draw_overlay(draw, frame, overlay_entry)

        # 5. Scanlines
        self.glass.apply_scanlines(frame)

        return frame

    def _draw_left_panel(self, draw: ImageDraw.Draw, image: Image.Image,
                          x: int, y: int, width: int, height: int):
        """Draw the left panel with Molty, status, and buttons."""
        layout = config.LAYOUT

        # Molty character (centered horizontally)
        sprite_w, sprite_h = layout["molty_sprite_size"]
        molty_x = x + (width - sprite_w) // 2
        molty_y = y + layout["molty_position_y"]

        # Glass platform behind Molty (tinted with state color)
        with self.lock:
            state_color = self.molty.get_state_color()

        platform_pad = 12
        platform_bbox = (
            molty_x - platform_pad,
            molty_y - platform_pad // 2,
            molty_x + sprite_w + platform_pad,
            molty_y + sprite_h + platform_pad // 2,
        )
        platform_fill = (state_color[0] // 12, state_color[1] // 12, state_color[2] // 12)
        platform_border = tuple(c // 4 for c in state_color[:3])
        self.glass.draw_rounded_rect(draw, platform_bbox, radius=12,
                                      fill=platform_fill, outline=platform_border)

        with self.lock:
            self.molty.render(image, (molty_x, molty_y))
            state_label = self.molty.get_state_label()
            state_color = self.molty.get_state_color()

        # State label with soft glow
        label_font = self._fonts["header"]
        label_w, _ = self.glass.get_text_size(state_label, label_font)
        label_x = x + (width - label_w) // 2
        label_y = y + layout["state_label_offset_y"]

        self.glass.draw_soft_glow_text(
            draw, (label_x, label_y),
            state_label, label_font, state_color
        )

        # Button panel
        btn_panel_y = y + layout["button_panel_y_offset"]
        btn_panel_h = layout["button_panel_height"]
        self._draw_button_panel(draw, x, btn_panel_y, width, btn_panel_h)

        # Connection bar (below buttons) in a glass card
        status_y = btn_panel_y + btn_panel_h + 8
        self._draw_connection_bar(draw, x, status_y, width)

    def _draw_activity_feed(self, draw: ImageDraw.Draw, x: int, y: int,
                            width: int, height: int):
        """Draw the activity feed panel."""
        layout = config.LAYOUT

        # Header
        header_h = layout["activity_header_height"]
        header_font = self._fonts["header"]
        draw.text((x + 18, y + 8), "ACTIVITY", font=header_font,
                  fill=config.COLORS["accent_cyan"])

        # Timestamp (use fixed-width estimate for monospace)
        time_str = datetime.now().strftime("%H:%M:%S")
        time_font = self._fonts["mono_small"]
        time_w, _ = self.glass.get_text_size("00:00:00", time_font)
        draw.text((x + width - time_w - 18, y + 12), time_str,
                  font=time_font, fill=config.COLORS["text_dim"])

        # Soft divider line (dimmed cyan)
        divider_color = tuple(c // 4 for c in config.COLORS["accent_cyan"][:3])
        draw.line([(x + 15, y + header_h - 1), (x + width - 15, y + header_h - 1)],
                  fill=divider_color, width=1)

        # Entries area
        entry_h = layout["activity_entry_height"]
        entry_gap = layout.get("activity_entry_gap", 6)
        entries_y = y + header_h + 4
        entries_area_h = height - header_h - 25

        with self.lock:
            entries = list(self.activity_feed.entries)
            scroll_offset = self._scroll_offset
            streaming_active = self._streaming_msg_id is not None
            streaming_text = self._streaming_text if streaming_active else ""

        max_visible = layout["activity_max_visible"]
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

        # Streaming entry first
        if streaming_active:
            self._draw_streaming_entry(draw, x + 12, entry_y,
                                       width - 24, entry_h - entry_gap,
                                       streaming_text)
            entry_y += entry_h

        for entry in visible:
            if entry_y + entry_h > entries_y + entries_area_h:
                break
            self._draw_activity_entry(draw, entry, x + 12, entry_y,
                                      width - 24, entry_h - entry_gap)
            entry_y += entry_h

    def _draw_activity_entry(self, draw: ImageDraw.Draw, entry: ActivityEntry,
                             x: int, y: int, width: int, height: int):
        """Draw a single activity entry as a glass card."""
        type_colors = {
            "tool": config.COLORS["accent_cyan"],
            "message": config.COLORS["accent_pink"],
            "status": config.COLORS["accent_purple"],
            "error": config.COLORS["status_red"],
            "notification": config.COLORS["status_amber"],
        }
        status_colors = {
            "done": config.COLORS["status_green"],
            "running": config.COLORS["status_amber"],
            "fail": config.COLORS["status_red"],
        }

        bar_color = type_colors.get(entry.type, config.COLORS["accent_cyan"])
        radius = config.LAYOUT.get("card_radius", 10)

        # Glass card background
        self.glass.draw_glass_card(draw, (x, y, x + width, y + height),
                                    accent_color=bar_color, radius=radius)

        # Status dot
        status_color = status_colors.get(entry.status, config.COLORS["text_dim"])
        dot_x = x + width - 18
        dot_y = y + height // 2

        if entry.status == "running":
            dim = tuple(c // 4 for c in status_color[:3])
            draw.ellipse([dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8], fill=dim)
        draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4],
                     fill=status_color)

        text_x = x + 14
        text_w = width - 44

        # Row 1: Title (body_small, type-colored) + Timestamp
        title_font = self._fonts["body_small"]
        title = self._truncate_text(entry.title, title_font, text_w - 60)
        draw.text((text_x, y + 8), title, font=title_font, fill=bar_color)

        time_str = entry.timestamp.strftime("%H:%M")
        time_font = self._fonts["mono_small"]
        time_bbox = time_font.getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text((x + width - 34 - time_w, y + 8), time_str,
                  font=time_font, fill=config.COLORS["text_dim"])

        # Row 2+3: Detail text (body font, primary color)
        if entry.detail:
            body_font = self._fonts["body"]
            cleaned = clean_response_text(entry.detail)
            wrapped = self._word_wrap(cleaned, body_font, text_w)
            for i, line in enumerate(wrapped[:2]):
                if i == 1 and len(wrapped) > 2:
                    line = self._truncate_text(line, body_font, text_w)
                draw.text((text_x, y + 30 + i * 28), line,
                          font=body_font,
                          fill=config.COLORS["text_primary"])

    def _draw_streaming_entry(self, draw: ImageDraw.Draw, x: int, y: int,
                               width: int, height: int, text: str):
        """Draw a streaming text entry as a glass card."""
        bar_color = config.COLORS["accent_purple"]
        radius = config.LAYOUT.get("card_radius", 10)

        # Glass card
        self.glass.draw_glass_card(draw, (x, y, x + width, y + height),
                                    accent_color=bar_color, radius=radius)

        text_x = x + 14
        text_w = width - 44

        # "Streaming..." label
        label_font = self._fonts["body_small"]
        draw.text((text_x, y + 8), "Streaming...", font=label_font, fill=bar_color)

        # Pulsing dot
        pulse = int((time.time() * 3) % 2)
        if pulse:
            dot_x = x + width - 18
            dot_y = y + height // 2
            dim = tuple(c // 4 for c in bar_color[:3])
            draw.ellipse([dot_x - 6, dot_y - 6, dot_x + 6, dot_y + 6], fill=dim)
            draw.ellipse([dot_x - 3, dot_y - 3, dot_x + 3, dot_y + 3], fill=bar_color)

        # Last 2 lines of streamed text
        if text:
            body_font = self._fonts["body"]
            cleaned = clean_response_text(text)
            wrapped = self._word_wrap(cleaned, body_font, text_w)
            last_lines = wrapped[-2:] if len(wrapped) >= 2 else wrapped
            for i, line in enumerate(last_lines):
                line = self._truncate_text(line, body_font, text_w)
                draw.text((text_x, y + 30 + i * 28), line,
                          font=body_font,
                          fill=config.COLORS["text_primary"])

    def _draw_button_panel(self, draw: ImageDraw.Draw, x: int, y: int,
                           width: int, height: int):
        """Draw the command button panel with glass buttons."""
        layout = config.LAYOUT
        padding = layout["button_padding"]
        gap = layout["button_gap"]
        cols = layout["button_cols"]
        rows = layout["button_rows"]

        usable_w = width - 2 * padding - (cols - 1) * gap
        usable_h = height - 2 * padding - (rows - 1) * gap
        btn_w = usable_w // cols
        btn_h = usable_h // rows

        # Button state → color mapping
        state_color_map = {
            "pressed": config.COLORS["accent_pink"],
            "running": config.COLORS["status_amber"],
            "success": config.COLORS["status_green"],
            "error": config.COLORS["status_red"],
            "listening": config.COLORS["accent_purple"],
        }

        # Auto-reset flash states
        flash_duration = config.TOUCH.get("button_flash_duration", 2.0)
        current_time = time.time()
        with self.lock:
            for btn_id, flash_time in list(self._button_flash_times.items()):
                state = self._button_states.get(btn_id)
                if state in ("success", "error") and current_time - flash_time > flash_duration:
                    self._button_states[btn_id] = "normal"

        button_font = self._fonts["button"]

        for i, btn_def in enumerate(config.BUTTONS):
            col = i % cols
            row = i // cols

            btn_x = x + padding + col * (btn_w + gap)
            btn_y = y + padding + row * (btn_h + gap)

            with self.lock:
                state = self._button_states.get(btn_def["id"], "normal")

            sc = state_color_map.get(state)
            bbox = (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h)
            self.glass.draw_glass_button(draw, bbox, btn_def["label"],
                                          font=button_font, state=state,
                                          state_color=sc)

    def _draw_connection_bar(self, draw: ImageDraw.Draw, x: int, y: int, width: int):
        """Draw connection status in a glass card."""
        with self.lock:
            connected = self._connection_status
            model = self._model_name
            cost = self._api_cost

        padding = 14
        card_h = 64
        radius = config.LAYOUT.get("card_radius", 10)

        # Glass card for connection bar
        self.glass.draw_glass_panel(
            draw, (x + 8, y, x + width - 8, y + card_h),
            radius=radius, glow=False
        )

        # Connection dot
        dot_color = config.COLORS["status_green"] if connected else config.COLORS["status_red"]
        dot_x = x + padding + 6
        dot_y = y + 12
        self.glass.draw_status_dot(draw, (dot_x, dot_y), dot_color, size=8, glow=True)

        # ONLINE/OFFLINE
        status_text = "ONLINE" if connected else "OFFLINE"
        status_font = self._fonts["mono_small"]
        draw.text((dot_x + 12, y + 5), status_text,
                  font=status_font, fill=dot_color)

        # Model name
        if model:
            model_font = self._fonts["mono_small"]
            model_display = self._truncate_text(model, model_font, width - 2 * padding - 16)
            draw.text((x + padding, y + 24), model_display,
                      font=model_font, fill=config.COLORS["text_dim"])

        # API cost
        if cost > 0:
            cost_str = f"${cost:.4f}"
            cost_font = self._fonts["mono_small"]
            draw.text((x + padding, y + 42), cost_str,
                      font=cost_font, fill=config.COLORS["text_dim"])

    def _draw_overlay(self, draw: ImageDraw.Draw, frame: Image.Image,
                      entry: ActivityEntry):
        """Draw fullscreen overlay with glass panel.
        Uses a separate RGBA layer composited onto the RGB frame for the
        semi-transparent backdrop, then draws content in RGB on top."""
        from PIL import Image as PILImage

        # Semi-transparent backdrop via alpha composite
        backdrop = PILImage.new("RGBA", frame.size, (5, 5, 10, 210))
        frame_rgba = frame.convert("RGBA")
        frame_rgba = PILImage.alpha_composite(frame_rgba, backdrop)
        frame.paste(frame_rgba.convert("RGB"))
        # Re-create draw since we pasted
        draw = ImageDraw.Draw(frame)

        # Content panel
        margin_x, margin_y = 60, 50
        panel_x1 = margin_x
        panel_y1 = margin_y
        panel_x2 = self.width - margin_x
        panel_y2 = self.height - margin_y
        radius = config.LAYOUT.get("panel_radius", 12)

        # Glass panel (on dark backdrop, so use direct fill)
        panel_fill = (18, 16, 28)
        panel_border = self.glass._border_color
        for i in range(2, 0, -1):
            dim = tuple(max(0, c - 15 * i) for c in panel_border)
            self.glass.draw_rounded_rect(draw, (panel_x1 - i, panel_y1 - i,
                                                panel_x2 + i, panel_y2 + i),
                                         radius + i, outline=dim)
        self.glass.draw_rounded_rect(draw, (panel_x1, panel_y1, panel_x2, panel_y2),
                                     radius, fill=panel_fill, outline=panel_border)

        # Type color accent bar at top
        type_colors = {
            "tool": config.COLORS["accent_cyan"],
            "message": config.COLORS["accent_pink"],
            "status": config.COLORS["accent_purple"],
            "error": config.COLORS["status_red"],
            "notification": config.COLORS["status_amber"],
        }
        bar_color = type_colors.get(entry.type, config.COLORS["accent_cyan"])

        bar_x1 = panel_x1 + radius
        bar_x2 = panel_x2 - radius
        if bar_x2 > bar_x1:
            draw.rectangle([bar_x1, panel_y1 + 1, bar_x2, panel_y1 + 5], fill=bar_color)

        # Content area
        content_x = panel_x1 + 25
        content_y = panel_y1 + 20
        content_w = (panel_x2 - panel_x1) - 50

        # Title with soft glow
        title_font = self._fonts["body"]
        self.glass.draw_soft_glow_text(draw, (content_x, content_y),
                                        entry.title, title_font, bar_color)

        # Timestamp right-aligned
        time_str = entry.timestamp.strftime("%H:%M:%S")
        time_font = self._fonts["mono_small"]
        time_bbox = time_font.getbbox(time_str)
        time_w = time_bbox[2] - time_bbox[0]
        draw.text((panel_x2 - 25 - time_w, content_y + 4), time_str,
                  font=time_font, fill=config.COLORS["text_dim"])

        # Separator
        sep_y = content_y + 35
        sep_color = tuple(c // 4 for c in config.COLORS["accent_cyan"][:3])
        draw.line([(content_x, sep_y), (panel_x2 - 25, sep_y)],
                  fill=sep_color, width=1)

        # Detail text with scroll
        body_font = self._fonts["body"]
        text_y = sep_y + 12
        line_height = 30
        max_text_y = panel_y2 - 55
        visible_lines = max(1, (max_text_y - text_y) // line_height)

        if entry.detail:
            cleaned = clean_response_text(entry.detail)
            wrapped = self._word_wrap(cleaned, body_font, content_w)
            total_lines = len(wrapped)

            with self.lock:
                self._overlay_total_lines = total_lines
                scroll_offset = self._overlay_scroll_offset
                max_scroll = max(0, total_lines - visible_lines)
                if scroll_offset > max_scroll:
                    self._overlay_scroll_offset = max_scroll
                    scroll_offset = max_scroll

            start_line = scroll_offset
            end_line = min(start_line + visible_lines, total_lines)
            for i, line in enumerate(wrapped[start_line:end_line]):
                draw.text((content_x, text_y + i * line_height), line,
                          font=body_font, fill=config.COLORS["text_primary"])

            scrollable = total_lines > visible_lines
            if scrollable:
                indicator_x = panel_x2 - 22
                indicator_font = self._fonts["body_small"]
                if scroll_offset > 0:
                    draw.text((indicator_x, text_y), "\u25b2",
                              font=indicator_font, fill=config.COLORS["accent_cyan"])
                if scroll_offset < total_lines - visible_lines:
                    draw.text((indicator_x, max_text_y - 20), "\u25bc",
                              font=indicator_font, fill=config.COLORS["accent_cyan"])

        # Hint at bottom
        with self.lock:
            scrollable = self._overlay_total_lines > visible_lines if entry.detail else False
        hint = "SWIPE / TAP TO CLOSE" if scrollable else "TAP TO CLOSE"
        hint_font = self._fonts["mono_small"]
        hint_bbox = hint_font.getbbox(hint)
        hint_w = hint_bbox[2] - hint_bbox[0]
        hint_x = (panel_x1 + panel_x2 - hint_w) // 2
        draw.text((hint_x, panel_y2 - 32), hint,
                  font=hint_font, fill=config.COLORS["text_dim"])

    # === Text Utilities ===

    def _truncate_text(self, text: str, font, max_width: int) -> str:
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

    # === Pygame Integration ===

    def render_to_surface(self) -> 'pygame.Surface':
        if not PYGAME_AVAILABLE:
            raise RuntimeError("Pygame not available")

        pil_image = self.render()
        raw_data = pil_image.tobytes()
        surface = pygame.image.fromstring(raw_data, pil_image.size, 'RGB')
        return surface

    def cleanup(self):
        print("[Display DSI] Cleanup complete")
