"""FL Strip Club: the desktop app.

    pythonw app.py [Project.flp]

A native window (WebView2 on Windows, WebKit on macOS) showing the preview page, served
by server.py on a private local port. No console, no browser. Dropping a .flp on the
window or using Open loads it. Starting it again with a project hands the project to the
window that is already open.
"""
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import quote
from urllib.request import Request, urlopen

import webview

import server

TITLE = "FL Strip Club"


class Api:
    """Functions the page can call as window.pywebview.api.*"""

    def pick(self, start=""):
        res = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN, directory=os.path.dirname(start) if start else "",
            file_types=("FL Studio project (*.flp)", "All files (*.*)"))
        return os.path.normpath(res[0]) if res else ""

    def link(self, url):
        """Open a web link in the user's own browser, not inside the app."""
        import webbrowser
        if url.startswith("https://"):
            webbrowser.open(url)


def hand_over(path):
    """True if an open FL Strip Club took the project (then this copy just quits)."""
    try:
        with urlopen("http://127.0.0.1:%d/api/ping" % server.PORT, timeout=1) as r:
            if json.load(r).get("app") != "fl-strip-club":
                return False
        req = Request("http://127.0.0.1:%d/api/show" % server.PORT, data=json.dumps({"path": path}).encode())
        urlopen(req, timeout=2).close()
        return True
    except Exception:
        return False


def on_drop(e):
    files = (e.get("dataTransfer") or {}).get("files") or []
    for f in files:
        p = f.get("pywebviewFullPath") or ""
        if p.lower().endswith(".flp"):
            webview.windows[0].evaluate_js("load(%s)" % json.dumps(p))
            return


def on_loaded():
    w = webview.windows[0]
    w.dom.document.events.dragover += webview.dom.DOMEventHandler(lambda e: None, True, True)
    w.dom.document.events.drop += webview.dom.DOMEventHandler(on_drop, True, True)


def main():
    path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if hand_over(path):
        return
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", server.PORT), server.Handler)
    except OSError:   # port taken by something else: any free port will do
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if path:
        server.remember(path)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1] + ("?path=" + quote(path) if path else "")
    win = webview.create_window(TITLE, url, js_api=Api(), width=1500, height=900, min_size=(900, 560),
                                background_color="#0B0B0F")
    server.WINDOW = win
    win.events.loaded += on_loaded
    icon = os.path.join(server.HERE, "brand", "app.ico" if os.name == "nt" else "icon.png")
    webview.start(icon=icon if os.path.exists(icon) else None,
                  storage_path=os.path.join(server.data_dir(), "webview"), private_mode=False)
    httpd.shutdown()


if __name__ == "__main__":
    main()
