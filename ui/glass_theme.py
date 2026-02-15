"""
Glassmorphism rendering engine for the CyberDeck DSI display.
Pre-renders expensive assets (gradients, textures) at init,
provides cheap per-frame drawing methods for glass panels, buttons, and text.

Performance strategy: work in RGB mode (not RGBA) for all per-frame drawing.
Glass panel fills are pre-blended solid RGB colors. RGBA alpha_composite is
only used during init for the base frame. This keeps per-frame cost low
on Raspberry Pi 4.
"""

import os
from PIL import Image, ImageDraw, ImageFont
import config_dsi as config


def _blend_rgba_on_rgb(bg_rgb, overlay_rgba):
    """Pre-blend an RGBA color onto an RGB background."""
    r, g, b, a = overlay_rgba
    alpha = a / 255.0
    inv = 1.0 - alpha
    return (
        int(r * alpha + bg_rgb[0] * inv),
        int(g * alpha + bg_rgb[1] * inv),
        int(b * alpha + bg_rgb[2] * inv),
    )


class GlassRenderer:
    """
    Glassmorphism renderer with pre-cached assets.
    All expensive operations run once at init.
    Per-frame methods draw on RGB images (fast on Pi).
    """

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

        # Load fonts first
        self._fonts = {}
        self._load_fonts()

        # Pre-render static assets
        self._base_frame = None  # Lazy-built, cached
        self._base_frame_panel_w = None
        # Scanline color: slightly darker than darkest bg
        self._scanline_color = (max(0, config.COLORS["background_bottom"][0] - 2),
                                max(0, config.COLORS["background_bottom"][1] - 2),
                                max(0, config.COLORS["background_bottom"][2] - 2))

        # Cache for getbbox results (text measurement is expensive)
        self._bbox_cache = {}

        # Pre-compute blended glass colors for left and right panel backgrounds
        bg = config.COLORS["background"]
        glass_panel = config.COLORS["glass_panel"]
        glass_card = config.COLORS["glass_card"]
        glass_button = config.COLORS["glass_button"]
        glass_border = config.COLORS["glass_border"]

        # Left panel bg = gradient blended with glass_panel tint
        self._left_bg = _blend_rgba_on_rgb(bg, glass_panel)
        # Right panel bg = gradient blended with slightly different tint
        right_tint = (glass_panel[0] - 2, glass_panel[1] - 2, glass_panel[2] - 2, glass_panel[3] - 10)
        self._right_bg = _blend_rgba_on_rgb(bg, right_tint)

        # Pre-blend glass fills against their expected backgrounds
        self._card_fill_left = _blend_rgba_on_rgb(self._left_bg, glass_card)
        self._card_fill_right = _blend_rgba_on_rgb(self._right_bg, glass_card)
        self._button_fill = _blend_rgba_on_rgb(self._left_bg, glass_button)
        self._border_color = _blend_rgba_on_rgb(self._left_bg, glass_border)
        self._border_color_right = _blend_rgba_on_rgb(self._right_bg, glass_border)
        self._highlight_color = _blend_rgba_on_rgb(self._left_bg, config.COLORS["glass_highlight"])

    # === Pre-rendered Assets ===

    def _make_base_frame(self, left_panel_w: int) -> Image.Image:
        """Build static base frame as RGB. Gradient bg + panel tints + divider."""
        img = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(img)

        c_top = config.COLORS["background_top"]
        c_bot = config.COLORS["background_bottom"]

        # Gradient background
        for y in range(self.height):
            t = y / max(self.height - 1, 1)
            r = int(c_top[0] + (c_bot[0] - c_top[0]) * t)
            g = int(c_top[1] + (c_bot[1] - c_top[1]) * t)
            b = int(c_top[2] + (c_bot[2] - c_top[2]) * t)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        # Blend panel tints (using RGBA composite just once during init)
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        left_tint = config.COLORS["glass_panel"]
        odraw.rectangle([0, 0, left_panel_w, self.height], fill=left_tint)
        right_tint = (left_tint[0] - 2, left_tint[1] - 2, left_tint[2] - 2, left_tint[3] - 10)
        odraw.rectangle([left_panel_w, 0, self.width, self.height], fill=right_tint)

        # Divider glow
        glow_c = config.COLORS["glass_border_glow"]
        dx = left_panel_w
        odraw.line([(dx, 0), (dx, self.height)],
                   fill=(glow_c[0], glow_c[1], glow_c[2], 60), width=1)
        for off in (1, 2):
            a = max(0, 30 - off * 12)
            odraw.line([(dx - off, 0), (dx - off, self.height)],
                       fill=(glow_c[0], glow_c[1], glow_c[2], a), width=1)
            odraw.line([(dx + off, 0), (dx + off, self.height)],
                       fill=(glow_c[0], glow_c[1], glow_c[2], a), width=1)

        # Composite overlay onto gradient, convert back to RGB
        base_rgba = img.convert("RGBA")
        base_rgba = Image.alpha_composite(base_rgba, overlay)
        result = base_rgba.convert("RGB")

        # Bake scanlines directly into base frame (0 cost per frame)
        draw_final = ImageDraw.Draw(result)
        for y in range(0, self.height, 3):
            draw_final.line([(0, y), (self.width, y)], fill=self._scanline_color)

        return result

    # Scanlines are baked into the base frame during _make_base_frame

    def _load_fonts(self):
        """Load custom fonts with fallbacks."""
        font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")

        def load(path, size, fallback_path, fallback_size=None):
            full = os.path.join(font_dir, path) if not os.path.isabs(path) else path
            try:
                return ImageFont.truetype(full, size)
            except (IOError, OSError):
                try:
                    return ImageFont.truetype(fallback_path, fallback_size or size)
                except (IOError, OSError):
                    return ImageFont.load_default()

        fb_bold = config.FONTS["bold_path"]
        fb_default = config.FONTS["default_path"]
        fb_mono = config.FONTS["mono_path"]

        self._fonts["header_large"] = load("Rajdhani-Bold.ttf", config.FONTS["size_header_large"], fb_bold)
        self._fonts["header"] = load("Rajdhani-Bold.ttf", config.FONTS["size_header"], fb_bold)
        self._fonts["header_semi"] = load("Rajdhani-SemiBold.ttf", config.FONTS["size_header"], fb_bold)
        self._fonts["button"] = load("Inter-Regular.ttf", config.FONTS["size_button"], fb_default)
        self._fonts["body"] = load("Inter-Regular.ttf", config.FONTS["size_body"], fb_default)
        self._fonts["body_small"] = load("Inter-Regular.ttf", config.FONTS["size_body_small"], fb_default)
        self._fonts["mono"] = load("JetBrainsMono-Regular.ttf", config.FONTS["size_mono"], fb_mono)
        self._fonts["mono_small"] = load("JetBrainsMono-Regular.ttf", config.FONTS["size_mono_small"], fb_mono)

        # Legacy compat aliases
        self._fonts["large"] = self._fonts["header_large"]
        self._fonts["medium"] = self._fonts["body"]
        self._fonts["small"] = self._fonts["body_small"]
        self._fonts["title"] = self._fonts["header_large"]

    def get_font(self, name: str) -> ImageFont.FreeTypeFont:
        return self._fonts.get(name, self._fonts.get("body", ImageFont.load_default()))

    def get_text_size(self, text: str, font) -> tuple:
        """Cached text size measurement. Returns (width, height)."""
        key = (text, id(font))
        if key not in self._bbox_cache:
            bbox = font.getbbox(text)
            self._bbox_cache[key] = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        return self._bbox_cache[key]

    # === Per-frame Composition ===

    def compose_frame(self, left_panel_w: int) -> Image.Image:
        """Return a fresh RGB copy of the cached base frame (~2ms)."""
        if self._base_frame is None or self._base_frame_panel_w != left_panel_w:
            self._base_frame = self._make_base_frame(left_panel_w)
            self._base_frame_panel_w = left_panel_w
        return self._base_frame.copy()

    def apply_scanlines(self, frame: Image.Image) -> Image.Image:
        """No-op: scanlines are pre-baked into base frame. Kept for API compat."""
        return frame

    # === Drawing Primitives (all RGB, no alpha) ===

    def draw_rounded_rect(self, draw: ImageDraw.Draw, bbox, radius: int,
                          fill=None, outline=None, outline_width: int = 1):
        """Draw a rounded rectangle."""
        x1, y1, x2, y2 = bbox
        if fill:
            draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)
        if outline:
            draw.rounded_rectangle([x1, y1, x2, y2], radius=radius,
                                   outline=outline, width=outline_width)

    def draw_glass_panel(self, draw: ImageDraw.Draw, bbox,
                         radius: int = 10, tint=None, border_color=None,
                         glow: bool = True, on_right: bool = False):
        """Draw a glass panel with pre-blended RGB fills."""
        x1, y1, x2, y2 = bbox

        if tint and len(tint) >= 4:
            bg = self._right_bg if on_right else self._left_bg
            fill = _blend_rgba_on_rgb(bg, tint)
        else:
            fill = tint or (self._card_fill_right if on_right else self._card_fill_left)

        border = border_color or (self._border_color_right if on_right else self._border_color)

        if glow:
            glow_c = self._border_color if not on_right else self._border_color_right
            for i in range(2, 0, -1):
                dim = tuple(max(0, c - 15 * i) for c in glow_c)
                self.draw_rounded_rect(draw, (x1 - i, y1 - i, x2 + i, y2 + i),
                                       radius + i, outline=dim)

        self.draw_rounded_rect(draw, bbox, radius, fill=fill)
        self.draw_rounded_rect(draw, bbox, radius, outline=border)

        # Top highlight
        hl = self._highlight_color
        clip_x1, clip_x2 = x1 + radius, x2 - radius
        if clip_x2 > clip_x1:
            draw.line([(clip_x1, y1 + 1), (clip_x2, y1 + 1)], fill=hl, width=1)

    def draw_glass_button(self, draw: ImageDraw.Draw, bbox, label: str,
                          font=None, state: str = "normal",
                          state_color=None, border_color=None):
        """Draw a glass button. Normal state uses pre-blended fills."""
        x1, y1, x2, y2 = bbox
        radius = config.LAYOUT.get("button_radius", 10)
        font = font or self._fonts.get("button", ImageFont.load_default())

        if state == "normal":
            fill = self._button_fill
            border = border_color or self._border_color
            text_color = config.COLORS["text_primary"]
            do_glow = False
        else:
            sc = state_color or config.COLORS["accent_cyan"]
            fill = (sc[0] // 8, sc[1] // 8, sc[2] // 8)
            border = sc
            text_color = sc
            do_glow = True

        if do_glow:
            sc = state_color or config.COLORS["accent_cyan"]
            dim1 = tuple(c // 3 for c in sc[:3])
            dim2 = tuple(c // 5 for c in sc[:3])
            self.draw_rounded_rect(draw, (x1 - 2, y1 - 2, x2 + 2, y2 + 2),
                                   radius + 2, outline=dim2)
            self.draw_rounded_rect(draw, (x1 - 1, y1 - 1, x2 + 1, y2 + 1),
                                   radius + 1, outline=dim1)

        self.draw_rounded_rect(draw, bbox, radius, fill=fill)
        self.draw_rounded_rect(draw, bbox, radius, outline=border)

        # Top highlight
        hl_x1, hl_x2 = x1 + radius, x2 - radius
        if hl_x2 > hl_x1:
            draw.line([(hl_x1, y1 + 1), (hl_x2, y1 + 1)],
                      fill=self._highlight_color, width=1)

        # Label centered (cached measurement)
        lw, lh = self.get_text_size(label, font)
        lx = x1 + (x2 - x1 - lw) // 2
        ly = y1 + (y2 - y1 - lh) // 2 - 1
        draw.text((lx, ly), label, font=font, fill=text_color)

    def draw_glass_card(self, draw: ImageDraw.Draw, bbox,
                        accent_color=None, radius: int = 10, on_right: bool = True):
        """Draw a glass card with accent bar."""
        x1, y1, x2, y2 = bbox
        fill = self._card_fill_right if on_right else self._card_fill_left
        border = self._border_color_right if on_right else self._border_color

        # Tint border from accent
        if accent_color:
            border = (
                (border[0] + accent_color[0]) // 3,
                (border[1] + accent_color[1]) // 3,
                (border[2] + accent_color[2]) // 3,
            )

        self.draw_rounded_rect(draw, bbox, radius, fill=fill)
        self.draw_rounded_rect(draw, bbox, radius, outline=border)

        # Left accent bar
        if accent_color:
            bar_y1 = y1 + radius
            bar_y2 = y2 - radius
            if bar_y2 > bar_y1:
                draw.rectangle([x1 + 1, bar_y1, x1 + 4, bar_y2], fill=accent_color)

    def draw_soft_glow_text(self, draw: ImageDraw.Draw, pos, text: str,
                            font, color):
        """Draw text with subtle glow (2 offset draws + main)."""
        x, y = pos
        # Dimmed glow color (just darken the main color)
        glow = tuple(c // 3 for c in color[:3])
        draw.text((x - 1, y), text, font=font, fill=glow)
        draw.text((x + 1, y), text, font=font, fill=glow)
        draw.text(pos, text, font=font, fill=color)

    def draw_status_dot(self, draw: ImageDraw.Draw, pos, color,
                        size: int = 10, glow: bool = True):
        """Draw a status dot with glow."""
        x, y = pos
        r = size // 2
        if glow:
            dim = tuple(c // 3 for c in color[:3])
            draw.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], fill=dim)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
