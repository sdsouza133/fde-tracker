"""Serve the tracker page and run the daily outreach job, for hosting on Railway.

Run: python server.py [--host 0.0.0.0]   (PORT defaults to 8080; host defaults to 127.0.0.1,
Railway's start command passes 0.0.0.0)

- The site is public unless TRACKER_PASSWORD is set; then every page needs HTTP Basic auth with that
  password (any username). /healthz is always open so the platform can probe it.
- With TRACKER_DATA_DIR (the Railway volume) and APOLLO_API_KEY set, a background thread runs
  scripts/daily.py every morning at DAILY_HOUR (default 7) Toronto time, and once at startup if
  today's list is missing. Day files are served from the volume at /data/.
"""
import argparse
import base64
import datetime as dt
import hmac
import os
import posixpath
import subprocess
import sys
import threading
import time
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DATA_DIR = os.environ.get("TRACKER_DATA_DIR")
MIN_PASSWORD = 12
TZ = ZoneInfo("America/Toronto")
MAX_TRIES_PER_DAY = 3


class Handler(SimpleHTTPRequestHandler):
    password = b""  # empty: public site

    def end_headers(self):
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")  # contact data: never cache it in shared caches
        super().end_headers()

    def translate_path(self, path):
        """With a data dir, /data/... comes from the volume instead of docs/data."""
        if DATA_DIR:
            p = urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0])
            if p.startswith("/data/"):
                rel = posixpath.normpath(p[len("/data/"):])
                if rel == "." or rel.startswith("..") or rel.startswith("/"):
                    return str(DOCS / ".no-such-file")  # outside the volume or a folder: 404
                return os.path.join(DATA_DIR, "data", *rel.split("/"))
        return super().translate_path(path)

    def authorized(self):
        if not self.password:
            return True
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


def daily_loop(hour, mock):
    """Run the daily job once per Toronto day after `hour`, retrying a failed run up to MAX_TRIES_PER_DAY."""
    tries = {}
    while True:
        now = dt.datetime.now(TZ)
        day = now.date().isoformat()
        done = (Path(DATA_DIR) / "data" / "days" / f"{day}.json").exists()
        attempts = tries.setdefault(day, [])
        due = now.hour >= hour and not done and len(attempts) < MAX_TRIES_PER_DAY
        if due and (not attempts or time.time() - attempts[-1] >= 3600):  # an hour between retries
            attempts.append(time.time())
            print(f"daily run for {day} (try {len(attempts)})", flush=True)
            cmd = [sys.executable, str(ROOT / "scripts" / "daily.py"), "--date", day] + (["--mock"] if mock else [])
            code = subprocess.run(cmd).returncode
            print(f"daily run for {day} exited {code}", flush=True)
        time.sleep(60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="interface to listen on; 0.0.0.0 only where the platform needs it")
    host = ap.parse_args().host
    password = os.environ.get("TRACKER_PASSWORD", "")
    if password and len(password) < MIN_PASSWORD:
        sys.exit(f"TRACKER_PASSWORD must be at least {MIN_PASSWORD} characters, or unset for a public site")
    Handler.password = password.encode()

    mock = os.environ.get("TRACKER_MOCK") == "1"
    if not DATA_DIR:
        print("TRACKER_DATA_DIR not set: serving docs/data, daily job off", flush=True)
    elif not (os.environ.get("APOLLO_API_KEY") or mock):
        print("APOLLO_API_KEY not set: daily job off until it is", flush=True)
    else:
        hour = int(os.environ.get("DAILY_HOUR", "7"))
        threading.Thread(target=daily_loop, args=(hour, mock), daemon=True).start()
        print(f"daily job on: {hour:02d}:00 America/Toronto, data in {DATA_DIR}", flush=True)

    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer((host, port), partial(Handler, directory=str(DOCS)))
    print(f"serving on {host}:{port} ({'password required' if password else 'public, no password'})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
