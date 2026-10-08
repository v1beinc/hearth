"""Serve only the music UI on loopback, so the YouTube embed has a referrer."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent


class MusicHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        files = {"/": ("music.html", "text/html"),
                 "/music.js": ("music.js", "text/javascript")}
        if route not in files:
            self.send_error(404)
            return
        name, content_type = files[route]
        content = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


class MusicPage:
    def __init__(self):
        self.server = None
        self.thread = None

    def open(self) -> str:
        if self.server is None:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), MusicHandler)
            self.thread = Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        url = f"http://127.0.0.1:{self.server.server_port}/"
        if webbrowser.open(url, new=2) is False:
            raise OSError("No browser could open the music page")
        return url

    def close(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=1)
            self.server = self.thread = None
