"""
Molty - Animated Robot Eyes Avatar.
State machine with RoboEyes animation engine.
Replaces the static Space Lobster sprite with expressive animated eyes.
"""

from enum import Enum
from PIL import ImageDraw

from .robo_eyes import (
    RoboEyes,
    MOOD_DEFAULT, MOOD_TIRED, MOOD_ANGRY, MOOD_HAPPY,
    POS_DEFAULT, POS_N, POS_S,
)


class MoltyState(Enum):
    """States for Molty character."""
    IDLE = "idle"
    LISTENING = "listening"
    WORKING = "working"
    SUCCESS = "success"
    ERROR = "error"
    THINKING = "thinking"


# State labels and colors (softened glassmorphism palette)
STATE_INFO = {
    MoltyState.IDLE: {
        "label": "Ready",
        "color": (70, 210, 230),
    },
    MoltyState.LISTENING: {
        "label": "Listening...",
        "color": (160, 80, 220),
    },
    MoltyState.WORKING: {
        "label": "Working...",
        "color": (235, 160, 40),
    },
    MoltyState.SUCCESS: {
        "label": "Done!",
        "color": (60, 220, 120),
    },
    MoltyState.ERROR: {
        "label": "Error!",
        "color": (220, 50, 70),
    },
    MoltyState.THINKING: {
        "label": "Thinking...",
        "color": (230, 60, 120),
    },
}


# Proximity modulation profiles — multipliers applied to blink/idle intervals
PROXIMITY_PROFILES = {
    "near":   {"blink_mult": 1.0, "idle_mult": 1.0, "mood": None,       "close": False},
    "medium": {"blink_mult": 1.5, "idle_mult": 1.5, "mood": None,       "close": False},
    "far":    {"blink_mult": 2.5, "idle_mult": 3.0, "mood": MOOD_TIRED, "close": False},
    "away":   {"blink_mult": 1.0, "idle_mult": 1.0, "mood": None,       "close": True},
}

# Base blink/idle settings per state (canonical values from _apply_state)
_BASE_STATE_SETTINGS = {
    MoltyState.IDLE:      {"blink": (True, 2, 3), "idle": (True, 2, 2)},
    MoltyState.LISTENING: {"blink": (True, 3, 2), "idle": (False,)},
    MoltyState.WORKING:   {"blink": (True, 2, 2), "idle": (True, 0, 1)},
    MoltyState.SUCCESS:   {"blink": (True, 3, 2), "idle": (False,)},
    MoltyState.ERROR:     {"blink": (False,),      "idle": (False,)},
    MoltyState.THINKING:  {"blink": (True, 3, 2), "idle": (True, 2, 2)},
}

# Transient states that should NOT be overridden by proximity
_TRANSIENT_STATES = {MoltyState.WORKING, MoltyState.SUCCESS, MoltyState.ERROR}


