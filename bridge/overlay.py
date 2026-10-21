"""Click-through black veil so the desktop can go darker than the backlight floor.

NightOwl's own window is lifted back above the veil after every change.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from bridge.monitor import geometry

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_HOTKEY = 0x0312
WM_PAINT = 0x000F
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_APP_VEIL = 0x8000 + 7
TINT_COLOR = 0x002884FF

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_HIDE = 0
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
LWA_ALPHA = 0x02
BLACK_BRUSH = 4

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_UP = 0x26
VK_DOWN = 0x28
HOT_UP = 1
HOT_DOWN = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wintypes.HDC),
        ("fErase", wintypes.BOOL),
        ("rcPaint", RECT),
        ("fRestore", wintypes.BOOL),
        ("fIncUpdate", wintypes.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


def raise_topmost(hwnd) -> None:
    if not hwnd:
        return
    user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def _bind() -> None:
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.BeginPaint.restype = wintypes.HDC
    user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PAINTSTRUCT)]
    user32.EndPaint.restype = wintypes.BOOL
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(RECT), wintypes.HBRUSH]
    user32.FillRect.restype = ctypes.c_int
    user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    gdi32.GetStockObject.argtypes = [ctypes.c_int]
    gdi32.GetStockObject.restype = wintypes.HBRUSH
    gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPCWSTR,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    gdi32.SetTextColor.restype = wintypes.DWORD
    user32.DrawTextW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(RECT), wintypes.UINT]
    user32.DrawTextW.restype = ctypes.c_int
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    user32.InvalidateRect.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD


_bind()


class Veil:
    def __init__(self, on_hotkey, on_raise) -> None:
        self._on_hotkey = on_hotkey
        self._on_raise = on_raise
        self._proc = WNDPROC(self._wndproc)
        self.hwnd = None
        self.tint_hwnd = None
        self.thread_id = 0
        self.hotkeys = False
        self.ready = threading.Event()
        self._ack = threading.Event()
        self._veil_alpha = 0
        self._tint_alpha = 0
        self._amber = None
        self._tray = None
        self.on_open = None
        self.on_quit = None
        self._thread = threading.Thread(target=self._loop, name="nightowl-veil", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self.ready.wait(3)

    def set_level(self, veil: int, wait: bool = False) -> None:
        if not self.ready.wait(2) or not self.hwnd:
            return
        alpha = _veil_alpha(veil)
        if wait:
            self._ack.clear()
        user32.PostMessageW(self.hwnd, WM_APP_VEIL, alpha, 0)
        if wait:
            self._ack.wait(0.6)

    def set_warmth(self, warmth: int, wait: bool = False) -> None:
        if not self.ready.wait(2) or not self.tint_hwnd:
            return
        alpha = _warmth_alpha(warmth)
        user32.PostMessageW(self.tint_hwnd, WM_APP_VEIL, alpha, 1 if wait else 0)

    def note(self, brightness: int, osd: bool = True) -> None:
        from bridge.tray import WM_APP_STATUS

        if not self.hwnd:
            return
        user32.PostMessageW(self.hwnd, WM_APP_STATUS, int(brightness) & 0xFFFF, 1 if osd else 0)

    def stop(self) -> None:
        if self.hwnd:
            self.set_level(0, wait=True)
        if self.tint_hwnd:
            self.set_warmth(0, wait=False)
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()
        instance = kernel32.GetModuleHandleW(None)
        klass = WNDCLASSW()
        klass.lpfnWndProc = self._proc
        klass.hInstance = instance
        klass.hbrBackground = gdi32.GetStockObject(BLACK_BRUSH)
        klass.lpszClassName = "NightOwlVeil"
        atom = user32.RegisterClassW(ctypes.byref(klass))
        if not atom and ctypes.get_last_error() not in (0, 1410):
            self.ready.set()
            return
        self._amber = gdi32.CreateSolidBrush(TINT_COLOR)
        tint_class = WNDCLASSW()
        tint_class.lpfnWndProc = self._proc
        tint_class.hInstance = instance
        tint_class.hbrBackground = self._amber
        tint_class.lpszClassName = "NightOwlTint"
        user32.RegisterClassW(ctypes.byref(tint_class))
        osd_class = WNDCLASSW()
        osd_class.lpfnWndProc = self._proc
        osd_class.hInstance = instance
        osd_class.hbrBackground = gdi32.GetStockObject(BLACK_BRUSH)
        osd_class.lpszClassName = "NightOwlOsd"
        user32.RegisterClassW(ctypes.byref(osd_class))
        geo = geometry()
        ex_style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            "NightOwlVeil",
            "NightOwl veil",
            WS_POPUP,
            geo["left"],
            geo["top"],
            max(1, geo["right"] - geo["left"]),
            max(1, geo["bottom"] - geo["top"]),
            None,
            None,
            instance,
            None,
        )
        self.tint_hwnd = user32.CreateWindowExW(
            ex_style,
            "NightOwlTint",
            "NightOwl warmth",
            WS_POPUP,
            geo["left"],
            geo["top"],
            max(1, geo["right"] - geo["left"]),
            max(1, geo["bottom"] - geo["top"]),
            None,
            None,
            instance,
            None,
        )
        from bridge.tray import Tray

        self._tray = Tray(self.on_open, self.on_quit, self._on_hotkey)
        self._tray.install(self.hwnd)
        mods = MOD_CONTROL | MOD_ALT | MOD_SHIFT
        up = bool(user32.RegisterHotKey(self.hwnd, HOT_UP, mods, VK_UP))
        down = bool(user32.RegisterHotKey(self.hwnd, HOT_DOWN, mods, VK_DOWN))
        self.hotkeys = up and down
        user32.SetTimer(self.hwnd, 3, 1000, None)
        self.ready.set()
        message = MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0 or result == -1:
                break
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        if self._tray is not None:
            self._tray.remove()
            self._tray = None
        if self.hwnd:
            user32.UnregisterHotKey(self.hwnd, HOT_UP)
            user32.UnregisterHotKey(self.hwnd, HOT_DOWN)
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.tint_hwnd:
            user32.DestroyWindow(self.tint_hwnd)
            self.tint_hwnd = None

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if self._tray is not None and self._tray.handle(hwnd, msg, wparam, lparam):
            return 0
        if msg == WM_APP_VEIL:
            alpha = int(wparam) & 0xFF
            if hwnd == self.tint_hwnd:
                self._tint_alpha = alpha
            else:
                self._veil_alpha = alpha
            self._apply_alpha(hwnd, alpha)
            self._ack.set()
            return 0
        if msg == 0x0113 and int(wparam) == 3:
            if self._veil_alpha > 0 and self.hwnd:
                self._apply_alpha(self.hwnd, self._veil_alpha)
            if self._tint_alpha > 0 and self.tint_hwnd:
                self._apply_alpha(self.tint_hwnd, self._tint_alpha)
            return 0
        if msg == WM_HOTKEY:
            step = 5 if int(wparam) == HOT_UP else -5 if int(wparam) == HOT_DOWN else 0
            if step and self._on_hotkey:
                self._on_hotkey(step)
            return 0
        if msg == WM_PAINT:
            paint = PAINTSTRUCT()
            hdc = user32.BeginPaint(hwnd, ctypes.byref(paint))
            rect = RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            if self._tray is not None and hwnd == self._tray.osd_hwnd:
                user32.FillRect(hdc, ctypes.byref(rect), gdi32.GetStockObject(BLACK_BRUSH))
                font = gdi32.CreateFontW(-28, 0, 0, 0, 600, 0, 0, 0, 1, 0, 0, 0, 0, "Segoe UI")
                old = gdi32.SelectObject(hdc, font)
                gdi32.SetBkMode(hdc, 1)
                gdi32.SetTextColor(hdc, 0x004AA1F0)
                user32.DrawTextW(hdc, self._tray._osd_text, -1, ctypes.byref(rect), 0x25)
                gdi32.SelectObject(hdc, old)
                gdi32.DeleteObject(font)
            else:
                brush = self._amber if hwnd == self.tint_hwnd and self._amber else gdi32.GetStockObject(BLACK_BRUSH)
                user32.FillRect(hdc, ctypes.byref(rect), brush)
            user32.EndPaint(hwnd, ctypes.byref(paint))
            return 0
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _apply_alpha(self, hwnd, alpha: int) -> None:
        if alpha <= 0:
            user32.ShowWindow(hwnd, SW_HIDE)
            return
        geo = geometry()
        user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)
        user32.SetWindowPos(
            hwnd,
            ctypes.c_void_p(HWND_TOPMOST),
            geo["left"],
            geo["top"],
            max(1, geo["right"] - geo["left"]),
            max(1, geo["bottom"] - geo["top"]),
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        self._raise_stack()

    def _raise_stack(self) -> None:
        flags = 0x0001 | 0x0002 | 0x0010
        if self.tint_hwnd and self._tint_alpha > 0:
            user32.SetWindowPos(self.tint_hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, flags)
        if self.hwnd and self._veil_alpha > 0:
            user32.SetWindowPos(self.hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, flags)
        if self._tray is not None and self._tray.osd_hwnd and user32.IsWindowVisible(self._tray.osd_hwnd):
            user32.SetWindowPos(self._tray.osd_hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, flags)
        if self._on_raise:
            self._on_raise()


def _veil_alpha(veil: int) -> int:
    level = max(0, min(100, int(veil)))
    if level <= 0:
        return 0
    return int(round((level / 100) ** 0.72 * 236))


def _warmth_alpha(warmth: int) -> int:
    level = max(0, min(100, int(warmth)))
    if level <= 0:
        return 0
    return int(round((level / 100) ** 0.85 * 96))
