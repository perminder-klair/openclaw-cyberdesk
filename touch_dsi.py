"""
Touch Handler for DSI Display using Pygame.
Handles FINGERDOWN/FINGERUP events from SDL2/pygame.
"""

import time
from dataclasses import dataclass
from typing import Optional, Callable, Tuple
from enum import Enum

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

import config_dsi as config


class TouchState(Enum):
    """Touch state machine states."""
    IDLE = "idle"
    TOUCHING = "touching"
    LONG_PRESS = "long_press"


@dataclass
class TouchPoint:
    """Represents a touch point."""
    x: int
    y: int
    finger_id: int
    timestamp: float


class TouchHandler:
    """
    Touch event handler for DSI display using pygame.
    Handles tap, long press, and drag gestures.
    """

    def __init__(self, screen_size: Tuple[int, int] = None):
        """
        Initialize touch handler.

        Args:
            screen_size: (width, height) of the display
        """
        self.screen_size = screen_size or (
            config.DSI_DISPLAY["width"],
            config.DSI_DISPLAY["height"]
        )

        # Touch configuration
        self.debounce_ms = config.TOUCH["debounce_ms"]
        self.long_press_ms = config.TOUCH["long_press_ms"]
        self.tap_threshold_px = config.TOUCH["tap_threshold_px"]

        # Touch state
        self._state = TouchState.IDLE
        self._touch_start: Optional[TouchPoint] = None
        self._last_tap_time = 0
        self._last_drag_pos: Optional[Tuple[int, int]] = None

        # Swipe detection
        self.swipe_threshold_px = 80
        self._gesture_locked = False
        self._gesture_is_swipe = False
        self._total_dx = 0
        self._total_dy = 0

        # Callbacks
        self.on_tap: Optional[Callable[[int, int], None]] = None
        self.on_long_press: Optional[Callable[[int, int], None]] = None
        self.on_drag: Optional[Callable[[int, int, int, int], None]] = None
        self.on_swipe: Optional[Callable[[int, int, str], None]] = None  # (start_x, start_y, "left"|"right")

    def process_event(self, event) -> bool:
        """
        Process a pygame event.

        Args:
            event: pygame event

        Returns:
            True if event was handled, False otherwise
        """
        if not PYGAME_AVAILABLE:
            return False

        if event.type == pygame.FINGERDOWN:
            return self._handle_finger_down(event)
        elif event.type == pygame.FINGERUP:
            return self._handle_finger_up(event)
        elif event.type == pygame.FINGERMOTION:
            return self._handle_finger_motion(event)

        # Also handle mouse events for desktop testing
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Left click
                return self._handle_mouse_down(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                return self._handle_mouse_up(event)
        elif event.type == pygame.MOUSEMOTION:
            if self._touch_start is not None and self._state == TouchState.TOUCHING:
                return self._handle_mouse_motion(event)

        return False

    def _handle_finger_down(self, event) -> bool:
        """Handle finger down event."""
        # Convert normalized coordinates to pixel coordinates
        x = int(event.x * self.screen_size[0])
        y = int(event.y * self.screen_size[1])

        self._touch_start = TouchPoint(
            x=x,
            y=y,
            finger_id=event.finger_id,
            timestamp=time.time()
        )
        self._state = TouchState.TOUCHING

        return True

    def _handle_finger_up(self, event) -> bool:
        """Handle finger up event."""
        if self._touch_start is None:
            return False

        x = int(event.x * self.screen_size[0])
        y = int(event.y * self.screen_size[1])

        touch_duration_ms = (time.time() - self._touch_start.timestamp) * 1000
        distance = self._calculate_distance(
            self._touch_start.x, self._touch_start.y, x, y
        )

        # Check for horizontal swipe before other gestures
        if self._gesture_locked and self._gesture_is_swipe and abs(self._total_dx) >= self.swipe_threshold_px:
            direction = "left" if self._total_dx < 0 else "right"
            if self.on_swipe:
                self.on_swipe(self._touch_start.x, self._touch_start.y, direction)
        elif distance <= self.tap_threshold_px:
            # Determine gesture type
            if touch_duration_ms >= self.long_press_ms:
                # Long press
                if self.on_long_press:
                    self.on_long_press(self._touch_start.x, self._touch_start.y)
            else:
                # Regular tap (check debounce)
                current_time = time.time() * 1000
                if current_time - self._last_tap_time > self.debounce_ms:
                    if self.on_tap:
                        self.on_tap(self._touch_start.x, self._touch_start.y)
                    self._last_tap_time = current_time

        # Reset state
        self._touch_start = None
        self._last_drag_pos = None
        self._gesture_locked = False
        self._gesture_is_swipe = False
        self._total_dx = 0
        self._total_dy = 0
        self._state = TouchState.IDLE

        return True

    def _handle_finger_motion(self, event) -> bool:
        """Handle finger motion event."""
        if self._touch_start is None:
            return False

        x = int(event.x * self.screen_size[0])
        y = int(event.y * self.screen_size[1])

        # Check for long press timeout during touch
        distance = self._calculate_distance(
            self._touch_start.x, self._touch_start.y, x, y
        )

        # If moved too far, it's not a long press anymore
        if distance > self.tap_threshold_px:
            # Compute incremental delta from last drag position
            if self._last_drag_pos is None:
                self._last_drag_pos = (self._touch_start.x, self._touch_start.y)
            dx = x - self._last_drag_pos[0]
            dy = y - self._last_drag_pos[1]
            self._last_drag_pos = (x, y)

            # Accumulate total deltas
            self._total_dx += dx
            self._total_dy += dy

            # Lock axis on first significant motion
            if not self._gesture_locked:
                total_abs_dx = abs(self._total_dx)
                total_abs_dy = abs(self._total_dy)
                if total_abs_dx > self.tap_threshold_px or total_abs_dy > self.tap_threshold_px:
                    self._gesture_locked = True
                    self._gesture_is_swipe = total_abs_dx > total_abs_dy

            # Only fire drag callback for vertical gestures (not horizontal swipes)
            if self._gesture_locked and not self._gesture_is_swipe:
                if self.on_drag:
                    self.on_drag(x, y, dx, dy)
            elif not self._gesture_locked:
                # Not locked yet, pass through drags
                if self.on_drag:
                    self.on_drag(x, y, dx, dy)

        return True

    def _handle_mouse_down(self, event) -> bool:
        """Handle mouse button down (for desktop testing)."""
        self._touch_start = TouchPoint(
            x=event.pos[0],
            y=event.pos[1],
            finger_id=0,
            timestamp=time.time()
        )
        self._state = TouchState.TOUCHING
        return True

    def _handle_mouse_motion(self, event) -> bool:
        """Handle mouse motion (for desktop testing, mirrors finger motion)."""
        if self._touch_start is None:
            return False

        x, y = event.pos
        distance = self._calculate_distance(
            self._touch_start.x, self._touch_start.y, x, y
        )

        if distance > self.tap_threshold_px:
            if self._last_drag_pos is None:
                self._last_drag_pos = (self._touch_start.x, self._touch_start.y)
            dx = x - self._last_drag_pos[0]
            dy = y - self._last_drag_pos[1]
            self._last_drag_pos = (x, y)

            self._total_dx += dx
            self._total_dy += dy

            if not self._gesture_locked:
                total_abs_dx = abs(self._total_dx)
                total_abs_dy = abs(self._total_dy)
                if total_abs_dx > self.tap_threshold_px or total_abs_dy > self.tap_threshold_px:
                    self._gesture_locked = True
                    self._gesture_is_swipe = total_abs_dx > total_abs_dy

            if self._gesture_locked and not self._gesture_is_swipe:
                if self.on_drag:
                    self.on_drag(x, y, dx, dy)
            elif not self._gesture_locked:
                if self.on_drag:
                    self.on_drag(x, y, dx, dy)

        return True

    def _handle_mouse_up(self, event) -> bool:
        """Handle mouse button up (for desktop testing)."""
        if self._touch_start is None:
            return False

        x, y = event.pos
        touch_duration_ms = (time.time() - self._touch_start.timestamp) * 1000
        distance = self._calculate_distance(
            self._touch_start.x, self._touch_start.y, x, y
        )

        # Check for horizontal swipe before other gestures
        if self._gesture_locked and self._gesture_is_swipe and abs(self._total_dx) >= self.swipe_threshold_px:
            direction = "left" if self._total_dx < 0 else "right"
            if self.on_swipe:
                self.on_swipe(self._touch_start.x, self._touch_start.y, direction)
        elif distance <= self.tap_threshold_px:
            if touch_duration_ms >= self.long_press_ms:
                if self.on_long_press:
                    self.on_long_press(self._touch_start.x, self._touch_start.y)
            else:
                current_time = time.time() * 1000
                if current_time - self._last_tap_time > self.debounce_ms:
                    if self.on_tap:
                        self.on_tap(self._touch_start.x, self._touch_start.y)
                    self._last_tap_time = current_time

        self._touch_start = None
        self._last_drag_pos = None
        self._gesture_locked = False
        self._gesture_is_swipe = False
        self._total_dx = 0
        self._total_dy = 0
        self._state = TouchState.IDLE
        return True

    def _calculate_distance(self, x1: int, y1: int, x2: int, y2: int) -> float:
        """Calculate distance between two points."""
        return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    def check_long_press(self) -> bool:
        """
        Check if current touch has exceeded long press threshold.
        Call this periodically during the main loop.

        Returns:
            True if long press was triggered
        """
        if self._state != TouchState.TOUCHING or self._touch_start is None:
            return False

        touch_duration_ms = (time.time() - self._touch_start.timestamp) * 1000

        if touch_duration_ms >= self.long_press_ms and self._state != TouchState.LONG_PRESS:
            self._state = TouchState.LONG_PRESS
            if self.on_long_press:
                self.on_long_press(self._touch_start.x, self._touch_start.y)
            return True

        return False

    def is_touching(self) -> bool:
        """Check if currently touching."""
        return self._state in (TouchState.TOUCHING, TouchState.LONG_PRESS)

    def get_touch_position(self) -> Optional[Tuple[int, int]]:
        """Get current touch position if touching."""
        if self._touch_start:
            return (self._touch_start.x, self._touch_start.y)
        return None

    def simulate_tap(self, x: int, y: int):
        """Simulate a tap event (for testing)."""
        if self.on_tap:
            self.on_tap(x, y)

    def simulate_long_press(self, x: int, y: int):
        """Simulate a long press event (for testing)."""
        if self.on_long_press:
            self.on_long_press(x, y)


class ButtonHitTester:
    """
    Helper class to test if touches hit buttons in the layout.
    """

    def __init__(self, screen_size: Tuple[int, int] = None, layout_config: dict = None):
        self.layout = layout_config or config.LAYOUT
        self.screen_size = screen_size or (
            config.DSI_DISPLAY["width"],
            config.DSI_DISPLAY["height"]
        )
        self._button_rects = []
        self._calculate_button_rects()

    def _calculate_button_rects(self):
        """Calculate button rectangles based on layout."""
        layout = self.layout
        screen_w, screen_h = self.screen_size

        # Button panel in left sidebar (offset by top bar)
        button_panel_x = 0
        button_panel_y = layout.get("top_bar_height", 0) + layout["button_panel_y_offset"]
        button_panel_w = layout["molty_panel_width"]
        button_panel_h = layout["button_panel_height"]

        # Calculate button sizes
        padding = layout["button_padding"]
        gap = layout["button_gap"]
        cols = layout["button_cols"]
        rows = layout["button_rows"]

        usable_w = button_panel_w - 2 * padding - (cols - 1) * gap
        usable_h = button_panel_h - 2 * padding - (rows - 1) * gap

        btn_w = usable_w // cols
        btn_h = usable_h // rows

        # Generate button rectangles
        self._button_rects = []
        for i, button_def in enumerate(config.BUTTONS):
            col = i % cols
            row = i // cols

            x = button_panel_x + padding + col * (btn_w + gap)
            y = button_panel_y + padding + row * (btn_h + gap)

            button_info = dict(button_def)
            button_info["rect"] = (x, y, btn_w, btn_h)
            self._button_rects.append(button_info)

    def find_button(self, x: int, y: int) -> Optional[dict]:
        """
        Find which button was tapped.

        Args:
            x: Touch X coordinate
            y: Touch Y coordinate

        Returns:
            Button dict if hit, None otherwise
        """
        for button in self._button_rects:
            bx, by, bw, bh = button["rect"]
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return button
        return None

    def get_button_rects(self) -> list:
        """Get all button rectangles for rendering."""
        return self._button_rects

    def recalculate(self):
        """Recalculate button positions (call after layout change)."""
        self._calculate_button_rects()
