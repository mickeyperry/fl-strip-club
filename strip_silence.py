"""Strip silence from FL Studio playlist audio clips, keeping every sound where it is.

Each audio clip in the playlist is cut into separate clips wherever its audio is
silent for a while. Every piece keeps its exact place on the timeline (its start
inside the audio file is set to match), and the silent stretches are left empty.

    python strip_silence.py Project.flp [--db -50] [--gap 0.3] [--pad 0.01] [--snap BEATS] [--rough]

Writes Project_stripped.flp next to the original and never changes the original.

How FL stores a playlist clip (event 233, one record per clip; 32 bytes in older
projects, 60/88 in newer ones): position (ticks) u32, base u16 (20480 = channel
clip), channel u16, length (ticks) u32, track (499 - index) u16, group u16,
flags, then start/end offset floats at bytes 24/28: for audio clips these are
milliseconds into the sample (-1 = from the start / to the end). Bytes 32-35 of
the bigger records are a per-clip id; new pieces get fresh ids.
Only unstretched clips are handled (sample plays at 1 ms per ms); stretched or pitched
channels (event 215) are skipped and left as they are.
"""
import argparse
import os
import re
import struct
import sys

import numpy as np

CLIP_BASE = 20480
WIN = 0.005   # analysis window, seconds


# ------------------------------------------------------------------ FLP events
def read_events(buf):
    if buf[:4] != b"FLhd":
        raise SystemExit("not an FL Studio project")
    hl = struct.unpack("<I", buf[4:8])[0]
    ppq = struct.unpack("<H", buf[12:14])[0]
    p = 8 + hl
    if buf[p:p + 4] != b"FLdt":
        raise SystemExit("bad project file (no FLdt)")
    data_start = p
    p += 8
    out = []
    while p < len(buf):
        start = p
        i = buf[p]
        p += 1
        if i < 64:
            n = 1
        elif i < 128:
            n = 2
        elif i < 192:
            n = 4
        else:
            n = s = 0
            while True:
                b = buf[p]
                p += 1
                n |= (b & 0x7F) << s
                s += 7
                if not b & 0x80:
                    break
        out.append([i, bytes(buf[p:p + n]), start, p + n])
        p += n
    return buf[:data_start], ppq, out


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def splice_event(buf, data_start, ev_start, ev_end, event_id, data):
    """Replace one event's bytes in place and fix the FLdt length; everything else stays byte-identical.
    (FL 2026 headers have an event this parser does not size right, so we never re-encode the file.)"""
    new = bytes([event_id]) + varint(len(data)) + data
    out = bytearray(buf[:ev_start]) + new + buf[ev_end:]
    struct.pack_into("<I", out, data_start + 4, len(out) - data_start - 8)
    return bytes(out)


# ------------------------------------------------------------------ project info
def project_info(events):
    chans, ch, tempo = {}, None, None
    for i, d, *_ in events:
        if i == 64:
            ch = struct.unpack("<H", d)[0]
            chans[ch] = {}
        elif ch is not None and i == 21:
            chans[ch]["type"] = d[0]
        elif ch is not None and i == 196:
            path = d.decode("utf-16-le", "replace").rstrip("\0")
            chans[ch]["sample"] = os.path.expandvars(path)
        elif ch is not None and i == 203:
            chans[ch]["name"] = d.decode("utf-16-le", "replace").rstrip("\0")
    return chans, tempo


