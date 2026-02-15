"""
Cron/Scheduled jobs view.
Displays upcoming scheduled tasks from the OpenClaw gateway.
"""

import time
from PIL import ImageDraw

import config_dsi as config
from ui.view_base import RightPanelView


class CronView(RightPanelView):
    """Cron/scheduled jobs view."""

    def __init__(self, glass_renderer, fonts: dict, bridge):
        super().__init__(glass_renderer, fonts)
        self.bridge = bridge
        self._last_refresh = 0
        self._refresh_interval = 30.0  # seconds

    def get_title(self) -> str:
        return "CRON"

    def on_activate(self):
        """Trigger immediate refresh when view becomes active."""
        self._last_refresh = 0

    def render(self, draw: ImageDraw.Draw, x: int, y: int,
               width: int, height: int):
        """Render scheduled jobs list."""
        # Auto-refresh
        now = time.time()
        if now - self._last_refresh > self._refresh_interval:
            self.bridge.request_cron_list()
            self._last_refresh = now

        jobs = self.bridge.get_cron_data()
        card_x = x + 12
        card_w = width - 24
        card_h = 75
        card_gap = 8
        radius = config.LAYOUT.get("card_radius", 10)
        cy = y + 8

        title_font = self.fonts["body_small"]
        mono_font = self.fonts["mono_small"]
        max_y = y + height - 10

        if not jobs:
            draw.text((card_x + 14, cy + 8), "No scheduled jobs", font=mono_font,
                      fill=config.COLORS["text_dim"])
            return

        for job in jobs:
            if cy + card_h > max_y:
                break

            enabled = job.get("enabled", True)
            accent = config.COLORS["status_amber"] if enabled else config.COLORS["text_dim"]

            self.glass.draw_glass_card(
                draw, (card_x, cy, card_x + card_w, cy + card_h),
                accent_color=accent, radius=radius
            )

            # Job name
            name = job.get("name", job.get("title", "Unnamed"))
            name = str(name)[:40]
            draw.text((card_x + 14, cy + 8), name, font=title_font,
                      fill=accent)

            # Enabled/disabled indicator
            status_text = "ENABLED" if enabled else "DISABLED"
            dot_x = card_x + card_w - 18
            dot_y = cy + 18
            draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=accent)

            # Schedule expression
            schedule = job.get("schedule", job.get("cron", ""))
            if schedule:
                draw.text((card_x + 14, cy + 32), str(schedule), font=mono_font,
                          fill=config.COLORS["text_secondary"])

            # Next run time
            next_run = job.get("nextRun", job.get("nextRunAt", ""))
            if next_run:
                next_str = f"Next: {str(next_run)[-19:]}"  # Trim to datetime portion
                draw.text((card_x + 14, cy + 52), next_str, font=mono_font,
                          fill=config.COLORS["text_dim"])

            cy += card_h + card_gap

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        scroll_delta = -dy // 20
        if scroll_delta != 0:
            self._scroll_offset = max(0, self._scroll_offset + scroll_delta)
            return True
        return False
