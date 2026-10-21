"""DDC/CI access to the physical monitor backlight and contrast."""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", ctypes.c_wchar * 128),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL

dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, ctypes.POINTER(ctypes.c_ulong)]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR,
    ctypes.c_ulong,
    ctypes.POINTER(PHYSICAL_MONITOR),
]
dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.DestroyPhysicalMonitors.argtypes = [ctypes.c_ulong, ctypes.POINTER(PHYSICAL_MONITOR)]
dxva2.DestroyPhysicalMonitors.restype = wintypes.BOOL
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE,
    ctypes.c_byte,
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.c_ulong),
]
dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, ctypes.c_byte, ctypes.c_ulong]
dxva2.SetVCPFeature.restype = wintypes.BOOL

BRIGHTNESS = 0x10
CONTRAST = 0x12


class DdcError(RuntimeError):
    pass


class Ddc:
    """One physical monitor. Reopens the handle if a call fails."""

    def __init__(self) -> None:
        self._callback = None
        self._monitors: ctypes.Array[PHYSICAL_MONITOR] | None = None
        self._count = 0
        self._lock = threading.Lock()

    def open(self) -> None:
        self._close_unlocked()
        found: list[int] = []

        def _enum(hmon, _hdc, _rect, _data):
            found.append(hmon)
            return True

        self._callback = MONITORENUMPROC(_enum)
        if not user32.EnumDisplayMonitors(None, None, self._callback, 0) or not found:
            raise DdcError("No display is attached.")
        count = ctypes.c_ulong()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(found[0], ctypes.byref(count)):
            raise DdcError("The display has no DDC/CI monitor.")
        if count.value < 1:
            raise DdcError("The display has no DDC/CI monitor.")
        arr = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(found[0], count.value, arr):
            raise DdcError("Couldn't open the monitor link.")
        self._monitors = arr
        self._count = count.value

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        if self._monitors is not None and self._count:
            dxva2.DestroyPhysicalMonitors(self._count, self._monitors)
        self._monitors = None
        self._count = 0

    @property
    def description(self) -> str:
        if not self._monitors:
            return ""
        return self._monitors[0].szPhysicalMonitorDescription

    def _handle(self):
        if self._monitors is None:
            self.open()
        return self._monitors[0].hPhysicalMonitor

    def get_vcp(self, code: int) -> tuple[int, int]:
        with self._lock:
            return self._get_retry(code)

    def set_vcp(self, code: int, value: int) -> None:
        with self._lock:
            self._set_retry(code, value)
            time.sleep(0.08)
            try:
                current, _maximum = self._get_once(code)
            except DdcError:
                return
            if int(current) == int(value):
                return
            time.sleep(0.05)
            self._set_retry(code, value)

    def _get_retry(self, code: int) -> tuple[int, int]:
        last = "The monitor didn't answer."
        for attempt in range(2):
            try:
                return self._get_once(code)
            except DdcError as exc:
                last = str(exc)
                self._close_unlocked()
                if attempt == 0:
                    time.sleep(0.08)
        raise DdcError(last)

    def _set_retry(self, code: int, value: int) -> None:
        last = "The monitor didn't accept the change."
        for attempt in range(2):
            try:
                self._set_once(code, value)
                return
            except DdcError as exc:
                last = str(exc)
                self._close_unlocked()
                if attempt == 0:
                    time.sleep(0.1)
        raise DdcError(last)

    def _get_once(self, code: int) -> tuple[int, int]:
        kind = ctypes.c_ulong()
        current = ctypes.c_ulong()
        maximum = ctypes.c_ulong()
        ctypes.set_last_error(0)
        ok = dxva2.GetVCPFeatureAndVCPFeatureReply(
            self._handle(), code, ctypes.byref(kind), ctypes.byref(current), ctypes.byref(maximum)
        )
        if not ok:
            raise DdcError("The monitor didn't answer.")
        return int(current.value), int(maximum.value)

    def _set_once(self, code: int, value: int) -> None:
        ctypes.set_last_error(0)
        if not dxva2.SetVCPFeature(self._handle(), code, int(value)):
            raise DdcError("The monitor didn't accept the change.")