# ------------------------------------------------------------------ audio
def _wav_blocks(path, block):
    """(sample rate, frames, generator of float32 [n, ch] blocks) for PCM and float WAV files."""
    f = open(path, "rb")
    riff = f.read(12)
    if riff[:4] not in (b"RIFF", b"RF64") or riff[8:12] != b"WAVE":
        f.close()
        raise ValueError("not a WAV file (install the soundfile package for other formats): %s" % path)
    fmt = None
    while True:
        h = f.read(8)
        if len(h) < 8:
            f.close()
            raise ValueError("no audio data in %s" % path)
        cid, size = h[:4], struct.unpack("<I", h[4:])[0]
        if cid == b"fmt ":
            d = f.read(size + (size & 1))
            tag, nch, sr = struct.unpack("<HHI", d[:8])
            bits = struct.unpack("<H", d[14:16])[0]
            if tag == 0xFFFE and len(d) >= 26:   # WAVE_FORMAT_EXTENSIBLE: real format in the sub-GUID
                tag = struct.unpack("<H", d[24:26])[0]
            fmt = (tag, nch, sr, bits)
        elif cid == b"data":
            if not fmt:
                f.close()
                raise ValueError("bad WAV (data before fmt): %s" % path)
            tag, nch, sr, bits = fmt
            width = bits // 8
            if size in (0, 0xFFFFFFFF):   # RF64 / streamed: data runs to the end of the file
                size = os.path.getsize(path) - f.tell()
            frames = size // (width * nch)
            break
        else:
            f.seek(size + (size & 1), 1)
    if (tag, width) not in ((1, 1), (1, 2), (1, 3), (1, 4), (3, 4), (3, 8)):
        f.close()
        raise ValueError("unsupported WAV format (tag %d, %d bit): %s" % (tag, bits, path))

    def gen():
        left = frames
        with f:
            while left > 0:
                n = min(block, left)
                raw = f.read(n * width * nch)
                n = len(raw) // (width * nch)
                if not n:
                    return
                raw = raw[:n * width * nch]
                left -= n
                if tag == 3:
                    a = np.frombuffer(raw, "<f4" if width == 4 else "<f8").astype(np.float32)
                elif width == 1:
                    a = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
                elif width == 2:
                    a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
                elif width == 3:
                    b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
                    a = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) << 8 >> 8).astype(np.float32) / 8388608
                else:
                    a = (np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648).astype(np.float32)
                yield a.reshape(-1, nch)
    return sr, frames, gen()


def _audio_blocks(path, block):
    try:
        import soundfile as sf   # WAV, AIFF, FLAC, OGG, MP3 (libsndfile 1.1+)
        info = sf.info(path)
        return info.samplerate, info.frames, sf.blocks(path, blocksize=block, dtype="float32", always_2d=True)
    except ImportError:
        pass
    except Exception:
        if not path.lower().endswith(".wav"):
            raise
    return _wav_blocks(path, block)


def load_peaks(path, win_s):
    """Per-window peak level (linear 0..1), the window length and the file length in seconds.
    Reads the file in blocks, so multi-GB stems don't need that much memory."""
    sr, frames, blocks = _audio_blocks(path, 1 << 20)
    hop = max(1, int(sr * win_s))
    out, carry = [], np.zeros(0, np.float32)
    for a in blocks:
        a = np.concatenate([carry, np.abs(a).max(axis=1)])
        m = len(a) // hop
        if m:
            out.append(a[:m * hop].reshape(m, hop).max(axis=1))
        carry = a[m * hop:]
    peaks = np.concatenate(out) if out else np.zeros(0, np.float32)
    return peaks, hop / sr, frames / sr


def sound_regions(peaks, win, total, db, gap, pad, tail=None):
    """[(start_s, end_s)] where there is sound; silences shorter than `gap` are kept.
    pad = seconds kept before each sound, tail = seconds kept after it (default: same as pad)."""
    if tail is None:
        tail = pad
    loud = np.concatenate([[False], peaks > 10 ** (db / 20), [False]])
    edges = np.flatnonzero(np.diff(loud.astype(np.int8)))
    regions = [[s * win, e * win] for s, e in zip(edges[::2], edges[1::2])]
    merged = []
    for s, e in regions:
        if merged and s - merged[-1][1] < gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(max(0.0, s - pad), min(total, e + tail)) for s, e in merged]