class Molty:
    """
    Animated robot eyes avatar with state-based expressions.
    Uses RoboEyes internally, keeps same external interface.
    """

    SPRITE_SIZE = (80, 80)

    def __init__(self, sprite_dir=None, sprite_size=None):
        if sprite_size:
            self.SPRITE_SIZE = sprite_size
        self.state = MoltyState.IDLE

        self._proximity_zone = "near"
        self._proximity_zone_prev = "near"
        self._wake_pending = False

        w, h = self.SPRITE_SIZE
        self.eyes = RoboEyes(canvas_width=w, canvas_height=h)
        self._apply_state()

    def _apply_state(self):
        """Configure RoboEyes for the current state."""
        info = STATE_INFO[self.state]
        color = info["color"]
        bg = (color[0] // 12, color[1] // 12, color[2] // 12)

        self.eyes.set_eye_color(color)
        self.eyes.set_bg_color(bg)

        if self.state == MoltyState.IDLE:
            self.eyes.set_mood(MOOD_DEFAULT)
            self.eyes.set_position(POS_DEFAULT)
            self.eyes.set_autoblinker(True, 2, 3)
            self.eyes.set_idle_mode(True, 2, 2)
            self.eyes.set_curiosity(False)

        elif self.state == MoltyState.LISTENING:
            self.eyes.set_mood(MOOD_DEFAULT)
            self.eyes.set_position(POS_N)
            self.eyes.set_autoblinker(True, 3, 2)
            self.eyes.set_idle_mode(False)
            self.eyes.set_curiosity(True)

        elif self.state == MoltyState.WORKING:
            self.eyes.set_mood(MOOD_DEFAULT)
            self.eyes.set_autoblinker(True, 2, 2)
            self.eyes.set_idle_mode(True, 0, 1)
            self.eyes.set_curiosity(False)

        elif self.state == MoltyState.SUCCESS:
            self.eyes.set_mood(MOOD_HAPPY)
            self.eyes.set_position(POS_DEFAULT)
            self.eyes.set_autoblinker(True, 3, 2)
            self.eyes.set_idle_mode(False)
            self.eyes.set_curiosity(False)
            self.eyes.anim_laugh()

        elif self.state == MoltyState.ERROR:
            self.eyes.set_mood(MOOD_ANGRY)
            self.eyes.set_position(POS_S)
            self.eyes.set_autoblinker(False)
            self.eyes.set_idle_mode(False)
            self.eyes.set_curiosity(False)
            self.eyes.anim_confused()

        elif self.state == MoltyState.THINKING:
            self.eyes.set_mood(MOOD_TIRED)
            self.eyes.set_position(POS_DEFAULT)
            self.eyes.set_autoblinker(True, 3, 2)
            self.eyes.set_idle_mode(True, 2, 2)
            self.eyes.set_curiosity(False)

    def set_state(self, state):
        """Set Molty's current state."""
        if isinstance(state, str):
            state = MoltyState(state)
        if state != self.state:
            self.state = state
            self._apply_state()
            self._apply_proximity_modulation()

    def set_proximity_zone(self, zone_str):
        """Update proximity zone and modulate eye behavior accordingly."""
        if zone_str == self._proximity_zone:
            return
        self._proximity_zone_prev = self._proximity_zone
        self._proximity_zone = zone_str

        # Detect approaching transition (far/away → near/medium)
        approaching = (
            self._proximity_zone_prev in ("far", "away")
            and self._proximity_zone in ("near", "medium")
        )
        if approaching:
            self._wake_pending = True

        self._apply_proximity_modulation()

    def _apply_proximity_modulation(self):
        """Modulate blink/idle based on proximity zone. Skip for transient states."""
        if self.state in _TRANSIENT_STATES:
            return

        profile = PROXIMITY_PROFILES.get(self._proximity_zone)
        if not profile:
            return

        # Handle wake-up reaction
        if self._wake_pending:
            self._wake_pending = False
            self._do_wake_reaction()
            return

        # Close eyes when away
        if profile["close"]:
            self.eyes.set_autoblinker(False)
            self.eyes.set_idle_mode(False)
            self.eyes.close()
            return

        # Override mood for far zone
        if profile["mood"] is not None:
            self.eyes.set_mood(profile["mood"])

        # Apply multipliers to base blink/idle settings
        base = _BASE_STATE_SETTINGS.get(self.state)
        if not base:
            return

        blink = base["blink"]
        if blink[0]:  # autoblinker active
            interval = int(blink[1] * profile["blink_mult"])
            variation = blink[2]
            self.eyes.set_autoblinker(True, interval, variation)

        idle = base["idle"]
        if len(idle) > 1 and idle[0]:  # idle mode active with params
            interval = int(idle[1] * profile["idle_mult"])
            variation = idle[2]
            self.eyes.set_idle_mode(True, interval, variation)

    def _do_wake_reaction(self):
        """Eyes open with brief upward glance when user approaches."""
        self.eyes.open()
        self.eyes.set_mood(MOOD_DEFAULT)
        self.eyes.set_position(POS_N)
        self.eyes.set_autoblinker(True, 2, 3)
        self.eyes.set_idle_mode(True, 2, 2)

    def get_state_label(self):
        """Get the display label for current state."""
        return STATE_INFO[self.state]["label"]

    def get_state_color(self):
        """Get the primary color for current state."""
        return STATE_INFO[self.state]["color"]

    def render(self, target_image, position, draw=None):
        """
        Render Molty onto a target image.

        Args:
            target_image: PIL Image to draw onto
            position: (x, y) top-left position
            draw: Optional ImageDraw object (created if not provided)
        """
        if draw is None:
            draw = ImageDraw.Draw(target_image)
        self.eyes.draw(draw, position[0], position[1])

    def get_sprite(self):
        """Get a snapshot as an RGBA image (backward compat)."""
        from PIL import Image
        img = Image.new('RGBA', self.SPRITE_SIZE, (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        self.eyes.draw(d, 0, 0)
        return img
