"""System-tray icon. Scroll over it changes the backlight, like the volume icon."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

WM_MOUSEWHEEL = 0x020A
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_PAINT = 0x000F
WM_TIMER = 0x0113
WM_USER = 0x0400
NIN_SELECT = WM_USER
WM_TRAY = WM_USER + 21
WM_APP_SCROLL = 0x8000 + 9
WM_APP_STATUS = 0x8000 + 10

WH_MOUSE_LL = 14
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_SHOWTIP = 0x80
NOTIFYICON_VERSION_4 = 4
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
MF_STRING = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
IDI_APPLICATION = 32512
SW_HIDE = 0
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
LWA_ALPHA = 0x02
DT_CENTER = 0x01
DT_VCENTER = 0x04
DT_SINGLELINE = 0x20
TRANSPARENT = 1
OSD_TIMER = 2


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("guidItem", ctypes.c_byte * 16),
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
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _bind() -> None:
    user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(RECT)]
    shell32.Shell_NotifyIconGetRect.restype = ctypes.HRESULT
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
    user32.TrackPopupMenu.restype = wintypes.UINT
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE


_bind()


def icon_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "assets" / "nightowl.ico"


class Tray:
    def __init__(self, on_open, on_quit, on_scroll) -> None:
        self.on_open = on_open
        self.on_quit = on_quit
        self.on_scroll = on_scroll
        self.hwnd = None
        self.ok = False
        self._icon = None
        self._hook = None
        self._hook_proc = HOOKPROC(self._mouse)
        self._wheel = 0
        self._menu_at = 0.0
        self._brightness = 0
        self.osd_hwnd = None
        self._osd_text = "0"

    def install(self, hwnd) -> bool:
        self.hwnd = hwnd
        self._icon = self._load_icon()
        nid = self._nid(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._icon
        nid.szTip = "NightOwl"
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            print(f"NightOwl tray icon failed ({ctypes.get_last_error()}).")
            return False
        version = self._nid(0)
        version.uTimeoutOrVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(version))
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._hook_proc, None, 0)
        self.ok = True
        return True

    def remove(self) -> None:
        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        if self.ok and self.hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid(0)))
            self.ok = False
        if self.osd_hwnd:
            user32.DestroyWindow(self.osd_hwnd)
            self.osd_hwnd = None
        if self._icon:
            user32.DestroyIcon(self._icon)
            self._icon = None

    def handle(self, hwnd, msg, wparam, lparam) -> bool:
        if hwnd != self.hwnd:
            return False
        if msg == WM_TRAY:
            self._on_tray(lparam)
            return True
        if msg == WM_APP_SCROLL:
            notches = max(1, int(lparam))
            step = 4 * notches if int(wparam) else -4 * notches
            if self.on_scroll:
                self.on_scroll(step)
            return True
        if msg == WM_APP_STATUS:
            self._brightness = int(wparam) & 0xFFFF
            self._tip(self._brightness)
            return True
        return False

    def _on_tray(self, lparam) -> None:
        code = int(lparam) & 0xFFFF
        if code in (NIN_SELECT, WM_LBUTTONUP, WM_LBUTTONDBLCLK):
            if self.on_open:
                self.on_open()
            return
        if code not in (WM_CONTEXTMENU, WM_RBUTTONUP):
            return
        now = time.monotonic()
        if now - self._menu_at < 0.4:
            return
        self._menu_at = now
        self._menu()

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        user32.AppendMenuW(menu, MF_STRING, 1, "Open NightOwl")
        user32.AppendMenuW(menu, MF_STRING, 2, "Quit")
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            point.x,
            point.y,
            0,
            self.hwnd,
            None,
        )
        user32.PostMessageW(self.hwnd, 0, 0, 0)
        user32.DestroyMenu(menu)
        if cmd == 1 and self.on_open:
            self.on_open()
        elif cmd == 2 and self.on_quit:
            self.on_quit()

    def _mouse(self, nCode, wParam, lParam):
        if nCode >= 0 and int(wParam) == WM_MOUSEWHEEL and self.hwnd:
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            rect = self._icon_rect()
            if rect is not None and _inside(info.pt.x, info.pt.y, rect):
                delta = ctypes.c_short((int(info.mouseData) >> 16) & 0xFFFF).value
                self._wheel += delta
                notches = int(self._wheel / 120)
                if notches:
                    self._wheel -= notches * 120
                    user32.PostMessageW(self.hwnd, WM_APP_SCROLL, 1 if notches > 0 else 0, abs(notches))
                    return 1
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _icon_rect(self):
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(ident)
        ident.hWnd = self.hwnd
        ident.uID = 1
        rect = RECT()
        if shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect)) != 0:
            return None
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0 or width > 64 or height > 64:
            return None
        return rect

    def _nid(self, flags: int) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        return nid

    def _tip(self, brightness: int) -> None:
        nid = self._nid(NIF_TIP | NIF_SHOWTIP)
        nid.szTip = f"NightOwl · {int(brightness)}%"
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _load_icon(self):
        path = icon_path()
        if path.is_file():
            handle = user32.LoadImageW(None, str(path), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
            if handle:
                return handle
        return user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))

def _inside(x: int, y: int, rect: RECT) -> bool:
    return rect.left <= x < rect.right and rect.top <= y < rect.bottom


def _bind_osd() -> None:
    user32.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
    user32.InvalidateRect.restype = wintypes.BOOL
    user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
    user32.SetTimer.restype = ctypes.c_size_t
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


_bind_osd()
