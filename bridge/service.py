"""NightOwl state: dimming, contrast, and warmth."""

from __future__ import annotations

import json
import os
import queue
import threading

from bridge.ddc import BRIGHTNESS, CONTRAST, Ddc, DdcError
from bridge.picture import reset as reset_picture
from bridge.picture import set_contrast as set_picture_contrast
from bridge.gamma import Gamma, GammaError
from bridge.monitor import describe, geometry, identify
from bridge.overlay import Veil, raise_topmost

VEIL_MAX = 100
PRESETS = (
    {"id": "night", "label": "Night", "brightness": 8, "veil": 55, "warmth": 48},
    {"id": "evening", "label": "Evening", "brightness": 40, "veil": 15, "warmth": 32},
    {"id": "desk", "label": "Desk", "brightness": 78, "veil": 0, "warmth": 28},
    {"id": "day", "label": "Day", "brightness": 100, "veil": 0, "warmth": 0},
)

DDC_ERROR = "This monitor didn't answer. Turn on DDC/CI in its menu, then try again."
GAMMA_ERROR = "Windows kept the color ramp. Warmth stays off while HDR or Night Light is holding it."


def app_dir() -> str:
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(root, "NightOwl")
    os.makedirs(folder, exist_ok=True)
    return folder


def _clamp(value: int, limit: int) -> int:
    return max(0, min(limit, int(value)))


def _overlay_level(brightness: int, veil: int) -> int:
    """This panel accepts a backlight number and does not change the picture.

    Brightness therefore dims the desktop directly. Deeper dark adds on top.
    """
    shortfall = _clamp(100 - int(brightness), 100)
    return _clamp(int(veil) + shortfall, VEIL_MAX)


def _match_preset(brightness: int, veil: int, warmth: int) -> str | None:
    for preset in PRESETS:
        if preset["brightness"] == brightness and preset["veil"] == veil and preset["warmth"] == warmth:
            return preset["id"]
    return None


