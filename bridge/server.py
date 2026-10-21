"""Local control API and the built NightOwl window."""

from __future__ import annotations

import json
import mimetypes
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = 8734

EXTRA_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".json": "application/json; charset=utf-8",
}


def as_int(value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected a number")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("expected a whole number")
    return int(value)


def make_handler(service, dist: Path | None):
    root = dist.resolve() if dist else None

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                self._send_json(200, service.snapshot())
                return
            if path == "/api/events":
                self._events()
                return
            if path.startswith("/api/"):
                self._send_json(404, {"error": "Not found"})
                return
            self._file(path)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._body()
                if path == "/api/apply":
                    partial = {}
                    for key in ("brightness", "contrast", "veil", "warmth"):
                        if key in body:
                            partial[key] = as_int(body[key])
                    self._send_json(200, service.apply(partial))
                    return
                if path == "/api/preset":
                    self._send_json(200, service.apply_preset(str(body.get("id", ""))))
                    return
                if path == "/api/reconnect":
                    self._send_json(200, service.refresh_monitor(apply_saved=False))
                    return
                if path == "/api/window":
                    action = body.get("action")
                    if action == "minimize":
                        service.minimize()
                    elif action == "close":
                        service.close_window()
                    else:
                        self._send_json(400, {"error": "Unknown window action"})
                        return
                    self._send_json(200, {"ok": True})
                    return
            except KeyError:
                self._send_json(404, {"error": "Unknown preset"})
                return
            except (ValueError, json.JSONDecodeError):
                self._send_json(400, {"error": "That value isn't a whole number."})
                return
            self._send_json(404, {"error": "Not found"})

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 100_000:
                raise ValueError("too large")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("object required")
            return data

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            listener = service.subscribe()
            try:
                while True:
                    try:
                        payload = listener.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": keep\n\n")
                    else:
                        self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
                pass
            finally:
                service.unsubscribe(listener)

        def _file(self, path: str):
            if root is None or not root.exists():
                message = "NightOwl is running, and the window build is missing."
                data = message.encode("utf-8")
                self.send_response(503)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            rel = path.lstrip("/") or "index.html"
            candidate = (root / rel).resolve()
            if not str(candidate).startswith(str(root)) or not candidate.is_file():
                candidate = root / "index.html"
            mime = EXTRA_TYPES.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0]
            payload = candidate.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-cache" if candidate.name == "index.html" else "public, max-age=3600")
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: int, payload: dict):
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(service, dist: Path | None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((HOST, PORT), make_handler(service, dist))
    server.daemon_threads = True
    return server
