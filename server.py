"""FL Strip Club preview: http://127.0.0.1:8912

Shows every audio clip of a saved FL project with the cuts that strip_silence would
make, live as you turn the dials, and writes exactly what you see on Apply.

Started by app.py (or the packaged FLStripClub.exe), which opens the page in an app window.
"""
import base64
import subprocess
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

import strip_silence as ss

PORT = 8912
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))   # bundled files
WINDOW = None   # the app window, set by app.py


def data_dir():
    """Per-user settings folder (the install folder may not be writable)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "FL Strip Club")
    os.makedirs(d, exist_ok=True)
    return d


STATE = os.path.join(data_dir(), "state.json")   # last project path
PEAKS = {}   # sample path -> (mtime, payload)
LOCK = threading.Lock()


def remember(path):
    try:
        json.dump({"last": path}, open(STATE, "w"))
    except OSError:
        pass


def last_path():
    try:
        return json.load(open(STATE)).get("last", "")
    except (OSError, ValueError):
        return ""


def sample_payload(path):
    """Peak level per analysis window as 0.5 dB steps above -96 dBFS (0 = silence), base64 bytes."""
    mt = os.path.getmtime(path)
    with LOCK:
        hit = PEAKS.get(path)
        if hit and hit[0] == mt:
            return hit[1]
    peaks, win, total = ss.load_peaks(path, ss.WIN)
    with np.errstate(divide="ignore"):
        db = 20 * np.log10(np.maximum(peaks, 1e-9))
    q = np.clip(np.round((db + 96) * 2), 0, 192).astype(np.uint8)
    payload = {"win": win, "total": total, "q": base64.b64encode(q.tobytes()).decode()}
    with LOCK:
        PEAKS[path] = (mt, payload)
    return payload


def load(path):
    proj = ss.Project(path)
    clips = proj.audio_clips()
    samples = {}
    for c in clips:
        if c["sample"] not in samples:
            samples[c["sample"]] = sample_payload(c["sample"])
    song = max((c["pos"] + c["len"] for c in clips), default=proj.ppq * 4)
    remember(path)
    guess = {}
    for c in clips:
        guess.setdefault(c["track"], ss.guess_category(c["name"]))
        c["short"] = ss.short_name(c["name"])
    return {"path": path, "tempo": proj.tempo, "ppq": proj.ppq, "msPerTick": proj.ms_per_tick,
            "songTicks": song, "records": len(proj.recs), "clips": clips, "samples": samples,
            "categories": [[n, col] for n, col, _ in ss.CATEGORIES], "guess": guess,
            "out": os.path.splitext(path)[0] + "_stripped.flp",
            "skipped": sorted(proj.skipped.items())}


def apply(body):
    proj = ss.Project(body["path"])
    known = {c["i"]: c for c in proj.audio_clips()}
    plans = {}
    for k, pieces in body["plans"].items():
        c = known.get(int(k))
        if not c:
            raise ValueError("clip %s is not an audio clip of this project" % k)
        lo, hi = c["pos"], c["pos"] + c["len"]
        for t0, t1 in pieces:
            if not lo <= t0 < t1 <= hi:
                raise ValueError("piece outside its clip")
        plans[int(k)] = [(int(a), int(b)) for a, b in pieces]
    out = body.get("out") or os.path.splitext(body["path"])[0] + "_stripped.flp"
    if not out.lower().endswith(".flp"):
        out += ".flp"
    groups = {int(t): g for t, g in (body.get("groups") or {}).items()}
    remove = {int(t) for t in body.get("remove") or []}
    for t in remove:
        if not any(plans.get(c["i"]) for c in known.values() if c["track"] == t):
            continue
        raise ValueError("track %d still has sound; not removing it" % (t + 1))
    if remove and not groups:   # every audio track takes part, so the removed ones leave no gaps
        groups = {c["track"]: None for c in known.values()}
    if os.path.exists(out):   # previous Apply result: keep it as the undo
        bak = out + ".bak"
        if os.path.exists(bak):
            os.remove(bak)
        os.replace(out, bak)
    n0, n1 = proj.write(plans, out, groups or None, remove=remove)
    return {"ok": True, "out": out, "before": n0, "after": n1}


def open_in_fl(path):
    """Hand the project to FL Studio, the program .flp files open with."""
    if not os.path.isfile(path):
        raise ValueError("file not found: %s" % path)
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
    return {"ok": True}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":
                return self._send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path.startswith("/brand/"):   # icon + font for the page
                f = os.path.join(HERE, "brand", os.path.basename(u.path))
                if os.path.isfile(f):
                    ext = os.path.splitext(f)[1].lower()
                    return self._send(200, open(f, "rb").read(), {".png": "image/png", ".ttf": "font/ttf"}.get(ext, "application/octet-stream"))
            if u.path == "/api/ping":
                return self._send(200, {"app": "fl-strip-club"})
            if u.path == "/api/last":
                return self._send(200, {"path": last_path()})
            if u.path == "/api/load":
                return self._send(200, load(q["path"][0].strip().strip('"')))
        except Exception as e:
            traceback.print_exc()
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/apply":
                return self._send(200, apply(body))
            if self.path == "/api/open":
                return self._send(200, open_in_fl(body["path"]))
            if self.path == "/api/show" and WINDOW:   # a second launch handed us a project
                WINDOW.restore()
                WINDOW.show()
                if body.get("path"):
                    WINDOW.evaluate_js("load(%s)" % json.dumps(body["path"]))
                return self._send(200, {"ok": True})
        except Exception as e:
            traceback.print_exc()
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})


if __name__ == "__main__":   # plain server, no window (app.py is the normal way in)
    if len(sys.argv) > 1:
        remember(os.path.abspath(sys.argv[1]))
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
