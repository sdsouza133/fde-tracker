"""Serve docs/ (the tracker page and its data) behind HTTP Basic auth, for hosting on Railway.

Run: TRACKER_PASSWORD=... python server.py   (PORT defaults to 8080)
Any username works; only the password is checked. /healthz is open so the platform can probe it.
"""
import base64
import hmac
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DOCS = Path(__file__).resolve().parent / "docs"
MIN_PASSWORD = 12


class Handler(SimpleHTTPRequestHandler):
    password = b""

    def end_headers(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")  # contact data: never cache it in shared caches
        super().end_headers()

    def authorized(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            _, _, given = base64.b64decode(header[6:]).partition(b":")
        except ValueError:
            return False
        return hmac.compare_digest(given, self.password)

    def deny(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="FDE tracker", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.authorized():
            return self.deny()
        path = self.path.split("?", 1)[0]
        if path.endswith("/") and path != "/":
            self.send_error(404)  # no directory listings
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.authorized():
            return self.deny()
        super().do_HEAD()

    def list_directory(self, path):
        self.send_error(404)


def main():
    password = os.environ.get("TRACKER_PASSWORD", "")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"TRACKER_PASSWORD must be set to at least {MIN_PASSWORD} characters; refusing to serve contact data without it")
    Handler.password = password.encode()
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler, directory=str(DOCS)))
    print(f"serving {DOCS} on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
