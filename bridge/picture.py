"""Whole-desktop contrast.

The panel accepts a contrast number and does not change the picture, and the
graphics-card contrast control does not change the pixels Windows draws.
This applies a color matrix to the desktop itself. 50 is the normal picture.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_mag = ctypes.WinDLL("magnification", use_last_error=True)
_mag.MagInitialize.restype = wintypes.BOOL
_mag.MagSetFullscreenColorEffect.argtypes = [ctypes.c_void_p]
_mag.MagSetFullscreenColorEffect.restype = wintypes.BOOL

_ready = False


def _matrix(level: int) -> ctypes.Array:
    gain = max(0, min(100, int(level))) / 50
    shift = (1.0 - gain) / 2
    return (ctypes.c_float * 25)(
        gain, 0, 0, 0, 0,
        0, gain, 0, 0, 0,
        0, 0, gain, 0, 0,
        0, 0, 0, 1, 0,
        shift, shift, shift, 0, 1,
    )


def _ensure() -> bool:
    global _ready
    if _ready:
        return True
    _ready = bool(_mag.MagInitialize())
    return _ready


def set_contrast(level: int) -> bool:
    if not _ensure():
        return False
    matrix = _matrix(level)
    return bool(_mag.MagSetFullscreenColorEffect(ctypes.cast(matrix, ctypes.c_void_p)))


def reset() -> None:
    if _ready:
        set_contrast(50)
