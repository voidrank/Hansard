#!/usr/bin/env python3
"""The MOBILE preview — a phone-shaped GLANCE of the project, built to land in your hand.

  python3 mobile.py [project]      # -> research/viz/<project>.mobile.png  (or .mobile.html)

The HTML report and the slide deck are *addresses* — a `/home/.../viz/<name>.html` path is
useless on a phone. This renders the compass essentials (goal · stance · pillars · main thread)
into ONE tall, dark, big-type card that previews INLINE as a zoomable image when the close
SendUserFile's it — so every plan/execute turn actually puts the picture in your hand, not just
a path you can't open from the couch.

Pure Pillow, no browser (headless Chrome needs system GUI libs that aren't guaranteed; a PNG
card needs none). It INVENTS nothing — every line is folded from the SAME substrate the HTML
report reads (goal.<name>.txt + plan.<name>.jsonl), reusing plan.* / viz.split_goal so the card
can never drift from the report. Graceful: if Pillow is missing it writes a self-contained,
phone-responsive <name>.mobile.html fallback instead, so the preview always builds.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import plan          # noqa: E402
import viz           # noqa: E402  (reuse split_goal — single source w/ the report)
import paths         # noqa: E402  — per-project data lives outside the versioned plugin dir

# --- design tokens (shared register with deck.py) -------------------------------------
BG   = (0x0A, 0x0E, 0x1A)
INK  = (0xF2, 0xF6, 0xFC)
MUT  = (0x7E, 0x8C, 0xA6)
ACC  = (0x4C, 0xC9, 0xF0)
ACC2 = (0x2D, 0xD4, 0xBF)
OK   = (0x34, 0xD3, 0x99)
WARN = (0xFB, 0xBF, 0x24)
RULE = (0x1E, 0x2A, 0x44)

W = 1080            # phone-portrait width; height grows to fit then crops
MARGIN = 72
_FONT_LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_LATIN_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_CJK = "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"  # covers zh/ja/ko/latin


def _trunc(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def _has_cjk(s):
    """Any char DejaVu can't render (CJK etc.) — those runs must use the CJK-capable font."""
    return any(ord(c) > 0x2E80 for c in s)


class _Fonts:
    """Pick a font that actually HAS the glyphs: DejaVu (crisp latin, has bold) for ascii-ish
    text, Droid Sans Fallback (zh/ja/ko) the moment a string carries CJK. One font per string
    keeps it simple and tofu-free."""
    def __init__(self, ImageFont):
        self._F = ImageFont
        self._cache = {}

    def _load(self, path, size):
        key = (path, size)
        if key not in self._cache:
            self._cache[key] = self._F.truetype(path, size)
        return self._cache[key]

    def pick(self, text, size, bold=False):
        if _has_cjk(text):
            return self._load(_FONT_CJK, size)           # Droid: no bold variant -> stroke fakes it
        return self._load(_FONT_LATIN_B if bold else _FONT_LATIN, size)


def _wrap(draw, text, fonts, size, bold, max_w):
    """Greedy wrap that works for BOTH latin (break on spaces) and CJK (break on chars). Tokens
    are space-delimited; an oversized token (a long CJK run, a URL) is split char-by-char."""
    def width(s):
        return draw.textlength(s, font=fonts.pick(s, size, bold))
    out = []
    line = ""
    tokens = []
    for tok in str(text).split(" "):
        tokens.append(tok)
    for i, tok in enumerate(tokens):
        cand = tok if not line else line + " " + tok
        if width(cand) <= max_w:
            line = cand
            continue
        if line:
            out.append(line)
            line = ""
        # token itself too wide -> char-break it
        if width(tok) <= max_w:
            line = tok
        else:
            cur = ""
            for ch in tok:
                if width(cur + ch) <= max_w or not cur:
                    cur += ch
                else:
                    out.append(cur)
                    cur = ch
            line = cur
    if line:
        out.append(line)
    return out or [""]