class Service:
    def __init__(self) -> None:
        self.ddc = Ddc()
        self.gamma = Gamma(os.path.join(app_dir(), "gamma-baseline.bin"))
        self.veil_window = Veil(self.nudge_brightness, self.raise_app)
        self.veil_window.on_open = self.show_window
        self.veil_window.on_quit = self.request_quit
        self.allow_close = False
        self.hub_listeners: list[queue.Queue] = []
        self._listeners_lock = threading.Lock()
        self._lock = threading.Lock()
        self._hw: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._hardware_loop, name="nightowl-ddc", daemon=True)
        self._save_timer: threading.Timer | None = None
        self._window = None
        self._settings_path = os.path.join(app_dir(), "settings.json")
        self._saved = self._read_settings()
        self._touched = bool(self._saved)
        self.shell = False
        self.connected = False
        self.error: str | None = None
        self.brightness = 0
        self.brightness_max = 100
        self.contrast = 75
        self.contrast_max = 100
        self.veil = 0
        self.warmth = 0
        self.preset: str | None = None
        self.monitor = {"title": "Display", "model": "", "detail": "", "mode": ""}
        self._seq = 0
        self._closed = False

    def start(self) -> None:
        try:
            self.gamma.neutralize()
        except GammaError:
            pass
        self.veil_window.start()
        self._worker.start()
        self.refresh_monitor(apply_saved=True)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.veil_window.stop()
        if self._touched:
            self._save_now()
        self.ddc.close()
        self._hw.put(None)

    def attach_window(self, window) -> None:
        self._window = window
        with self._lock:
            self.shell = True
            snap = self._snapshot()
        self._publish(snap)
        self.raise_app()

    def subscribe(self) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=32)
        with self._listeners_lock:
            self.hub_listeners.append(listener)
        listener.put(self.snapshot_json())
        return listener

    def unsubscribe(self, listener: queue.Queue) -> None:
        with self._listeners_lock:
            if listener in self.hub_listeners:
                self.hub_listeners.remove(listener)

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot(), separators=(",", ":"))

    def refresh_monitor(self, apply_saved: bool = False) -> dict:
        info = describe(identify(), geometry())
        try:
            current, maximum = self.ddc.get_vcp(BRIGHTNESS)
            contrast, contrast_max = self.ddc.get_vcp(CONTRAST)
        except DdcError:
            with self._lock:
                self.connected = False
                self.monitor = info
                self.error = DDC_ERROR
                if apply_saved:
                    self.veil = _clamp(int(self._saved.get("veil", 0) or 0), VEIL_MAX)
                    self.warmth = _clamp(int(self._saved.get("warmth", 0) or 0), 100)
                veil_level = self.veil
                warmth_level = self.warmth
                snap = self._snapshot()
            self.veil_window.set_warmth(warmth_level)
            self.veil_window.set_level(_overlay_level(snap["brightness"], veil_level))
            self.veil_window.note(snap["brightness"], osd=False)
            self._publish(snap)
            return snap

        saved_brightness = self._saved.get("brightness") if apply_saved else None
        saved_contrast = self._saved.get("contrast") if apply_saved else None
        saved_veil = _clamp(int(self._saved.get("veil", 0)), VEIL_MAX) if apply_saved else self.veil
        saved_warmth = _clamp(int(self._saved.get("warmth", 0)), 100) if apply_saved else self.warmth
        brightness = int(current)
        contrast_value = int(contrast)
        if saved_brightness is not None:
            brightness = _clamp(int(saved_brightness), int(maximum) or 100)
        if saved_contrast is not None:
            contrast_value = _clamp(int(saved_contrast), int(contrast_max) or 100)

        with self._lock:
            self.connected = True
            self.error = None
            self.monitor = info
            self.brightness_max = int(maximum) or 100
            self.contrast_max = int(contrast_max) or 100
            self.brightness = brightness
            self.contrast = contrast_value
            self.veil = saved_veil
            self.warmth = saved_warmth
            self.preset = _match_preset(self.brightness, self.veil, self.warmth)
            snap = self._snapshot()

        if saved_brightness is not None and brightness != int(current):
            self._hw.put(("brightness", brightness))
        if saved_contrast is not None:
            self._hw.put(("contrast", contrast_value))
        self.veil_window.set_warmth(saved_warmth)
        self.veil_window.set_level(_overlay_level(snap["brightness"], snap["veil"]))
        self.veil_window.note(snap["brightness"], osd=False)
        self._publish(snap)
        return snap

    def apply(self, partial: dict) -> dict:
        hardware: list[tuple[str, int]] = []
        veil_level = None
        warmth_level = None
        with self._lock:
            if "brightness" in partial:
                self.brightness = _clamp(int(partial["brightness"]), self.brightness_max)
                if self.connected:
                    hardware.append(("brightness", self.brightness))
                    if self.error == DDC_ERROR:
                        self.error = None
            if "contrast" in partial:
                self.contrast = _clamp(int(partial["contrast"]), self.contrast_max or 100)
                hardware.append(("contrast", self.contrast))
            if "veil" in partial:
                self.veil = _clamp(int(partial["veil"]), VEIL_MAX)
                veil_level = self.veil
            if "warmth" in partial:
                self.warmth = _clamp(int(partial["warmth"]), 100)
                warmth_level = self.warmth
            self.preset = _match_preset(self.brightness, self.veil, self.warmth)
            snap = self._snapshot()
        for item in hardware:
            self._hw.put(item)
        if veil_level is not None or "brightness" in partial:
            self.veil_window.set_level(_overlay_level(snap["brightness"], snap["veil"]))
        if warmth_level is not None:
            self.veil_window.set_warmth(warmth_level)
        if "brightness" in partial:
            self.veil_window.note(snap["brightness"])
        self._schedule_save()
        self._publish(snap)
        return snap

    def apply_preset(self, preset_id: str) -> dict:
        preset = next((item for item in PRESETS if item["id"] == preset_id), None)
        if preset is None:
            raise KeyError(preset_id)
        return self.apply(
            {"brightness": preset["brightness"], "veil": preset["veil"], "warmth": preset["warmth"]}
        )

    def nudge_brightness(self, delta: int) -> None:
        if self._closed:
            return
        with self._lock:
            self.brightness = _clamp(self.brightness + delta, self.brightness_max)
            self.preset = _match_preset(self.brightness, self.veil, self.warmth)
            value = self.brightness
            veil_level = self.veil
            connected = self.connected
            snap = self._snapshot()
        if connected:
            self._hw.put(("brightness", value))
        self.veil_window.set_level(_overlay_level(value, veil_level))
        self.veil_window.note(value)
        self._schedule_save()
        self._publish(snap)

    def minimize(self) -> None:
        window = self._window
        if window is not None:
            window.minimize()

    def hide_window(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.hide()
        except Exception:
            pass

    def show_window(self) -> None:
        window = self._window
        if window is not None:
            try:
                window.show()
            except Exception:
                pass
        self.raise_app()

    def request_quit(self) -> None:
        self.allow_close = True
        window = self._window
        if window is not None:
            try:
                window.destroy()
                return
            except Exception:
                pass
        self.shutdown()

    def close_window(self) -> None:
        self.hide_window()

    def raise_app(self) -> None:
        raise_topmost(_window_handle(self._window))

    def _hardware_loop(self) -> None:
        while True:
            item = self._hw.get()
            if item is None:
                reset_picture()
                return
            pending = [item]
            while True:
                try:
                    nxt = self._hw.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    reset_picture()
                    return
                pending.append(nxt)
            latest: dict[str, int] = {}
            for key, value in pending:
                latest[key] = value
            for key, value in latest.items():
                if key == "contrast" and set_picture_contrast(value):
                    continue
                code = BRIGHTNESS if key == "brightness" else CONTRAST
                try:
                    self.ddc.set_vcp(code, value)
                except DdcError:
                    self._read_back(key)

    def _read_back(self, key: str) -> None:
        code = BRIGHTNESS if key == "brightness" else CONTRAST
        try:
            current, _maximum = self.ddc.get_vcp(code)
        except DdcError:
            with self._lock:
                self.connected = False
                self.error = DDC_ERROR
                snap = self._snapshot()
            self._publish(snap)
            return
        with self._lock:
            if key == "brightness":
                self.brightness = int(current)
            else:
                self.contrast = int(current)
            self.connected = True
            self.error = DDC_ERROR
            self.preset = _match_preset(self.brightness, self.veil, self.warmth)
            snap = self._snapshot()
        self._publish(snap)

    def _snapshot(self) -> dict:
        self._seq += 1
        return {
            "seq": self._seq,
            "shell": self.shell,
            "connected": self.connected,
            "error": self.error,
            "hotkeys": self.veil_window.hotkeys,
            "brightness": self.brightness,
            "brightnessMax": self.brightness_max,
            "contrast": self.contrast,
            "contrastMax": self.contrast_max,
            "veil": self.veil,
            "veilMax": VEIL_MAX,
            "warmth": self.warmth,
            "warmthMax": 100,
            "preset": self.preset,
            "presets": [dict(item) for item in PRESETS],
            "monitor": dict(self.monitor),
        }

    def _publish(self, snap: dict) -> None:
        payload = json.dumps(snap, separators=(",", ":"))
        with self._listeners_lock:
            listeners = list(self.hub_listeners)
        for listener in listeners:
            try:
                listener.put_nowait(payload)
            except queue.Full:
                try:
                    listener.get_nowait()
                except queue.Empty:
                    pass
                try:
                    listener.put_nowait(payload)
                except queue.Full:
                    pass

    def _schedule_save(self) -> None:
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.35, self._save_now)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _save_now(self) -> None:
        with self._lock:
            payload = {
                "version": 3,
                "brightness": self.brightness,
                "contrast": self.contrast,
                "veil": self.veil,
                "warmth": self.warmth,
            }
        try:
            with open(self._settings_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            self._saved = payload
        except OSError:
            pass

    def _read_settings(self) -> dict:
        try:
            with open(self._settings_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        version = int(data.get("version", 1) or 1)
        if version < 2:
            # The stored backlight number never changed this panel's picture.
            data["brightness"] = 100
        if version < 3:
            # The stored contrast number never changed this panel's picture.
            # 50 is the normal picture.
            data["contrast"] = 50
            data["version"] = 3
        return data


def _window_handle(window):
    if window is None:
        return None
    native = getattr(window, "native", None)
    if native is None:
        return None
    handle = getattr(native, "Handle", None)
    if handle is None:
        return None
    if hasattr(handle, "ToInt64"):
        return handle.ToInt64()
    try:
        return int(handle)
    except (TypeError, ValueError):
        return None