# ------------------------------------------------------------------ groups
# order = playlist order; keywords are matched against the stem name (lower case)
CATEGORIES = [
    ("Drums", "#c8553d", ("drum", "808kick", "808snare", "kick", "snare", "amen", "hats", "chats", "ohats",
                          "darbuka", "crash", "perc", "break", "slices", "clap", "ride", "cymbal")),
    ("Bass", "#8e5cd1", ("bass", "reese", "growl", "sub ", "808")),
    ("Synths", "#3f88c5", ("wavetable", "lead", "arp", "piano", "flute", "pad", "synth", "saw", "keys", "pluck",
                           "chord", "glisten", "string", "organ", "bell")),
    ("Vocals", "#d36ba6", ("vocal", "vox", "voice", "choir", "acapella")),
    ("FX", "#2fa58c", ("impact", "imp ", "noise", "riser", "splash", "bowed", "drone", "deelay", "delay", "reverb",
                       "eq eight", "comet", "sweep", "fx", "metal", "downlifter", "uplifter")),
    ("Other", "#7d8790", ()),
    ("Mix", "#c9a33a", ()),
]
CAT_NAMES = [c[0] for c in CATEGORIES]
CAT_COLOR = {c[0]: c[1] for c in CATEGORIES}


def short_name(name):
    """'Song [2025-03-04 214948] 14-stemz__# Amen' -> 'Amen'"""
    n = re.sub(r"^.*?\]\s*", "", name) if "]" in name else name
    n = re.sub(r"^[0-9A-Z]{1,3}-(stemz__)?#?\s*", "", n)
    return n.strip() or name


def guess_category(name):
    if name.rstrip().endswith("]"):   # bare export name = the full mix
        return "Mix"
    low = " " + short_name(name).lower().replace("_", " ") + " "
    # vocals first ("Vocal Texture Pad" is a vocal), then the playlist order
    for cat, _, words in sorted(CATEGORIES, key=lambda c: c[0] != "Vocals"):
        if any(w in low for w in words):
            return cat
    return "Other"


def rgb_bytes(hexcol):
    """'#rrggbb' -> FL's color dword (R, G, B, 0)"""
    h = hexcol.lstrip("#")
    return bytes([int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 0])


def encode_event(i, d):
    return bytes([i]) + (varint(len(d)) if i >= 192 else b"") + d


