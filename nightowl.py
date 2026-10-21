"""Frozen entry point for the NightOwl executable."""

import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_set_dpi = getattr(_user32, "SetProcessDpiAwarenessContext", None)
if _set_dpi is not None:
    _set_dpi.argtypes = [ctypes.c_void_p]
    _set_dpi.restype = wintypes.BOOL
    _set_dpi(ctypes.c_void_p(-4))

from bridge.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
