"""Software warmth through the display gamma ramp.

The original ramp is kept so closing NightOwl puts the picture back.
Warmth replaces the ramp while it is above zero, including after a crash,
using the baseline saved before NightOwl first changed it.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p]
gdi32.CreateDCW.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.GetDeviceGammaRamp.restype = wintypes.BOOL
gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.restype = wintypes.BOOL


class GammaError(RuntimeError):
    pass


def _identity() -> ctypes.Array:
    ramp = (ctypes.c_ushort * 768)()
    for i in range(256):
        value = int(round(i * 65535 / 255))
        ramp[i] = ramp[256 + i] = ramp[512 + i] = value
    return ramp


class Gamma:
    def __init__(self, baseline_path: str) -> None:
        self._path = baseline_path
        self._baseline = _identity()
        self._available = True

    def capture(self, current_is_clean: bool) -> None:
        if current_is_clean:
            try:
                self._baseline = self._read()
            except GammaError:
                self._baseline = self._load() or _identity()
            self._store(self._baseline)
            return
        stored = self._load()
        self._baseline = stored if stored is not None else _identity()

    def apply(self, warmth: int) -> None:
        warmth = max(0, min(100, int(warmth)))
        if warmth == 0:
            self._write(self._baseline)
            return
        amount = warmth / 100
        red_gain = 1.0 + 0.05 * amount
        green_gain = 1.0 - 0.10 * amount
        blue_gain = 1.0 - 0.50 * amount
        ramp = (ctypes.c_ushort * 768)()
        for i in range(256):
            base = int(round(i * 65535 / 255))
            ramp[i] = _clamp_channel(base * red_gain)
            ramp[256 + i] = _clamp_channel(base * green_gain)
            ramp[512 + i] = _clamp_channel(base * blue_gain)
        self._write(ramp)

    def neutralize(self) -> None:
        """Clear a leftover warm ramp once. Live warmth is an overlay now."""
        ramp = self._read()
        midpoint_red = int(ramp[128])
        midpoint_blue = int(ramp[512 + 128])
        if midpoint_blue + 1500 >= midpoint_red:
            return
        self._write(_identity())

    def restore(self) -> None:
        try:
            self._write(self._baseline)
        except GammaError:
            pass

    def _read(self) -> ctypes.Array:
        ramp = (ctypes.c_ushort * 768)()
        hdc = gdi32.CreateDCW("DISPLAY", None, None, None)
        if not hdc:
            raise GammaError("No display device.")
        try:
            if not gdi32.GetDeviceGammaRamp(hdc, ramp):
                raise GammaError("Windows didn't share the color ramp.")
        finally:
            gdi32.DeleteDC(hdc)
        return ramp

    def _write(self, ramp: ctypes.Array) -> None:
        hdc = gdi32.CreateDCW("DISPLAY", None, None, None)
        if not hdc:
            self._available = False
            raise GammaError("No display device.")
        try:
            if not gdi32.SetDeviceGammaRamp(hdc, ramp):
                self._available = False
                raise GammaError("Windows didn't allow a color shift. HDR or Night Light may be holding it.")
            self._available = True
        finally:
            gdi32.DeleteDC(hdc)

    def _store(self, ramp: ctypes.Array) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "wb") as handle:
            handle.write(bytes(ramp))

    def _load(self) -> ctypes.Array | None:
        try:
            raw = open(self._path, "rb").read()
        except OSError:
            return None
        if len(raw) != 1536:
            return None
        ramp = (ctypes.c_ushort * 768)()
        ctypes.memmove(ramp, raw, 1536)
        return ramp


def _clamp_channel(value: float) -> int:
    return max(0, min(65535, int(round(value))))
