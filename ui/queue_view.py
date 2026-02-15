"""
Queue/Runs management view.
Shows active, pending, and completed runs from the OpenClaw gateway.
"""

import time
from PIL import ImageDraw

import config_dsi as config
from ui.view_base import RightPanelView


class QueueView(RightPanelView):
    """Queue/runs management view."""

    def __init__(self, glass_renderer, fonts: dict, bridge):
        super().__init__(glass_renderer, fonts)
        self.bridge = bridge
        self._last_refresh = 0
        self._refresh_interval = 5.0  # seconds

    def get_title(self) -> str:
        return "QUEUE"

    def on_activate(self):
        """Trigger immediate refresh when view becomes active."""
        self._last_refresh = 0

    def render(self, draw: ImageDraw.Draw, x: int, y: int,
               width: int, height: int):
        """Render runs list grouped by status."""
        # Auto-refresh
        now = time.time()
        if now - self._last_refresh > self._refresh_interval:
            self.bridge.request_runs_list()
            self._last_refresh = now

        runs = self.bridge.get_runs_data()
        card_x = x + 12
        card_w = width - 24
        card_h = 75
        card_gap = 8
        radius = config.LAYOUT.get("card_radius", 10)
        cy = y + 8

        title_font = self.fonts["body_small"]
        mono_font = self.fonts["mono_small"]
        max_y = y + height - 10

        status_colors = {
            "active": config.COLORS["status_amber"],
            "running": config.COLORS["status_amber"],
            "pending": config.COLORS["accent_cyan"],
            "queued": config.COLORS["accent_cyan"],
            "completed": config.COLORS["status_green"],
            "done": config.COLORS["status_green"],
            "failed": config.COLORS["status_red"],
            "error": config.COLORS["status_red"],
            "cancelled": config.COLORS["text_dim"],
        }

        if not runs:
            draw.text((card_x + 14, cy + 8), "No runs", font=mono_font,
                      fill=config.COLORS["text_dim"])
            draw.text((card_x + 14, cy + 28), "Queue is empty", font=mono_font,
                      fill=config.COLORS["text_dim"])
            return

        for run in runs:
            if cy + card_h > max_y:
                break

            status = run.get("status", "unknown")
            accent = status_colors.get(status, config.COLORS["text_dim"])

            self.glass.draw_glass_card(
                draw, (card_x, cy, card_x + card_w, cy + card_h),
                accent_color=accent, radius=radius
            )

            # Status badge
            badge_text = status.upper()[:10]
            draw.text((card_x + 14, cy + 8), badge_text, font=title_font,
                      fill=accent)

            # Status dot
            dot_x = card_x + card_w - 18
            dot_y = cy + 18
            if status in ("active", "running"):
                dim = tuple(c // 4 for c in accent[:3])
                draw.ellipse([dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8], fill=dim)
            draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=accent)

            # Command/title
            cmd = run.get("command", run.get("title", run.get("message", "")))
            if isinstance(cmd, str) and cmd:
                cmd_display = cmd[:50] + "..." if len(cmd) > 50 else cmd
                draw.text((card_x + 14, cy + 32), cmd_display, font=mono_font,
                          fill=config.COLORS["text_secondary"])

            # Time / duration
            created = run.get("createdAt", run.get("startedAt", ""))
            duration = run.get("durationMs", run.get("duration", 0))
            info_parts = []
            if duration:
                secs = int(duration) // 1000 if isinstance(duration, (int, float)) and duration > 1000 else int(duration)
                info_parts.append(f"{secs}s")
            if created and isinstance(created, str):
                info_parts.append(created[-8:])  # last 8 chars (time portion)
            if info_parts:
                draw.text((card_x + 14, cy + 52), " | ".join(info_parts),
                          font=mono_font, fill=config.COLORS["text_dim"])

            cy += card_h + card_gap

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        scroll_delta = -dy // 20
        if scroll_delta != 0:
            self._scroll_offset = max(0, self._scroll_offset + scroll_delta)
            return True
        return False
