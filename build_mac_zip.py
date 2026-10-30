"""Packs the macOS download: dist/StripSilence-mac-<version>.zip (source + launcher; needs Python 3 on the Mac).
Untested on a real Mac: the window is pywebview's WebKit backend, everything else is plain Python."""
import os
import zipfile

VERSION = "1.0.0"
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["app.py", "server.py", "strip_silence.py", "index.html", "requirements.txt", "README.md", "LICENSE",
         "brand/icon.png", "brand/SpaceGrotesk.ttf"]
os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
out = os.path.join(HERE, "dist", "StripSilence-mac-%s.zip" % VERSION)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        z.write(os.path.join(HERE, f), "Strip Silence/" + f)
    info = zipfile.ZipInfo("Strip Silence/Strip Silence.command")
    info.external_attr = (0o100755 << 16)   # executable, so a double-click runs it
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, open(os.path.join(HERE, "mac", "Strip Silence.command"), "rb").read().replace(b"\r\n", b"\n"))
print(out)