# ------------------------------------------------------------------ project
class Project:
    """A saved .flp, its audio clips, and a writer that replaces only the clips block."""

    def __init__(self, path, bpm=None):
        self.path = path
        self.buf = buf = open(path, "rb").read()
        self.head, self.ppq, self.events = read_events(buf)
        self.chans, _ = project_info(self.events)
        # tempo = event 156 (bpm * 1000), in the project header right after the version strings
        tempos = [struct.unpack("<I", buf[k + 1:k + 5])[0] / 1000
                  for k in range(len(self.head), min(len(buf) - 5, len(self.head) + 512))
                  if buf[k] == 156 and 10_000 <= struct.unpack("<I", buf[k + 1:k + 5])[0] <= 999_000]
        self.tempo = bpm or (tempos[0] if tempos else None)
        if not self.tempo:
            raise ValueError("project tempo not found: pass --bpm")
        self.ms_per_tick = 60000 / self.tempo / self.ppq
        self.idx = next(k for k, e in enumerate(self.events) if e[0] == 233)
        blob = self.events[self.idx][1]
        if buf[self.events[self.idx][2]] != 233 or len(blob) % 4:
            raise ValueError("could not find the playlist clips block safely")
        self.size = next(s for s in (88, 60, 32) if len(blob) % s == 0)
        self.recs = [bytearray(blob[k:k + self.size]) for k in range(0, len(blob), self.size)]
        # channel -> its color event (128); playlist tracks = blocks [238 data, 43, 239 name?]
        # channel -> mixer insert it feeds (event 104)
        self.chan_color, self.chan_insert, ch = {}, {}, None
        for k, (i, d, a, b) in enumerate(self.events[:self.idx]):
            if i == 64:
                ch = struct.unpack("<H", d)[0]
            elif i == 128 and ch is not None and ch not in self.chan_color:
                self.chan_color[ch] = k
            elif i == 104 and ch is not None and len(d) == 2 and ch not in self.chan_insert:
                self.chan_insert[ch] = struct.unpack("<H", d)[0]
        self.tracks, k = [], self.idx + 1
        while k < len(self.events) and self.events[k][0] == 238:
            j = k + 1
            while j < len(self.events) and self.events[j][0] in (43, 239):
                j += 1
            self.tracks.append((k, j))
            k = j

    def audio_clips(self):
        """Playlist clips of audio channels whose file exists, with where their audio sits."""
        out, self.skipped = [], {}
        for i, r in enumerate(self.recs):
            pos, base, ch, ln, trk = struct.unpack("<IHHIH", r[:14])
            so, eo = struct.unpack("<ff", r[24:32])
            c = self.chans.get(ch, {})
            if base != CLIP_BASE or c.get("type") != 4:
                continue
            label = c.get("name") or os.path.basename(c.get("sample", "")) or "channel %d" % ch
            if not os.path.exists(c.get("sample", "")):
                self.skipped[label] = "audio file not found: %s" % c.get("sample", "")
                continue
            if c.get("stretched"):
                self.skipped[label] = "stretched or pitched in FL (not supported)"
                continue
            clip_s = max(0.0, so) / 1000                    # audio time (s) at the clip's left edge
            clip_e = clip_s + ln * self.ms_per_tick / 1000
            if eo >= 0:
                clip_e = min(clip_e, eo / 1000)
            out.append({"i": i, "pos": pos, "len": ln, "track": 499 - trk, "ch": ch, "clip_s": clip_s,
                        "clip_e": clip_e, "sample": c["sample"],
                        "name": c.get("name") or os.path.splitext(os.path.basename(c["sample"]))[0]})
        return out

    def plan(self, clip, peaks, win, total, db, gap, pad, snap, tail=None):
        """[(t0, t1)] timeline ticks of the pieces to keep. (The preview page mirrors this.)"""
        pos, ln, clip_s = clip["pos"], clip["len"], clip["clip_s"]
        clip_e = min(clip["clip_e"], total)
        grid = int(round(snap * self.ppq)) if snap else 0
        pieces = []
        for s, e in sound_regions(peaks, win, total, db, gap, pad, tail):
            s, e = max(s, clip_s), min(e, clip_e)
            if e <= s:
                continue
            t0 = pos + int((s - clip_s) * 1000 / self.ms_per_tick)
            t1 = pos + int(np.ceil((e - clip_s) * 1000 / self.ms_per_tick))
            if grid:   # widen the cut out to the song's beat grid
                t0, t1 = t0 // grid * grid, -(-t1 // grid) * grid
            t0, t1 = max(t0, pos), min(t1, pos + ln)
            if t1 <= t0:
                continue
            if pieces and t0 <= pieces[-1][1]:   # touching after padding/snapping: one piece
                pieces[-1][1] = max(pieces[-1][1], t1)
            else:
                pieces.append([t0, t1])
        return [tuple(p) for p in pieces]

    def _color_inserts(self, buf, insert_color):
        """Patch mixer insert colors into buf (all after the playlist, so applied back to front)."""
        start = self.tracks[-1][1] if self.tracks else self.idx + 1
        for off, old, new in sorted(_insert_color_patch(self.events, start, insert_color), reverse=True):
            buf[off:off + old] = new

    def write(self, plans, dst, groups=None, colors=None, remove=()):
        """plans: {record index: [(t0, t1), ...]}; records not in plans are kept as they are.
        Each piece's audio offset is computed from its exact tick, so it plays at the same moment.
        groups: {track index: category or None}: these tracks are re-ordered as whole track blocks
        (mute/height/etc. go along). Tracks with a category are sorted into category blocks,
        renamed "Category - stem", grouped with each other and they and their channels are
        painted the category color (colors: {category: '#rrggbb'} overrides). Tracks with None
        keep their relative order.
        remove: track indices to delete from the playlist (their clips go, their slot becomes a
        fresh default track and is moved after all the others, so no gaps are left)."""
        if os.path.abspath(dst) == os.path.abspath(self.path):
            raise ValueError("refusing to overwrite the original")
        remove = {int(t) for t in remove}
        groups = {int(k): (v if v in CAT_COLOR else None) for k, v in (groups or {}).items()}
        for t in remove:
            groups.setdefault(t, None)
        colors = dict(CAT_COLOR, **(colors or {}))
        if groups and not self.tracks:
            raise ValueError("playlist tracks not found in this project")
        slots = sorted(groups)
        order = sorted(slots, key=lambda t: (t in remove, CAT_NAMES.index(groups[t]) if groups[t] else -1, t))
        new_track = dict(zip(order, slots))   # old track index -> new track index
        ids = [struct.unpack("<I", r[32:36])[0] for r in self.recs] if self.size >= 36 else []
        next_id = max(ids, default=0) + 1
        out = []
        for i, r in enumerate(self.recs):
            trk = 499 - struct.unpack("<H", r[12:14])[0]
            if trk in remove:
                continue
            if trk in new_track:
                r = bytearray(r)
                struct.pack_into("<H", r, 12, 499 - new_track[trk])
            if i not in plans:
                out.append(r)
                continue
            pos = struct.unpack("<I", r[:4])[0]
            so = struct.unpack("<f", r[24:28])[0]
            base_ms = max(0.0, so)
            for k, (t0, t1) in enumerate(plans[i]):
                t0, t1 = int(t0), int(t1)
                n = bytearray(r)
                struct.pack_into("<I", n, 0, t0)
                struct.pack_into("<I", n, 8, t1 - t0)
                struct.pack_into("<ff", n, 24, base_ms + (t0 - pos) * self.ms_per_tick,
                                 base_ms + (t1 - pos) * self.ms_per_tick)
                if self.size >= 36 and k:
                    struct.pack_into("<I", n, 32, next_id)
                    next_id += 1
                out.append(n)
        blob = b"".join(bytes(x) for x in out)
        buf = bytearray(self.buf)
        # channel colors: same-size in-place patches, all before the clips block
        chan_name, insert_color = {}, {}
        for c in self.audio_clips():
            t = c["track"]
            if groups.get(t):
                chan_name[t] = c["name"]
                k = self.chan_color.get(c["ch"])
                if k is not None:
                    a = self.events[k][2]
                    buf[a + 1:a + 5] = rgb_bytes(colors[groups[t]])
                ins = self.chan_insert.get(c["ch"], 0)
                if ins > 0:
                    insert_color.setdefault(ins, colors[groups[t]])
        self._color_inserts(buf, insert_color)
        # the clips block and the track blocks are adjacent in the file: rebuild them together
        new = encode_event(233, blob)
        end = self.events[self.idx][3]
        if groups:
            src_of = {n: t for t, n in new_track.items()}   # new slot -> old track
            ta, tb = self.tracks[-1]                          # last track = untouched default: the template
            template = [[i, bytes(d)] for i, d, *_ in self.events[ta:tb] if i != 239]
            for n, (a, b) in enumerate(self.tracks):
                src = src_of.get(n, n)
                if src in remove:
                    evs = [[i, bytes(d)] for i, d in template]
                else:
                    sa, sb = self.tracks[src]
                    evs = [[i, bytes(d)] for i, d, *_ in self.events[sa:sb]]
                if n in src_of:
                    d = bytearray(evs[0][1])
                    struct.pack_into("<I", d, 0, n + 1)   # track number
                    cat = None if src in remove else groups[src]
                    if cat:
                        d[4:8] = rgb_bytes(colors[cat])
                        label = "%s - %s" % (cat, short_name(chan_name.get(src, "")))
                        evs = [e for e in evs if e[0] != 239] + [[239, (label + "\0").encode("utf-16-le")]]
                    # byte 46 = "group with above track": on for every track of a category block but its first
                    above = src_of.get(n - 1)
                    if len(d) > 46:
                        d[46] = 1 if cat and above is not None and groups.get(above) == cat else 0
                    evs[0][1] = bytes(d)
                new += b"".join(encode_event(i, d) for i, d in evs)
            end = self.events[self.tracks[-1][1] - 1][3]
        out_buf = bytearray(bytes(buf[:self.events[self.idx][2]]) + new + bytes(buf[end:]))
        struct.pack_into("<I", out_buf, len(self.head) + 4, len(out_buf) - len(self.head) - 8)
        open(dst, "wb").write(out_buf)
        return len(self.recs), len(out)


