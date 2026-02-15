"""
Animated Robot Eyes for CyberDeck Display.
Ported from pico-robot's RoboEyes (FluxGarage RoboEyes V 1.1.1).
Draws directly onto PIL ImageDraw in RGB mode — no RGBA compositing.
"""

import random
import time

# Mood types
MOOD_DEFAULT = 0
MOOD_TIRED = 1
MOOD_ANGRY = 2
MOOD_HAPPY = 3

# Position constants (compass directions)
POS_DEFAULT = 0
POS_N = 1
POS_NE = 2
POS_E = 3
POS_SE = 4
POS_S = 5
POS_SW = 6
POS_W = 7
POS_NW = 8


def _ticks_ms():
    return int(time.time() * 1000)


class RoboEyes:
    """Animated robot eyes rendered via PIL ImageDraw."""

    def __init__(self, canvas_width=110, canvas_height=110,
                 eye_color=(255, 255, 255), bg_color=(0, 0, 0)):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.eye_color = eye_color
        self.bg_color = bg_color

        # Eye geometry (scaled for ~110x110 canvas)
        self.eye_l_width_default = 46
        self.eye_l_height_default = 46
        self.eye_l_width_current = 46
        self.eye_l_height_current = 1  # Start closed
        self.eye_l_width_next = 46
        self.eye_l_height_next = 46
        self.eye_l_height_offset = 0
        self.eye_l_border_radius_default = 8
        self.eye_l_border_radius_current = 8
        self.eye_l_border_radius_next = 8

        self.eye_r_width_default = 46
        self.eye_r_height_default = 46
        self.eye_r_width_current = 46
        self.eye_r_height_current = 1
        self.eye_r_width_next = 46
        self.eye_r_height_next = 46
        self.eye_r_height_offset = 0
        self.eye_r_border_radius_default = 8
        self.eye_r_border_radius_current = 8
        self.eye_r_border_radius_next = 8

        self.space_between_default = 14
        self.space_between_current = 14
        self.space_between_next = 14

        # Default positions (centered in canvas)
        total_w = self.eye_l_width_default + self.space_between_default + self.eye_r_width_default
        self.eye_l_x_default = (canvas_width - total_w) // 2
        self.eye_l_y_default = (canvas_height - self.eye_l_height_default) // 2

        self.eye_l_x = self.eye_l_x_default
        self.eye_l_y = self.eye_l_y_default
        self.eye_l_x_next = self.eye_l_x
        self.eye_l_y_next = self.eye_l_y

        self.eye_r_x_default = self.eye_l_x + self.eye_l_width_current + self.space_between_default
        self.eye_r_y_default = self.eye_l_y
        self.eye_r_x = self.eye_r_x_default
        self.eye_r_y = self.eye_r_y_default
        self.eye_r_x_next = self.eye_r_x
        self.eye_r_y_next = self.eye_r_y

        # State flags
        self.tired = False
        self.angry = False
        self.happy = False
        self.curious = False
        self.eye_l_open = False
        self.eye_r_open = False

        # Eyelid state
        self.eyelids_tired_height = 0
        self.eyelids_tired_height_next = 0
        self.eyelids_angry_height = 0
        self.eyelids_angry_height_next = 0
        self.eyelids_happy_bottom_offset = 0
        self.eyelids_happy_bottom_offset_next = 0

        # Flicker animations
        self.h_flicker = False
        self.h_flicker_alternate = False
        self.h_flicker_amplitude = 2

        self.v_flicker = False
        self.v_flicker_alternate = False
        self.v_flicker_amplitude = 10

        # Auto-blinker
        self.autoblinker = False
        self.blink_interval = 1
        self.blink_interval_variation = 4
        self.blink_timer = 0

        # Idle mode
        self.idle = False
        self.idle_interval = 1
        self.idle_interval_variation = 3
        self.idle_animation_timer = 0

        # Confused animation
        self.confused = False
        self.confused_animation_timer = 0
        self.confused_animation_duration = 500
        self.confused_toggle = True

        # Laugh animation
        self.laugh = False
        self.laugh_animation_timer = 0
        self.laugh_animation_duration = 500
        self.laugh_toggle = True

    # ============ Setters ============

    def set_eye_color(self, color):
        self.eye_color = color

    def set_bg_color(self, color):
        self.bg_color = color

    def set_mood(self, mood):
        if mood == MOOD_TIRED:
            self.tired = True
            self.angry = False
            self.happy = False
        elif mood == MOOD_ANGRY:
            self.tired = False
            self.angry = True
            self.happy = False
        elif mood == MOOD_HAPPY:
            self.tired = False
            self.angry = False
            self.happy = True
        else:
            self.tired = False
            self.angry = False
            self.happy = False

    def set_position(self, position):
        cx = self._get_constraint_x()
        cy = self._get_constraint_y()

        if position == POS_N:
            self.eye_l_x_next = cx // 2
            self.eye_l_y_next = 0
        elif position == POS_NE:
            self.eye_l_x_next = cx
            self.eye_l_y_next = 0
        elif position == POS_E:
            self.eye_l_x_next = cx
            self.eye_l_y_next = cy // 2
        elif position == POS_SE:
            self.eye_l_x_next = cx
            self.eye_l_y_next = cy
        elif position == POS_S:
            self.eye_l_x_next = cx // 2
            self.eye_l_y_next = cy
        elif position == POS_SW:
            self.eye_l_x_next = 0
            self.eye_l_y_next = cy
        elif position == POS_W:
            self.eye_l_x_next = 0
            self.eye_l_y_next = cy // 2
        elif position == POS_NW:
            self.eye_l_x_next = 0
            self.eye_l_y_next = 0
        else:  # POS_DEFAULT (center)
            self.eye_l_x_next = cx // 2
            self.eye_l_y_next = cy // 2

    def set_autoblinker(self, active, interval=1, variation=4):
        self.autoblinker = active
        self.blink_interval = interval
        self.blink_interval_variation = variation

    def set_idle_mode(self, active, interval=1, variation=3):
        self.idle = active
        self.idle_interval = interval
        self.idle_interval_variation = variation

    def set_curiosity(self, curious):
        self.curious = curious

    # ============ Basic Animations ============

    def close(self, left=True, right=True):
        if left:
            self.eye_l_height_next = 1
            self.eye_l_open = False
        if right:
            self.eye_r_height_next = 1
            self.eye_r_open = False

    def open(self, left=True, right=True):
        if left:
            self.eye_l_open = True
        if right:
            self.eye_r_open = True

    def blink(self, left=True, right=True):
        self.close(left, right)
        self.open(left, right)

    def anim_confused(self):
        self.confused = True

    def anim_laugh(self):
        self.laugh = True

    # ============ Internal ============

    def _set_h_flicker(self, flicker, amplitude=2):
        self.h_flicker = flicker
        self.h_flicker_amplitude = amplitude

    def _set_v_flicker(self, flicker, amplitude=10):
        self.v_flicker = flicker
        self.v_flicker_amplitude = amplitude

    def _get_constraint_x(self):
        return (self.canvas_width
                - self.eye_l_width_current
                - self.space_between_current
                - self.eye_r_width_current)

    def _get_constraint_y(self):
        return self.canvas_height - self.eye_l_height_default

    # ============ Render ============

    def draw(self, draw, offset_x=0, offset_y=0):
        """Render eyes onto ImageDraw at given offset. Call once per frame."""
        now = _ticks_ms()

        # Curious mode — enlarge outer eye
        if self.curious:
            if self.eye_l_x_next <= 5:
                self.eye_l_height_offset = 8
            else:
                self.eye_l_height_offset = 0
            if self.eye_r_x_next >= self.canvas_width - self.eye_r_width_current - 5:
                self.eye_r_height_offset = 8
            else:
                self.eye_r_height_offset = 0
        else:
            self.eye_l_height_offset = 0
            self.eye_r_height_offset = 0

        # Height tweening
        self.eye_l_height_current = (
            self.eye_l_height_current
            + self.eye_l_height_next
            + self.eye_l_height_offset
        ) // 2
        self.eye_l_y += (self.eye_l_height_default - self.eye_l_height_current) // 2
        self.eye_l_y -= self.eye_l_height_offset // 2

        self.eye_r_height_current = (
            self.eye_r_height_current
            + self.eye_r_height_next
            + self.eye_r_height_offset
        ) // 2
        self.eye_r_y += (self.eye_r_height_default - self.eye_r_height_current) // 2
        self.eye_r_y -= self.eye_r_height_offset // 2

        # Reopen after blink
        if self.eye_l_open and self.eye_l_height_current <= 1 + self.eye_l_height_offset:
            self.eye_l_height_next = self.eye_l_height_default
        if self.eye_r_open and self.eye_r_height_current <= 1 + self.eye_r_height_offset:
            self.eye_r_height_next = self.eye_r_height_default

        # Width tweening
        self.eye_l_width_current = (self.eye_l_width_current + self.eye_l_width_next) // 2
        self.eye_r_width_current = (self.eye_r_width_current + self.eye_r_width_next) // 2

        # Space between
        self.space_between_current = (self.space_between_current + self.space_between_next) // 2

        # Position tweening
        self.eye_l_x = (self.eye_l_x + self.eye_l_x_next) // 2
        self.eye_l_y = (self.eye_l_y + self.eye_l_y_next) // 2

        self.eye_r_x_next = self.eye_l_x_next + self.eye_l_width_current + self.space_between_current
        self.eye_r_y_next = self.eye_l_y_next
        self.eye_r_x = (self.eye_r_x + self.eye_r_x_next) // 2
        self.eye_r_y = (self.eye_r_y + self.eye_r_y_next) // 2

        # Border radius tweening
        self.eye_l_border_radius_current = (
            self.eye_l_border_radius_current + self.eye_l_border_radius_next
        ) // 2
        self.eye_r_border_radius_current = (
            self.eye_r_border_radius_current + self.eye_r_border_radius_next
        ) // 2

        # Auto-blinker
        if self.autoblinker and now >= self.blink_timer:
            self.blink()
            self.blink_timer = (
                now
                + self.blink_interval * 1000
                + random.randint(0, self.blink_interval_variation) * 1000
            )

        # Laugh animation
        if self.laugh:
            if self.laugh_toggle:
                self._set_v_flicker(True, 5)
                self.laugh_animation_timer = now
                self.laugh_toggle = False
            elif now - self.laugh_animation_timer >= self.laugh_animation_duration:
                self._set_v_flicker(False, 0)
                self.laugh_toggle = True
                self.laugh = False

        # Confused animation
        if self.confused:
            if self.confused_toggle:
                self._set_h_flicker(True, 20)
                self.confused_animation_timer = now
                self.confused_toggle = False
            elif now - self.confused_animation_timer >= self.confused_animation_duration:
                self._set_h_flicker(False, 0)
                self.confused_toggle = True
                self.confused = False

        # Idle mode — random eye movement
        if self.idle and now >= self.idle_animation_timer:
            cx = self._get_constraint_x()
            cy = self._get_constraint_y()
            if cx > 0:
                self.eye_l_x_next = random.randint(0, cx)
            if cy > 0:
                self.eye_l_y_next = random.randint(0, cy)
            self.idle_animation_timer = (
                now
                + self.idle_interval * 1000
                + random.randint(0, self.idle_interval_variation) * 1000
            )

        # Compute flicker offsets
        flicker_x = 0
        flicker_y = 0
        if self.h_flicker:
            flicker_x = self.h_flicker_amplitude if self.h_flicker_alternate else -self.h_flicker_amplitude
            self.h_flicker_alternate = not self.h_flicker_alternate
        if self.v_flicker:
            flicker_y = self.v_flicker_amplitude if self.v_flicker_alternate else -self.v_flicker_amplitude
            self.v_flicker_alternate = not self.v_flicker_alternate

        # ===== DRAW EYES =====
        ox, oy = offset_x, offset_y

        # Left eye
        lx = ox + self.eye_l_x + flicker_x
        ly = oy + self.eye_l_y + flicker_y
        lw = self.eye_l_width_current
        lh = self.eye_l_height_current
        lr = self.eye_l_border_radius_current
        if lw > 0 and lh > 0:
            draw.rounded_rectangle(
                [lx, ly, lx + lw, ly + lh],
                radius=lr, fill=self.eye_color,
            )

        # Right eye
        rx = ox + self.eye_r_x + flicker_x
        ry = oy + self.eye_r_y + flicker_y
        rw = self.eye_r_width_current
        rh = self.eye_r_height_current
        rr = self.eye_r_border_radius_current
        if rw > 0 and rh > 0:
            draw.rounded_rectangle(
                [rx, ry, rx + rw, ry + rh],
                radius=rr, fill=self.eye_color,
            )

        # ===== MOOD EYELIDS =====
        bg = self.bg_color

        # Mood transitions
        if self.tired:
            self.eyelids_tired_height_next = self.eye_l_height_current // 2
            self.eyelids_angry_height_next = 0
        else:
            self.eyelids_tired_height_next = 0

        if self.angry:
            self.eyelids_angry_height_next = self.eye_l_height_current // 2
            self.eyelids_tired_height_next = 0
        else:
            self.eyelids_angry_height_next = 0

        if self.happy:
            self.eyelids_happy_bottom_offset_next = self.eye_l_height_current // 2
        else:
            self.eyelids_happy_bottom_offset_next = 0

        # Tired eyelids (top, slanted down on outer edge)
        self.eyelids_tired_height = (
            self.eyelids_tired_height + self.eyelids_tired_height_next
        ) // 2
        if self.eyelids_tired_height > 0:
            # Left eye: flat top-right, droops on left (outer)
            draw.polygon([
                (lx, ly - 1),
                (lx + lw, ly - 1),
                (lx, ly + self.eyelids_tired_height - 1),
            ], fill=bg)
            # Right eye: flat top-left, droops on right (outer)
            draw.polygon([
                (rx, ry - 1),
                (rx + rw, ry - 1),
                (rx + rw, ry + self.eyelids_tired_height - 1),
            ], fill=bg)

        # Angry eyelids (top, slanted down on inner edge)
        self.eyelids_angry_height = (
            self.eyelids_angry_height + self.eyelids_angry_height_next
        ) // 2
        if self.eyelids_angry_height > 0:
            # Left eye: flat top-left, droops on right (inner)
            draw.polygon([
                (lx, ly - 1),
                (lx + lw, ly - 1),
                (lx + lw, ly + self.eyelids_angry_height - 1),
            ], fill=bg)
            # Right eye: flat top-right, droops on left (inner)
            draw.polygon([
                (rx, ry - 1),
                (rx + rw, ry - 1),
                (rx, ry + self.eyelids_angry_height - 1),
            ], fill=bg)

        # Happy eyelids (bottom, rounded — covers lower portion)
        self.eyelids_happy_bottom_offset = (
            self.eyelids_happy_bottom_offset + self.eyelids_happy_bottom_offset_next
        ) // 2
        if self.eyelids_happy_bottom_offset > 0:
            # Left eye bottom
            hly = ly + lh - self.eyelids_happy_bottom_offset + 1
            draw.rounded_rectangle(
                [lx - 1, hly, lx + lw + 1, hly + self.eye_l_height_default],
                radius=lr, fill=bg,
            )
            # Right eye bottom
            hry = ry + rh - self.eyelids_happy_bottom_offset + 1
            draw.rounded_rectangle(
                [rx - 1, hry, rx + rw + 1, hry + self.eye_r_height_default],
                radius=rr, fill=bg,
            )
