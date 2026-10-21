"""Open the NightOwl window and the local control service."""

from __future__ import annotations

import atexit
import ctypes
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes
from pathlib import Path

from bridge.server import PORT, serve
from bridge.service import Service

WINDOW_TITLE = "NightOwl"


def enable_dpi() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if setter is not None:
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = wintypes.BOOL
        if setter(ctypes.c_void_p(-4)):
            return
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.HRESULT
        shcore.SetProcessDpiAwareness(2)
    except OSError:
        pass


def acquire_single_instance() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, "Local\\NightOwlBrightness")
    if not handle:
        return True
    if ctypes.get_last_error() != 183:
        acquire_single_instance.handle = handle
        return True
    focus_existing()
    return False


def focus_existing() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)


def dist_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parent.parent
    folder = root / "dist"
    if (folder / "index.html").is_file():
        return folder
    return None


def configure_stdio() -> None:
    if not getattr(sys, "frozen", False):
        return
    from bridge.service import app_dir

    stream = open(os.path.join(app_dir(), "nightowl.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def open_window(service: Service, url: str, hidden: bool = False) -> None:
    import webview

    window = webview.create_window(
        WINDOW_TITLE,
        url,
        width=456,
        height=880,
        min_size=(420, 640),
        resizable=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
        on_top=True,
        background_color="#0E0D0B",
        text_select=True,
        hidden=hidden,
    )

    def ready():
        service.attach_window(window)

    def on_closing():
        if service.allow_close:
            return True
        native = getattr(window, "native", None)
        if native is not None:
            native.Hide()
        else:
            service.hide_window()
        return False

    window.events.closing += on_closing
    webview.start(ready)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    enable_dpi()
    configure_stdio()
    if not acquire_single_instance():
        print("NightOwl is already open.")
        return 0
    service = Service()
    atexit.register(service.shutdown)
    service.start()
    try:
        httpd = serve(service, dist_dir())
    except OSError:
        print("NightOwl couldn't listen on port 8734. It may already be running.")
        service.shutdown()
        return 1
    thread = threading.Thread(target=httpd.serve_forever, name="nightowl-http", daemon=True)
    thread.start()
    snap = service.snapshot()
    monitor = snap["monitor"]
    print(f"NightOwl · {monitor['title']}")
    detail = " · ".join(part for part in (monitor.get("detail"), monitor.get("mode")) if part)
    if detail:
        print(detail)
    print(f"Backlight {snap['brightness']} / {snap['brightnessMax']} · contrast {snap['contrast']}")
    print(f"http://127.0.0.1:{PORT}")
    try:
        if "--api-only" in argv:
            while True:
                time.sleep(0.4)
        else:
            url = f"http://127.0.0.1:{PORT}/?shell=1"
            if "--dev" in argv:
                url = "http://127.0.0.1:5173/?shell=1"
            open_window(service, url, hidden="--background" in argv)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        service.shutdown()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
