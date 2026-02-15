"""
Tool approval overlay modal.
Draws a centered glass panel with APPROVE/DENY buttons for tool execution requests.
Uses solid dark fill (no RGBA alpha_composite) for performance.
"""

import time
from typing import Optional, Tuple
from PIL import Image, ImageDraw

import config_dsi as config


class ApprovalModal:
    """Tool approval modal overlay."""

    def __init__(self, glass_renderer, fonts: dict):
        self.glass = glass_renderer
        self.fonts = fonts
        self._approval: Optional[dict] = None
        self._appeared_at: float = 0
        self._timeout_seconds = 120

        # Button hit rects (set during render)
        self._approve_rect: Optional[Tuple[int, int, int, int]] = None
        self._deny_rect: Optional[Tuple[int, int, int, int]] = None

    def show(self, approval: dict):
        """Show the approval modal for a tool request."""
        self._approval = approval
        self._appeared_at = time.time()

    def dismiss(self):
        """Dismiss the modal."""
        self._approval = None
        self._approve_rect = None
        self._deny_rect = None

    @property
    def is_visible(self) -> bool:
        if self._approval is None:
            return False
        # Auto-timeout
        if time.time() - self._appeared_at > self._timeout_seconds:
            self.dismiss()
            return False
        return True

    @property
    def current_approval(self) -> Optional[dict]:
        return self._approval

    def find_button(self, x: int, y: int) -> str:
        """Check if (x, y) hits APPROVE or DENY button. Returns 'approve', 'deny', or ''."""
        if self._approve_rect:
            ax1, ay1, ax2, ay2 = self._approve_rect
            if ax1 <= x <= ax2 and ay1 <= y <= ay2:
                return "approve"
        if self._deny_rect:
            dx1, dy1, dx2, dy2 = self._deny_rect
            if dx1 <= x <= dx2 and dy1 <= y <= dy2:
                return "deny"
        return ""

    def render(self, draw: ImageDraw.Draw, frame: Image.Image,
               screen_width: int, screen_height: int):
        """Render the approval modal overlay onto the frame."""
        if not self._approval:
            return

        # Solid dark backdrop (no RGBA composite — fast)
        draw.rectangle([0, 0, screen_width, screen_height], fill=(5, 5, 10))

        # Panel dimensions
        panel_w = min(600, screen_width - 80)
        panel_h = min(380, screen_height - 80)
        panel_x = (screen_width - panel_w) // 2
        panel_y = (screen_height - panel_h) // 2
        radius = config.LAYOUT.get("panel_radius", 12)

        # Glass panel with glow
        panel_fill = (18, 16, 28)
        panel_border = self.glass._border_color
        for i in range(2, 0, -1):
            dim = tuple(max(0, c - 15 * i) for c in panel_border)
            self.glass.draw_rounded_rect(
                draw, (panel_x - i, panel_y - i,
                       panel_x + panel_w + i, panel_y + panel_h + i),
                radius + i, outline=dim
            )
        self.glass.draw_rounded_rect(
            draw, (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
            radius, fill=panel_fill, outline=panel_border
        )

        # Amber accent bar at top
        amber = config.COLORS["status_amber"]
        bar_x1 = panel_x + radius
        bar_x2 = panel_x + panel_w - radius
        if bar_x2 > bar_x1:
            draw.rectangle([bar_x1, panel_y + 1, bar_x2, panel_y + 5], fill=amber)

        # Content
        cx = panel_x + 25
        cy = panel_y + 20
        content_w = panel_w - 50

        # Title with amber glow
        header_font = self.fonts["header"]
        self.glass.draw_soft_glow_text(
            draw, (cx, cy), "TOOL APPROVAL REQUIRED", header_font, amber
        )
        cy += 40

        # Separator
        sep_color = tuple(c // 4 for c in amber[:3])
        draw.line([(cx, cy), (cx + content_w, cy)], fill=sep_color, width=1)
        cy += 12

        # Tool name
        body_font = self.fonts["body"]
        mono_font = self.fonts["mono_small"]

        tool_name = self._approval.get("tool", "Unknown tool")
        draw.text((cx, cy), f"Tool: {tool_name}", font=body_font,
                  fill=config.COLORS["text_primary"])
        cy += 32

        # Description / args
        desc = self._approval.get("description", "")
        args = self._approval.get("args", {})
        if desc:
            display_text = str(desc)[:200]
        elif args:
            if isinstance(args, dict):
                display_text = ", ".join(f"{k}: {str(v)[:30]}" for k, v in list(args.items())[:4])
            else:
                display_text = str(args)[:200]
        else:
            display_text = "No details provided"

        # Word wrap the detail text
        wrapped = self._word_wrap(display_text, mono_font, content_w)
        max_detail_lines = 4
        for i, line in enumerate(wrapped[:max_detail_lines]):
            if i == max_detail_lines - 1 and len(wrapped) > max_detail_lines:
                line = line[:50] + "..."
            draw.text((cx, cy + i * 22), line, font=mono_font,
                      fill=config.COLORS["text_secondary"])
        cy += max_detail_lines * 22 + 10

        # Timeout indicator
        remaining = max(0, self._timeout_seconds - (time.time() - self._appeared_at))
        timeout_str = f"Auto-dismiss in {int(remaining)}s"
        draw.text((cx, cy), timeout_str, font=mono_font,
                  fill=config.COLORS["text_dim"])

        # Buttons at bottom
        btn_w = 160
        btn_h = 48
        btn_y = panel_y + panel_h - btn_h - 25
        gap = 30

        # APPROVE button (green)
        approve_x = panel_x + (panel_w // 2) - btn_w - gap // 2
        self._approve_rect = (approve_x, btn_y, approve_x + btn_w, btn_y + btn_h)
        self.glass.draw_glass_button(
            draw, self._approve_rect, "APPROVE",
            font=self.fonts["button"], state="success",
            state_color=config.COLORS["status_green"]
        )

        # DENY button (red)
        deny_x = panel_x + (panel_w // 2) + gap // 2
        self._deny_rect = (deny_x, btn_y, deny_x + btn_w, btn_y + btn_h)
        self.glass.draw_glass_button(
            draw, self._deny_rect, "DENY",
            font=self.fonts["button"], state="error",
            state_color=config.COLORS["status_red"]
        )

    def _word_wrap(self, text: str, font, max_width: int) -> list:
        """Simple word wrap."""
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
