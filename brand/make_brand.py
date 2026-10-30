"""Builds the installer artwork from Mickey Perry's two marks (sources in src/):
  pafu_logo.png  Pafu Igniters diamond (white on transparent; the transparent part is black)
  mp_fav.png     Mickey Perry motion design / animation cube logo (pink to purple)

Output (committed, so the repo builds without running this):
  wizard.png / wizard_small.png   welcome + finish side panel (410x785 / 164x314)
  corner.png / corner_small.png   top-right corner of the other pages (138x140 / 55x55)
  app.ico                      setup + uninstaller icon
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PAFU = os.path.join(HERE, "src", "pafu_logo.png")
MP = os.path.join(HERE, "src", "mp_fav.png")
AILERONS = os.path.join(os.environ["LOCALAPPDATA"], r"Microsoft\Windows\Fonts\Ailerons.ttf")
# mickeyperry.github.io: Space Grotesk for the name (OFL, from Google Fonts; put SpaceGrotesk.ttf in src/)
GROTESK = os.path.join(HERE, "src", "SpaceGrotesk.ttf")
BLACK = (11, 11, 15)          # = WizardBackColor in FLStripClub.iss
PINK, PURPLE = (255, 45, 135), (180, 107, 255)   # mickeyperry.github.io accents
DIM = (200, 200, 214)


def pafu(size):
    im = Image.open(PAFU).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def mp(size):
    im = Image.open(MP).convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def tracked_width(draw, text, font, spacing):
    return sum(draw.textlength(c, font=font) for c in text) + spacing * (len(text) - 1)


def tracked(draw, cx, y, text, font, fill, spacing):
    """Text centred on cx with wide letter spacing (Ailerons wants air)."""
    x = cx - tracked_width(draw, text, font, spacing) / 2
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + spacing


def grain(img, strength=5, seed=7):
    """Film grain that averages to zero, so the black still matches the wizard background."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    noise = np.random.default_rng(seed).integers(-strength, strength + 1, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a + noise, 0, 255).astype(np.uint8))


def glow(size, center, radius, color):
    g = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    cx, cy = center
    d.ellipse((cx - radius, cy - radius * 0.55, cx + radius, cy + radius * 0.55), fill=color + (120,))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.45))


def gradient_line(img, x0, x1, y, h=2):
    d = ImageDraw.Draw(img)
    for x in range(x0, x1):
        t = (x - x0) / max(1, x1 - x0 - 1)
        c = tuple(int(PINK[i] + (PURPLE[i] - PINK[i]) * t) for i in range(3))
        d.line((x, y, x, y + h - 1), fill=c)


def font(path, size, weight=None):
    f = ImageFont.truetype(path, size)
    if weight:
        f.set_variation_by_name(weight)
    return f


def block(img, top, bottom, logo, title, title_font, title_spacing):
    """One brand block (logo + name), centred horizontally and in [top, bottom]."""
    W = img.width
    d = ImageDraw.Draw(img)
    gap, title_h = 28, 40
    y = top + (bottom - top - (logo.height + gap + title_h)) // 2
    img.alpha_composite(logo, ((W - logo.width) // 2, y))
    tracked(d, W / 2, y + logo.height + gap, title, title_font, (255, 255, 255), title_spacing)


def side_panel():
    W, H = 410, 785
    MID = 392
    img = Image.new("RGBA", (W, H), BLACK + (255,))
    img.alpha_composite(glow((W, H), (W // 2, 760), 320, (70, 30, 150)))   # dusk glow at the bottom

    # sizes balanced by eye: the diamond's left half is black-on-black and its shards are thin,
    # so it needs more size than the solid MP cube to weigh the same
    block(img, 20, MID, pafu(176), "PAFU IGNITERS", ImageFont.truetype(AILERONS, 36), 5)
    gradient_line(img, W // 2 - 60, W // 2 + 60, MID)
    mp_logo = Image.open(MP).convert("RGBA")
    mp_logo = mp_logo.resize((int(mp_logo.width * 132 / mp_logo.height), 132), Image.LANCZOS)
    block(img, MID, H - 30, mp_logo, "MICKEY PERRY", font(GROTESK, 32, b"Bold"), 1)

    out = grain(img)
    out.save(os.path.join(HERE, "wizard.png"))
    out.resize((164, 314), Image.LANCZOS).save(os.path.join(HERE, "wizard_small.png"))


def corner():
    for (w, h), name in (((138, 140), "corner.png"), ((55, 55), "corner_small.png")):
        img = Image.new("RGBA", (w, h), BLACK + (255,))
        logo = pafu(int(min(w, h) * 0.72))
        # Setup pins this image to the window's right edge: shift the logo left, off the border
        img.alpha_composite(logo, ((w - logo.width) // 2 - w // 8, (h - logo.height) // 2))
        img.convert("RGB").save(os.path.join(HERE, name))


def icon():
    """Waveform bars in the pink to purple gradient with a silent gap cut out, on a black tile."""
    S = 1024   # drawn big, scaled down for each size
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, S - 1, S - 1), radius=200, fill=BLACK + (255,))
    bars = [0.30, 0.62, 0.45, 0.80, 0.38, None, None, 0.55, 0.90, 0.60, 0.34]
    n, margin = len(bars), 150
    step = (S - 2 * margin) / n
    bw = step * 0.56
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    for k, h in enumerate(bars):
        x = margin + k * step + (step - bw) / 2
        if h is None:
            continue
        hh = h * (S - 2 * margin) / 2
        d.rounded_rectangle((x, S / 2 - hh, x + bw, S / 2 + hh), radius=bw / 2, fill=255)
    # the cut: a thin line where the silence was
    gx0, gx1 = margin + 5 * step + step * 0.2, margin + 7 * step - step * 0.2
    line = Image.new("L", (S, S), 0)
    ImageDraw.Draw(line).rounded_rectangle((gx0, S / 2 - 9, gx1, S / 2 + 9), radius=9, fill=255)
    grad = Image.new("RGBA", (S, S))
    gp = grad.load()
    for x in range(S):
        t = x / (S - 1)
        c = tuple(int(PINK[i] + (PURPLE[i] - PINK[i]) * t) for i in range(3))
        for y in range(S):
            gp[x, y] = c + (255,)
    tile.paste(grad, (0, 0), mask)
    tile.paste(Image.new("RGBA", (S, S), (70, 70, 88, 255)), (0, 0), line)
    out = tile.resize((256, 256), Image.LANCZOS)
    out.save(os.path.join(HERE, "icon.png"))
    out.save(os.path.join(HERE, "app.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    tile.resize((512, 512), Image.LANCZOS).save(os.path.join(HERE, "icon_512.png"))   # macOS / README


if __name__ == "__main__":
    side_panel()
    corner()
    icon()
    print("brand art written to", HERE)
