"""UI-scale helpers — multiply hardcoded pixel sizes by the active
scale factor so widgets that don't naturally scale with font metrics
(QChart views with setFixedHeight, dialog setFixedSize, etc.) still
grow when the user picks Large or Extra Large in File > Customize.

Usage:

    from .scale import sx

    self.setFixedHeight(sx(200))     # 200 px at 100% scale, 260 at 130%
    self.setMinimumWidth(sx(180))

For widgets that need to react to a runtime scale change, register
a refresh callback:

    from .scale import register_listener
    register_listener(self._on_scale_changed)

The Customize dialog calls ``set_active(scale)`` whenever the user
picks a new scale, which fires every registered callback.
"""
from __future__ import annotations

from typing import Callable, List


_active_scale: float = 1.0
_listeners: List[Callable[[], None]] = []


def active() -> float:
    """Return the currently-active scale factor (e.g. 1.0, 1.15)."""
    return _active_scale


def set_active(scale: float) -> None:
    """Set the active scale + notify every listener so widgets can
    re-apply their sizing. Out-of-range values are clamped."""
    global _active_scale
    try:
        s = float(scale)
    except (TypeError, ValueError):
        return
    s = max(0.5, min(s, 2.5))
    if abs(s - _active_scale) < 0.001:
        return
    _active_scale = s
    for cb in list(_listeners):
        try:
            cb()
        except Exception:
            pass


def sx(px: float) -> int:
    """Scale a pixel value by the active scale factor. Returns int
    because Qt sizing functions all take ints."""
    return int(round(px * _active_scale))


def register_listener(callback: Callable[[], None]) -> None:
    """Register a callback to fire on every scale change. Use to
    re-apply setFixedHeight / setFixedWidth / etc. on widgets that
    should grow when the user picks a different scale."""
    _listeners.append(callback)


def unregister_listener(callback: Callable[[], None]) -> None:
    while callback in _listeners:
        _listeners.remove(callback)