def _render_png(name, png_path):
    """The phone card. Returns png_path on success, None if Pillow/fonts are unavailable."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    try:
        fonts = _Fonts(ImageFont)
        # substrate (same reads as the report)
        gp = paths.resolve(f"goal.{name}.txt")
        goal, bar = viz.split_goal(gp.read_text(encoding="utf-8") if gp.exists() else "")
        pl = plan.load(name)
        summ = plan.summary(pl) if pl else {"counts": {}, "decided_built": 0, "total": 0}
        c = summ["counts"]
        pillars = plan.pillars(pl) if pl else []
        mt = plan.main_thread(pl) if pl else None

        img = Image.new("RGB", (W, 2600), BG)
        d = ImageDraw.Draw(img)
        x = MARGIN
        maxw = W - 2 * MARGIN
        y = MARGIN

        def block(text, size, color, bold=False, gap=14, lead=1.18, stroke=0):
            nonlocal y
            for ln in _wrap(d, text, fonts, size, bold, maxw):
                f = fonts.pick(ln, size, bold)
                d.text((x, y), ln, font=f, fill=color, stroke_width=stroke, stroke_fill=color)
                y += int(size * lead)
            y += gap

        def rule(color=RULE, gap=26):
            nonlocal y
            y += 6
            d.line([(x, y), (x + maxw, y)], fill=color, width=2)
            y += gap

        # eyebrow
        block(f"TRAINLINT · {name}", 30, ACC2, bold=True, gap=22)
        # goal headline (the glance — cap so the card stays a card)
        block(_trunc(goal, 300) if goal else "no goal yet — run /trainlint:plan",
              46, INK, bold=True, gap=20, lead=1.28, stroke=1)
        if bar:
            block("DONE = " + _trunc(bar, 170), 27, OK, gap=24, lead=1.3)
        rule()
        # stance line (built-of-decided FIRST — decided≠built)
        decided = c.get("decided", 0)
        # no emoji in the PNG: neither DejaVu nor Droid carries emoji glyphs -> they'd tofu. The
        # HTML fallback keeps them (system font renders them).
        stance = (f"{summ.get('decided_built', 0)}/{decided} built  ·  "
                  f"{c.get('verified', 0)} verified  ·  {c.get('open', 0)} open  ·  "
                  f"{len(pillars)} pillars")
        block(stance, 30, MUT, gap=22)
        # pillars — the core dimensions, always shown
        if pillars:
            block("PILLARS", 24, MUT, bold=True, gap=10)
            for p in pillars:
                block("◆  " + _trunc(p.get("decision", p.get("id", "")), 90), 28, ACC2, gap=10, lead=1.25)
            y += 8
        # main thread — the one thing to drive next
        if mt:
            rule()
            block("MAIN THREAD — drive this next", 24, WARN, bold=True, gap=12)
            block("→  " + _trunc(mt.get("decision", ""), 150), 32, ACC, bold=True, gap=14, lead=1.3)

        used = y + MARGIN
        img = img.crop((0, 0, W, min(used, 2600)))
        png_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(png_path))
        return png_path
    except Exception:
        return None


_HTML_FALLBACK = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} · mobile</title>
<style>:root{{color-scheme:dark}}body{{margin:0;background:#0A0E1A;color:#F2F6FC;
font:17px/1.5 -apple-system,system-ui,'Helvetica Neue',Arial,'PingFang SC','Noto Sans CJK SC',sans-serif;
padding:22px;max-width:620px;margin:0 auto}}.eb{{color:#2DD4BF;font-weight:700;font-size:14px;
letter-spacing:.08em}}h1{{font-size:26px;line-height:1.3;margin:10px 0 14px}}
.done{{color:#34D399;font-size:15px;margin:0 0 16px}}hr{{border:0;border-top:1px solid #1E2A44;margin:18px 0}}
.stance{{color:#7E8CA6;font-size:16px}}.sec{{color:#7E8CA6;font-weight:700;font-size:13px;
letter-spacing:.08em;margin:16px 0 8px}}.pil{{color:#2DD4BF;margin:7px 0}}.mt-h{{color:#FBBF24;
font-weight:700;font-size:13px;letter-spacing:.08em}}.mt{{color:#4CC9F0;font-weight:700;font-size:19px;
margin:6px 0 0}}</style></head><body>
<div class="eb">TRAINLINT · {name}</div><h1>{goal}</h1>{done}<hr>
<div class="stance">\U0001F4D0 {stance}</div>{pillars}{mt}</body></html>"""


def _render_html(name, html_path):
    """Pillow-free fallback: a self-contained, phone-responsive card (no CDN). Always builds."""
    import html as _h
    gp = paths.resolve(f"goal.{name}.txt")
    goal, bar = viz.split_goal(gp.read_text(encoding="utf-8") if gp.exists() else "")
    pl = plan.load(name)
    summ = plan.summary(pl) if pl else {"counts": {}, "decided_built": 0}
    c = summ["counts"]
    pillars = plan.pillars(pl) if pl else []
    mt = plan.main_thread(pl) if pl else None
    decided = c.get("decided", 0)
    stance = (f"{summ.get('decided_built', 0)}/{decided} built · {c.get('verified', 0)} verified "
              f"· {c.get('open', 0)} open · {len(pillars)} pillars")
    pil_html = ""
    if pillars:
        rows = "".join(f'<div class="pil">◆ {_h.escape(_trunc(p.get("decision", p.get("id","")), 110))}</div>'
                       for p in pillars)
        pil_html = '<div class="sec">PILLARS</div>' + rows
    mt_html = ""
    if mt:
        mt_html = ('<hr><div class="mt-h">MAIN THREAD — DRIVE THIS NEXT</div>'
                   f'<div class="mt">→ {_h.escape(_trunc(mt.get("decision",""), 170))}</div>')
    out = _HTML_FALLBACK.format(
        name=_h.escape(name),
        goal=_h.escape(_trunc(goal, 360)) if goal else "no goal yet — run /trainlint:plan",
        done=(f'<div class="done">DONE = {_h.escape(_trunc(bar, 220))}</div>' if bar else ""),
        stance=_h.escape(stance), pillars=pil_html, mt=mt_html)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(out, encoding="utf-8")
    return html_path


def build(name, outdir=None):
    """Render the phone card. Returns the path the close should SendUserFile — a .mobile.png when
    Pillow is present (previews inline as a zoomable image), else a self-contained .mobile.html."""
    outdir = Path(outdir) if outdir else (ROOT / "viz")
    png = _render_png(name, outdir / f"{name}.mobile.png")
    if png is not None:
        return png
    return _render_html(name, outdir / f"{name}.mobile.html")


def main():
    import tree
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    name = tree._active(args[0] if args else None)
    path = build(name)
    print(f"MOBILE: {path}")


if __name__ == "__main__":
    main()
