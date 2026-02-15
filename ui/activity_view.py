"""
Activity feed view — wraps existing activity feed rendering as a swipeable view.
Delegates to the display's existing activity/streaming drawing logic.
"""

import time
from PIL import ImageDraw

import config_dsi as config
from ui.view_base import RightPanelView
from ui.text_utils import clean_response_text


class ActivityView(RightPanelView):
    """Activity feed wrapped as a right-panel view."""

    def __init__(self, glass_renderer, fonts: dict, display_ref):
        super().__init__(glass_renderer, fonts)
        self.display = display_ref

    def get_title(self) -> str:
        return "ACTIVITY"

    def render(self, draw: ImageDraw.Draw, x: int, y: int,
               width: int, height: int):
        """Render the activity feed (delegates to display methods)."""
        layout = config.LAYOUT

        # Header
        header_h = layout["activity_header_height"]
        header_font = self.fonts["header"]
        draw.text((x + 18, y + 8), "ACTIVITY", font=header_font,
                  fill=config.COLORS["accent_cyan"])

        divider_color = tuple(c // 4 for c in config.COLORS["accent_cyan"][:3])
        draw.line([(x + 15, y + header_h - 1), (x + width - 15, y + header_h - 1)],
                  fill=divider_color, width=1)

        # Entries area
        entry_h = layout["activity_entry_height"]
        entry_gap = layout.get("activity_entry_gap", 6)
        entries_y = y + header_h + 4
        entries_area_h = height - header_h - 25

        with self.display.lock:
            entries = list(self.display.activity_feed.entries)
            scroll_offset = self.display._scroll_offset
            streaming_active = self.display._streaming_msg_id is not None
            streaming_text = self.display._streaming_text if streaming_active else ""

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
            self.display._draw_streaming_entry(draw, x + 12, entry_y,
                                                width - 24, entry_h - entry_gap,
                                                streaming_text)
            entry_y += entry_h

        for entry in visible:
            if entry_y + entry_h > entries_y + entries_area_h:
                break
            self.display._draw_activity_entry(draw, entry, x + 12, entry_y,
                                               width - 24, entry_h - entry_gap)
            entry_y += entry_h

    def on_tap(self, x: int, y: int) -> bool:
        """Handle tap — delegate to display's find_activity_entry."""
        entry = self.display.find_activity_entry(x, y)
        if entry and entry.detail:
            self.display.show_overlay(entry)
            return True
        return False

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        """Handle vertical scroll of activity entries."""
        current = self.display.get_scroll_offset()
        scroll_delta = -dy // 20
        if scroll_delta != 0:
            self.display.set_scroll_offset(current + scroll_delta)
            return True
        return False
