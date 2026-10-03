"""Local HTTP API and static host for the React UI.

Same shape as EyesRhythm: the page talks only to 127.0.0.1. This uses the
standard library so ScreenQuery does not need a second web framework.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from screenquery.login_item import is_enabled as login_enabled
from screenquery.login_item import launch_at_login_supported, set_enabled as set_login
from screenquery.openai_api import endpoint
from screenquery.permissions_text import MAC_SETTINGS_URLS, permission_help
from screenquery.status import Status


def ui_dist() -> Path:
    import sys as _sys

    if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
        return Path(_sys._MEIPASS) / "frontend" / "dist"
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


class UiServer:
    def __init__(self, app, host: str = "127.0.0.1", port: int = 8756) -> None:
        self.app = app
        self.host = host
        self.port = port
        self._status = Status()
        self._generation = 0
        self._visible = False
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self.on_hide = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        handler = _handler_factory(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        thread = threading.Thread(target=self._httpd.serve_forever, name="screenquery-ui", daemon=True)
        thread.start()

    def stop(self) -> None:
        server = self._httpd
        self._httpd = None
        if server is not None:
            server.shutdown()

    def publish(self, status: Status) -> int:
        with self._lock:
            self._generation += 1
            self._status = status
            self._visible = True
            return self._generation

    def hide_status(self, generation: int | None = None) -> bool:
        with self._lock:
            if generation is not None and int(generation) != self._generation:
                return False
            self._visible = False
        callback = self.on_hide
        if callback is not None:
            try:
                callback()
            except Exception:
                pass
        return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "generation": self._generation,
                "visible": self._visible,
                "status": self._status.to_dict(),
            }

    def settings_payload(self) -> dict:
        settings = self.app.settings_store.load()
        stored = ""
        key_status = "No API key stored."
        try:
            stored = self.app.keystore.load() or ""
            if stored:
                key_status = "A key is stored in the system keychain."
        except Exception as exc:  # noqa: BLE001
            key_status = str(exc)
        try:
            login = bool(login_enabled()) if launch_at_login_supported() else False
        except Exception:
            login = False
        payload = settings.to_dict()
        payload.update(
            {
                "key_stored": bool(stored),
                "key_status": key_status,
                "login_supported": launch_at_login_supported(),
                "launch_at_login": login,
                "permission_help": permission_help(sys.platform),
                "platform": sys.platform,
            }
        )
        return payload

    def update_settings(self, raw: dict) -> dict:
        current = self.app.settings_store.load()
        folder = raw.get("custom_folder", current.custom_folder)
        if folder is not None and not isinstance(folder, str):
            folder = current.custom_folder
        if isinstance(folder, str) and not folder.strip():
            folder = None
        base_url = raw.get("base_url", current.base_url)
        if isinstance(base_url, str) and base_url.strip():
            endpoint(base_url)
        else:
            base_url = current.base_url
        model = raw.get("model", current.model)
        if not isinstance(model, str) or not model.strip():
            model = current.model
        from screenquery.settings_store import Settings

        settings = Settings(
            save_enabled=bool(raw.get("save_enabled", current.save_enabled)),
            llm_enabled=bool(raw.get("llm_enabled", current.llm_enabled)),
            custom_folder=folder,
            base_url=str(base_url).strip(),
            model=str(model).strip(),
            clipboard_enabled=bool(raw.get("clipboard_enabled", current.clipboard_enabled)),
        )
        self.app.settings_store.save(settings)
        return self.settings_payload()

    def save_key(self, secret: str) -> dict:
        secret = (secret or "").strip()
        if not secret:
            raise ValueError("Paste a key first.")
        self.app.keystore.save(secret)
        current = self.app.settings_store.load()
        if not current.llm_enabled:
            payload = current.to_dict()
            payload["llm_enabled"] = True
            self.update_settings(payload)
        return self.settings_payload()

    def remove_key(self) -> dict:
        self.app.keystore.delete()
        return self.settings_payload()

    def set_login(self, enabled: bool) -> dict:
        set_login(bool(enabled))
        return self.settings_payload()

    def open_permission(self, kind: str) -> None:
        import subprocess

        urls = MAC_SETTINGS_URLS.get(kind) or ()
        for url in urls:
            result = subprocess.run(["open", url], check=False)
            if result.returncode == 0:
                return
        # Do not call CGRequestScreenCaptureAccess or CGRequestListenEventAccess
        # here. Those pop the system dialog on every click. The buttons only
        # open the Privacy panes; the user turns ScreenQuery on there.

    def choose_folder(self) -> str | None:
        import subprocess

        if sys.platform == "darwin":
            script = 'POSIX path of (choose folder with prompt "Choose screenshot folder")'
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return None
            chosen = result.stdout.strip()
            return chosen or None
        if sys.platform == "win32":
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "if ($d.ShowDialog() -eq 'OK') { $d.SelectedPath }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                check=False,
            )
            chosen = result.stdout.strip()
            return chosen or None
        return None


def _handler_factory(server: UiServer):
    dist = ui_dist()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(min(length, 1_000_000))
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/health":
                self._json(200, {"ok": True, "name": "ScreenQuery"})
                return
            if path == "/api/settings":
                self._json(200, server.settings_payload())
                return
            if path == "/api/status":
                self._json(200, server.snapshot())
                return
            self._file(path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                body = self._read_json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "Expected JSON."})
                return
            try:
                if path == "/api/settings":
                    self._json(200, server.update_settings(body))
                    return
                if path == "/api/key":
                    self._json(200, server.save_key(str(body.get("key") or "")))
                    return
                if path == "/api/login":
                    self._json(200, server.set_login(bool(body.get("enabled"))))
                    return
                if path == "/api/permissions":
                    server.open_permission(str(body.get("kind") or ""))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/folder":
                    chosen = server.choose_folder()
                    if chosen:
                        current = server.app.settings_store.load().to_dict()
                        current["custom_folder"] = chosen
                        self._json(200, server.update_settings(current))
                    else:
                        self._json(200, server.settings_payload())
                    return
                if path == "/api/folder/default":
                    current = server.app.settings_store.load().to_dict()
                    current["custom_folder"] = ""
                    self._json(200, server.update_settings(current))
                    return
                if path == "/api/capture":
                    server.app.capture()
                    self._json(200, {"ok": True})
                    return
                if path == "/api/quit":
                    server.app.quit()
                    self._json(200, {"ok": True})
                    return
                if path == "/api/status/hide":
                    raw_generation = body.get("generation")
                    generation = int(raw_generation) if raw_generation is not None else None
                    hidden = server.hide_status(generation)
                    self._json(200, {"ok": True, "hidden": hidden})
                    return
                if path == "/api/reveal":
                    _reveal(str(body.get("path") or ""))
                    self._json(200, {"ok": True})
                    return
            except Exception as exc:  # noqa: BLE001
                self._json(400, {"error": str(exc)})
                return
            self._json(404, {"error": "Not found."})

        def do_DELETE(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/key":
                try:
                    self._json(200, server.remove_key())
                except Exception as exc:  # noqa: BLE001
                    self._json(400, {"error": str(exc)})
                return
            self._json(404, {"error": "Not found."})

        def _file(self, path: str) -> None:
            if path in ("/", "/index.html"):
                target = dist / "index.html"
            elif path in ("/overlay", "/overlay.html"):
                target = dist / "overlay.html"
            else:
                relative = path.lstrip("/")
                target = (dist / relative).resolve()
                if dist.resolve() not in target.parents and target != dist.resolve():
                    self._json(404, {"error": "Not found."})
                    return
            if not target.is_file():
                if path in ("/", "/index.html", "/overlay", "/overlay.html"):
                    self._json(404, {"error": "UI build is missing. Run npm run build in frontend/."})
                else:
                    self._json(404, {"error": "Not found."})
                return
            content_type = _content_type(target.suffix)
            self._send(200, target.read_bytes(), content_type)

    return Handler


def _content_type(suffix: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".ttf": "font/ttf",
        ".json": "application/json",
        ".png": "image/png",
    }.get(suffix, "application/octet-stream")


def _reveal(path: str) -> None:
    import subprocess

    if not path:
        return
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", path], check=False)
    elif sys.platform == "win32":
        subprocess.run(["explorer", "/select,", path], check=False)
    else:
        subprocess.run(["xdg-open", str(Path(path).parent)], check=False)
