"""Identify the attached panel and its current mode."""

from __future__ import annotations

import ctypes
import math
import winreg
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shcore = ctypes.WinDLL("shcore", use_last_error=True)

KNOWN = {
    "LC34G55T": {"line": "Odyssey G5", "curve": "1000R"},
}

MANUFACTURERS = {
    "SAM": "Samsung",
    "GSM": "LG",
    "DEL": "Dell",
    "AUS": "ASUS",
    "ACI": "ASUS",
    "MSI": "MSI",
    "LEN": "Lenovo",
    "ACR": "Acer",
    "BNQ": "BenQ",
    "PHL": "Philips",
    "SEC": "Samsung",
}


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM
)

user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
user32.EnumDisplaySettingsW.restype = wintypes.BOOL
shcore.GetDpiForMonitor.argtypes = [
    wintypes.HMONITOR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(wintypes.UINT),
]
shcore.GetDpiForMonitor.restype = ctypes.HRESULT


def geometry() -> dict:
    found: list[int] = []

    def _enum(hmon, _hdc, _rect, _data):
        found.append(hmon)
        return True

    callback = MONITORENUMPROC(_enum)
    user32.EnumDisplayMonitors(None, None, callback, 0)
    empty = {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0, "refresh": 0, "scale": 0}
    if not found:
        return empty

    chosen = found[0]
    info = MONITORINFOEXW()
    for hmon in found:
        probe = MONITORINFOEXW()
        probe.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(probe)):
            info = probe
            chosen = hmon
            if probe.dwFlags & 1:
                break

    rect = info.rcMonitor
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    refresh = 0
    if info.szDevice and user32.EnumDisplaySettingsW(info.szDevice, 0xFFFFFFFF, ctypes.byref(mode)):
        if mode.dmPelsWidth:
            width = int(mode.dmPelsWidth)
        if mode.dmPelsHeight:
            height = int(mode.dmPelsHeight)
        refresh = int(mode.dmDisplayFrequency)

    scale = 0
    dpi_x = wintypes.UINT()
    dpi_y = wintypes.UINT()
    if shcore.GetDpiForMonitor(chosen, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0 and dpi_x.value:
        scale = int(round(dpi_x.value / 96 * 100))

    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": width,
        "height": height,
        "refresh": refresh,
        "scale": scale,
    }


def identify() -> dict:
    panels = _read_edids()
    chosen = None
    for panel in panels:
        if _lookup(panel["name"]):
            chosen = panel
            break
    if chosen is None and panels:
        chosen = panels[0]
    if chosen is None:
        return {"title": "Display", "model": "", "detail": "", "mode": ""}

    known = _lookup(chosen["name"]) or {}
    manufacturer = MANUFACTURERS.get(chosen["manufacturer"], chosen["manufacturer"] or "Display")
    line = known.get("line", "")
    title = f"{manufacturer} {line}".strip() if line else manufacturer
    if not line and chosen["name"]:
        title = f"{manufacturer} {chosen['name']}".strip()
    size = _size_label(chosen["width_cm"], chosen["height_cm"])
    curve = known.get("curve", "")
    detail_parts = [part for part in (chosen["name"], " ".join(p for p in (size, curve) if p)) if part]
    detail = " · ".join(detail_parts)
    return {"title": title, "model": chosen["name"], "detail": detail, "mode": ""}


def describe(info: dict, geo: dict) -> dict:
    mode_parts = []
    if geo.get("width") and geo.get("height"):
        mode_parts.append(f"{geo['width']} × {geo['height']}")
    if geo.get("refresh"):
        mode_parts.append(f"{geo['refresh']} Hz")
    if geo.get("scale"):
        mode_parts.append(f"{geo['scale']}%")
    return {
        "title": info.get("title") or "Display",
        "model": info.get("model") or "",
        "detail": info.get("detail") or "",
        "mode": " · ".join(mode_parts),
    }


def _lookup(name: str) -> dict | None:
    key = (name or "").strip().upper()
    if not key:
        return None
    if key in KNOWN:
        return KNOWN[key]
    for model, meta in KNOWN.items():
        if key.startswith(model) or model.startswith(key):
            return meta
    return None


def _size_label(width_cm: int, height_cm: int) -> str:
    if width_cm <= 0 or height_cm <= 0:
        return ""
    diagonal = math.sqrt(width_cm ** 2 + height_cm ** 2) / 2.54
    inches = int(round(diagonal))
    if inches <= 0:
        return ""
    return f"{inches}″"


def _read_edids() -> list[dict]:
    panels: list[dict] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Enum\DISPLAY")
    except OSError:
        return panels
    device_index = 0
    while True:
        try:
            device = winreg.EnumKey(root, device_index)
        except OSError:
            break
        device_index += 1
        try:
            device_key = winreg.OpenKey(root, device)
        except OSError:
            continue
        instance_index = 0
        while True:
            try:
                instance = winreg.EnumKey(device_key, instance_index)
            except OSError:
                break
            instance_index += 1
            try:
                params = winreg.OpenKey(device_key, instance + r"\Device Parameters")
                raw, _ = winreg.QueryValueEx(params, "EDID")
            except OSError:
                continue
            parsed = _parse_edid(bytes(raw))
            if parsed:
                panels.append(parsed)
    return panels


def _parse_edid(edid: bytes) -> dict | None:
    if len(edid) < 128 or edid[:8] != bytes.fromhex("00ffffffffffff00"):
        return None
    manufacturer = _manufacturer(edid[8], edid[9])
    name = ""
    for offset in (54, 72, 90, 108):
        block = edid[offset : offset + 18]
        if len(block) < 18:
            continue
        if block[0] == 0 and block[1] == 0 and block[2] == 0 and block[3] == 0xFC:
            name = block[5:18].decode("cp437", "ignore").split("\n", 1)[0].strip()
    return {
        "manufacturer": manufacturer,
        "name": name,
        "width_cm": edid[21],
        "height_cm": edid[22],
    }


def _manufacturer(first: int, second: int) -> str:
    code = (first << 8) | second
    letters = [((code >> 10) & 0x1F), ((code >> 5) & 0x1F), code & 0x1F]
    return "".join(chr(letter + 64) for letter in letters if letter)