def _insert_color_patch(events, start, insert_color):
    """Mixer insert colors, so the mixer shows the same colors as the playlist. Inserts are the 236-event
    blocks after the playlist (block 0 = master); FL writes insert n's color (149), icon (95) and name (204)
    between insert n-1's output event (147) and insert n's 236. -> [(offset, old_len, new_bytes)]"""
    ins = [k for k in range(start, len(events)) if events[k][0] == 236]
    out = []
    for n, col in insert_color.items():
        if not 1 <= n < len(ins):
            continue
        lo, hi = ins[n - 1], ins[n]
        k149 = next((k for k in range(lo, hi) if events[k][0] == 149), None)
        if k149 is not None:
            out.append((events[k149][2] + 1, 4, rgb_bytes(col)))
            continue
        k147 = max((k for k in range(lo, hi) if events[k][0] == 147), default=None)
        if k147 is not None:
            out.append((events[k147][3], 0, encode_event(149, rgb_bytes(col))))
    return out


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flp")
    ap.add_argument("--db", type=float, default=-50, help="silence threshold in dBFS (default -50)")
    ap.add_argument("--gap", type=float, default=0.3, help="shortest silence to remove, seconds (default 0.3)")
    ap.add_argument("--pad", type=float, default=0.01, help="kept before each sound, seconds (default 0.01)")
    ap.add_argument("--tail", type=float, help="kept after each sound, seconds (default: same as --pad)")
    ap.add_argument("--snap", type=float, default=0, help="snap cuts outward to this many beats (1 = beat, 4 = bar)")
    ap.add_argument("--rough", action="store_true", help="coarse chops: -40 dB, 2 s gaps, 150 ms pad, snap to beats")
    ap.add_argument("--group", action="store_true", help="sort tracks into Drums/Bass/Synths/... blocks and color them")
    ap.add_argument("--remove-blank", action="store_true", help="delete playlist tracks whose clips come out with no sound")
    ap.add_argument("--bpm", type=float, help="project tempo, if it can't be read from the file")
    ap.add_argument("--out", help="output file (default <name>_stripped.flp)")
    args = ap.parse_args()
    if args.rough:   # only fills in what wasn't given explicitly
        given = set(a.split("=")[0] for a in sys.argv[1:])
        for k, v in (("--db", -40), ("--gap", 2.0), ("--pad", 0.15), ("--snap", 1)):
            if k not in given:
                setattr(args, k[2:], v)

    proj = Project(args.flp, args.bpm)
    cache, plans = {}, {}
    clips = proj.audio_clips()
    for name, why in sorted(proj.skipped.items()):
        print("skip %s: %s" % (name, why))
    for c in clips:
        if c["sample"] not in cache:
            cache[c["sample"]] = load_peaks(c["sample"], WIN)
        plans[c["i"]] = proj.plan(c, *cache[c["sample"]], args.db, args.gap, args.pad, args.snap, args.tail)
        print("%3d  %s" % (len(plans[c["i"]]), c["name"]))
    dst = args.out or os.path.splitext(args.flp)[0] + "_stripped.flp"
    groups = {c["track"]: guess_category(c["name"]) for c in clips} if args.group else {}
    remove = set()
    if args.remove_blank:
        by_track = {}
        for c in clips:
            by_track.setdefault(c["track"], []).append(len(plans[c["i"]]))
        remove = {t for t, n in by_track.items() if not any(n)}
        groups.update({t: groups.get(t) for t in by_track})   # everyone takes part so the gaps close
    names = {c["track"]: c["name"] for c in clips}
    for t, g in sorted(groups.items(), key=lambda x: (x[0] in remove, CAT_NAMES.index(x[1]) if x[1] else -1, x[0])):
        print("  %-7s %s" % ("REMOVED" if t in remove else g or "", short_name(names[t])))
    n0, n1 = proj.write(plans, dst, groups or None, remove=remove)
    print("tempo %.3f bpm, ppq %d, %d-byte clip records" % (proj.tempo, proj.ppq, proj.size))
    print("clips: %d -> %d   ->  %s" % (n0, n1, dst))


if __name__ == "__main__":
    main()
