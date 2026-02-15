"""
Health & Presence dashboard view.
Shows gateway status, heartbeat, and connected devices.
"""

import time
from PIL import ImageDraw

import config_dsi as config
from ui.view_base import RightPanelView


class HealthView(RightPanelView):
    """Presence & health dashboard view."""

    def __init__(self, glass_renderer, fonts: dict, bridge):
        super().__init__(glass_renderer, fonts)
        self.bridge = bridge

    def get_title(self) -> str:
        return "HEALTH"

    def render(self, draw: ImageDraw.Draw, x: int, y: int,
               width: int, height: int):
        """Render health dashboard with gateway status and connected devices."""
        card_x = x + 12
        card_w = width - 24
        card_h = 90
        card_gap = 8
        radius = config.LAYOUT.get("card_radius", 10)
        cy = y + 8

        gateway_info = self.bridge.get_gateway_info()
        health_data = self.bridge.get_health_data()
        presence_data = self.bridge.get_presence_data()
        last_tick = self.bridge.get_last_tick()

        # === Gateway Status Card ===
        self.glass.draw_glass_card(
            draw, (card_x, cy, card_x + card_w, cy + card_h),
            accent_color=config.COLORS["accent_cyan"], radius=radius
        )

        title_font = self.fonts["body_small"]
        body_font = self.fonts["body"]
        mono_font = self.fonts["mono_small"]

        draw.text((card_x + 14, cy + 8), "GATEWAY", font=title_font,
                  fill=config.COLORS["accent_cyan"])

        # Health status dot
        is_healthy = bool(gateway_info) or self.bridge.is_connected()
        dot_color = config.COLORS["status_green"] if is_healthy else config.COLORS["status_red"]
        dot_x = card_x + card_w - 18
        dot_y = cy + 18
        draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=dot_color)

        # Uptime
        uptime_ms = gateway_info.get("uptimeMs", 0)
        if uptime_ms > 0:
            uptime_secs = uptime_ms // 1000
            hours = uptime_secs // 3600
            mins = (uptime_secs % 3600) // 60
            uptime_str = f"Uptime: {hours}h {mins}m"
        else:
            uptime_str = "Uptime: --"
        draw.text((card_x + 14, cy + 32), uptime_str, font=mono_font,
                  fill=config.COLORS["text_secondary"])

        # Last heartbeat
        if last_tick > 0:
            ago = time.time() - last_tick
            if ago < 60:
                tick_str = f"Heartbeat: {int(ago)}s ago"
            else:
                tick_str = f"Heartbeat: {int(ago // 60)}m ago"
        else:
            tick_str = "Heartbeat: --"
        draw.text((card_x + 14, cy + 52), tick_str, font=mono_font,
                  fill=config.COLORS["text_secondary"])

        # State version
        sv = gateway_info.get("stateVersion", 0)
        if sv:
            draw.text((card_x + 14, cy + 72), f"State v{sv}", font=mono_font,
                      fill=config.COLORS["text_dim"])

        cy += card_h + card_gap

        # === Connected Devices ===
        device_card_h = 60
        max_y = y + height - 10

        if presence_data:
            devices = list(presence_data.values()) if isinstance(presence_data, dict) else []
            for dev in devices:
                if cy + device_card_h > max_y:
                    break

                self.glass.draw_glass_card(
                    draw, (card_x, cy, card_x + card_w, cy + device_card_h),
                    accent_color=config.COLORS["accent_purple"], radius=radius
                )

                # Device name/ID
                dev_name = dev.get("name", dev.get("clientId", dev.get("id", "Unknown")))
                dev_name = str(dev_name)[:30]
                draw.text((card_x + 14, cy + 8), dev_name, font=title_font,
                          fill=config.COLORS["accent_purple"])

                # Role/mode
                role = dev.get("role", dev.get("mode", ""))
                if role:
                    draw.text((card_x + 14, cy + 32), role, font=mono_font,
                              fill=config.COLORS["text_dim"])

                # Status dot
                dev_status = dev.get("status", dev.get("state", "connected"))
                dot_color = config.COLORS["status_green"] if dev_status in ("connected", "online", "active") else config.COLORS["text_dim"]
                dot_x = card_x + card_w - 18
                dot_y = cy + device_card_h // 2
                draw.ellipse([dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4], fill=dot_color)

                cy += device_card_h + card_gap
        else:
            # No devices
            draw.text((card_x + 14, cy + 8), "No devices connected", font=mono_font,
                      fill=config.COLORS["text_dim"])

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        scroll_delta = -dy // 20
        if scroll_delta != 0:
            self._scroll_offset = max(0, self._scroll_offset + scroll_delta)
            return True
        return False
