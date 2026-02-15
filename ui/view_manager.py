"""
View manager for swipeable right-panel views.
Handles view switching and provides the active view for rendering.
"""

from typing import List, Optional
from ui.view_base import RightPanelView


# View index constants
ACTIVITY = 0
CRON = 1
HEALTH = 2
QUEUE = 3


class ViewManager:
    """Manages a list of right-panel views and tracks the active one."""

    def __init__(self):
        self._views: List[RightPanelView] = []
        self._active_index: int = 0

    def add_view(self, view: RightPanelView):
        """Add a view to the manager."""
        self._views.append(view)

    @property
    def active_view(self) -> Optional[RightPanelView]:
        """Get the currently active view."""
        if 0 <= self._active_index < len(self._views):
            return self._views[self._active_index]
        return None

    @property
    def active_index(self) -> int:
        return self._active_index

    @property
    def view_count(self) -> int:
        return len(self._views)

    def next_view(self):
        """Switch to the next view (wraps around)."""
        if not self._views:
            return
        old = self._active_index
        self._active_index = (self._active_index + 1) % len(self._views)
        if old != self._active_index:
            self._views[old].on_deactivate()
            self._views[self._active_index].on_activate()

    def prev_view(self):
        """Switch to the previous view (wraps around)."""
        if not self._views:
            return
        old = self._active_index
        self._active_index = (self._active_index - 1) % len(self._views)
        if old != self._active_index:
            self._views[old].on_deactivate()
            self._views[self._active_index].on_activate()

    def switch_to(self, index: int):
        """Switch to a specific view by index."""
        if not self._views or index < 0 or index >= len(self._views):
            return
        old = self._active_index
        self._active_index = index
        if old != self._active_index:
            self._views[old].on_deactivate()
            self._views[self._active_index].on_activate()
