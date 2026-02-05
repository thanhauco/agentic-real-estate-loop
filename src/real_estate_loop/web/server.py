"""A zero-dependency HTTP server exposing the API and the static SPA.

Run it with:
    python serve.py                      (repo-root launcher)
    python -m real_estate_loop.web       (when installed or PYTHONPATH=src)
    realestate-web                       (console script after `pip install -e .`)
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .api import ApiRouter

_STATIC_DIR = Path(__file__).resolve().parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class _Handler(BaseHTTPRequestHandler):
    router: ApiRouter  # set on the class before the server starts
    static_dir: Path = _STATIC_DIR

    # -- response helpers --------------------------------------------------- #
    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _content_type(path))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- verbs -------------------------------------------------------------- #
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            result = self.router.dispatch("GET", path, {})
            self._send_json(result.status, result.payload)
            return
        if path in ("/", "/index.html"):
            self._send_file(self.static_dir / "index.html")
            return
        # Other static files (guarded against path traversal).
        candidate = (self.static_dir / path.lstrip("/")).resolve()
        if candidate.is_file() and self.static_dir in candidate.parents:
            self._send_file(candidate)
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        result = self.router.dispatch("POST", path, body)
        self._send_json(result.status, result.payload)

    def log_message(self, *args) -> None:  # keep the console quiet
        return


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="real_estate_loop.web", description="Real Estate AI web UI + JSON API"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--state", default=".realestate_state.json", help="learned-state file path"
    )
    parser.add_argument("--no-persist", action="store_true", help="do not load/save state")
    args = parser.parse_args(argv)

    state_path = None if args.no_persist else args.state
    _Handler.router = ApiRouter(state_path=state_path)

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"Real Estate AI web UI running at {url}  (Ctrl+C to stop)")
    if state_path:
        print(f"Persisting learned state to {state_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
        if state_path:
            _Handler.router.orch.save_state(state_path)
    return 0
