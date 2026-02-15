"""
Abstract base class for swipeable right-panel views.
Each view renders into a given region of the PIL draw context.
"""

from abc import ABC, abstractmethod
from PIL import ImageDraw


class RightPanelView(ABC):
    """Base class for right-panel views (activity, health, queue, cron)."""

    def __init__(self, glass_renderer, fonts: dict):
        self.glass = glass_renderer
        self.fonts = fonts
        self._scroll_offset = 0

    @abstractmethod
    def render(self, draw: ImageDraw.Draw, x: int, y: int,
               width: int, height: int):
        """Render the view content into the given region."""

    @abstractmethod
    def get_title(self) -> str:
        """Return the view title string (e.g. 'ACTIVITY')."""

    def on_tap(self, x: int, y: int) -> bool:
        """Handle tap within the view region. Return True if consumed."""
        return False

    def on_drag(self, x: int, y: int, dx: int, dy: int) -> bool:
        """Handle drag within the view region. Return True if consumed."""
        return False

    def on_activate(self):
        """Called when this view becomes the active view."""

    def on_deactivate(self):
        """Called when this view is no longer the active view."""
