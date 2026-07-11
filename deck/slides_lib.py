# -*- coding: utf-8 -*-
"""Design system + SVG primitives for the 法规检索系统设计 deck."""

FONT = "'Microsoft YaHei','Segoe UI','Segoe UI Emoji',sans-serif"
MONO = "'Consolas','Courier New',monospace"

BG        = "#EEF3FA"
PANEL     = "#FFFFFF"
INK       = "#17222E"
MUTE      = "#5A6B7B"
FAINT     = "#93A1B3"
NAVY      = "#123A63"
BLUE      = "#1470C4"
BLUE_SOFT = "#DBEAFA"
TEAL      = "#0E9C9C"
TEAL_SOFT = "#D3EFEE"
GREEN     = "#2E9E6B"
GREEN_SOFT= "#D7F0E3"
ORANGE    = "#E0812E"
ORANGE_SOFT="#FBE9D6"
PURPLE    = "#7A5CC0"
PURPLE_SOFT="#E7E0F6"
RED       = "#D2503F"
LINE      = "#D8E1EC"
W, H = 1280, 720

# syntax token colors
CK="#5FA8E0"; CS="#93D07E"; CC="#5E7891"; CN="#E0B072"; CT="#E39AC7"; CI="#CFE0F0"; CP="#9FB4C8"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=16, color=INK, weight="400", anchor="start", ff=FONT,
         opacity=1.0, spacing=None, italic=False):
    extra = ""
    if spacing is not None:
        extra += f' letter-spacing="{spacing}"'
    if italic:
        extra += ' font-style="italic"'
    return (f'<text x="{x}" y="{y}" font-family="{ff}" font-size="{size}" '
            f'fill="{color}" font-weight="{weight}" text-anchor="{anchor}" '
            f'opacity="{opacity}"{extra}>{esc(s)}</text>')


def rect(x, y, w, h, fill, rx=0, opacity=1.0, stroke=None, sw=1.0, dash=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" opacity="{opacity}"{st}{d}/>')


def line(x1, y1, x2, y2, stroke=LINE, sw=1.5, dash=None, opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}"{d} opacity="{opacity}" stroke-linecap="round"/>')


def circle(cx, cy, r, fill="none", stroke=None, sw=1.0, opacity=1.0):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" opacity="{opacity}"{st}/>'


def pill(x, y, w, h, fill, text_s="", tsize=14, tcolor="#FFFFFF", tweight="600",
         stroke=None, sw=1.0):
    out = rect(x, y, w, h, fill, rx=h / 2, stroke=stroke, sw=sw)
    if text_s:
        out += text(x + w / 2, y + h / 2 + tsize * 0.35, text_s, tsize, tcolor,
                    tweight, anchor="middle")
    return out


def arrow(x1, y1, x2, y2, stroke=BLUE, sw=2.4, dash=None, marker="arrow"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}"{d} marker-end="url(#{marker})" stroke-linecap="round"/>')


def wrapw(s, maxchars):
    lines, cur, curlen, token = [], "", 0, ""

    def flush():
        nonlocal cur, curlen, token
        if not token:
            return
        tlen = len(token)
        if curlen + tlen > maxchars and cur:
            lines.append(cur)
            cur2, curlen2 = token, tlen
        else:
            cur2, curlen2 = cur + token, curlen + tlen
        cur, curlen, token = cur2, curlen2, ""

    for ch in s:
        if ch == "\n":
            flush(); lines.append(cur); cur, curlen = "", 0; continue
        is_latin = (ch.isalnum() and ord(ch) < 128) or ch in "._-/%+()·:"
        if is_latin:
            token += ch
        else:
            flush()
            if ch == " ":
                if curlen + 1 > maxchars and cur:
                    lines.append(cur); cur, curlen = "", 0
                elif cur:
                    cur += " "; curlen += 1
            else:
                if curlen + 1 > maxchars and cur:
                    lines.append(cur); cur, curlen = "", 0
                cur += ch; curlen += 1
    flush()
    if cur:
        lines.append(cur)
    return lines


DEFS = f'''
<defs>
  <linearGradient id="bgg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#F4F8FD"/><stop offset="1" stop-color="#E7EEF8"/>
  </linearGradient>
  <linearGradient id="cover" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0B2C4E"/><stop offset="0.55" stop-color="#123A63"/>
    <stop offset="1" stop-color="#1470C4"/>
  </linearGradient>
  <linearGradient id="brand" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{BLUE}"/><stop offset="0.6" stop-color="{TEAL}"/>
    <stop offset="1" stop-color="{GREEN}"/>
  </linearGradient>
  <linearGradient id="bluegrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#1C82D6"/><stop offset="1" stop-color="{BLUE}"/>
  </linearGradient>
  <marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{BLUE}"/></marker>
  <marker id="arrowt" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{TEAL}"/></marker>
  <marker id="arrowg" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{GREEN}"/></marker>
  <marker id="arrowo" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{ORANGE}"/></marker>
  <marker id="arrowm" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{MUTE}"/></marker>
  <marker id="arrowp" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M0,0 L9,4.5 L0,9 Z" fill="{PURPLE}"/></marker>
  <filter id="sh" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="3" stdDeviation="7" flood-color="#123A63" flood-opacity="0.13"/>
  </filter>
</defs>'''


def svg(inner, bg="url(#bgg)", w=W, h=H):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{DEFS}'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="{bg}"/>' + inner + '</svg>')


def html_wrap(svg_str):
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<style>*{margin:0;padding:0}html,body{background:#EEF3FA}</style>'
            f'</head><body>{svg_str}</body></html>')


def card(x, y, w, h, accent=BLUE, fill=PANEL, radius=14, shadow=True):
    sh = ' filter="url(#sh)"' if shadow else ""
    o = f'<g{sh}>{rect(x, y, w, h, fill, rx=radius)}</g>'
    o += rect(x, y, 6, h, accent, rx=3)
    return o


def cap(s, y=158, color=MUTE, size=15.5):
    return text(70, y, s, size, color, "500")


def node(x, y, w, h, label, fill, stroke, tcolor=None, sub=None, tsize=15, rx=10, sw=1.6):
    """A graph node box (centered label)."""
    tcolor = tcolor or stroke
    o = rect(x, y, w, h, fill, rx=rx, stroke=stroke, sw=sw)
    if sub:
        o += text(x + w / 2, y + h / 2 - 3, label, tsize, tcolor, "800", anchor="middle")
        o += text(x + w / 2, y + h / 2 + 16, sub, 11.5, MUTE, "500", anchor="middle")
    else:
        lines = wrapw(label, int((w - 16) / (tsize * 0.62)))
        yy = y + h / 2 + tsize * 0.36 - (len(lines) - 1) * (tsize + 3) / 2
        for ln in lines:
            o += text(x + w / 2, yy, ln, tsize, tcolor, "700", anchor="middle")
            yy += tsize + 3
    return o


def codebox(x, y, w, h, lines, title=None, accent=TEAL, fs=13.5, lh=21, bg="#0E2233", pad=20):
    o = [rect(x, y, w, h, bg, rx=10), rect(x, y, 5, h, accent, rx=2)]
    yy = y + 30
    if title:
        o.append(text(x + pad, y + 26, title, 12.5, "#7FB0D9", "700", ff=MONO))
        o.append(line(x + 16, y + 38, x + w - 16, y + 38, "#213A50", 1))
        yy = y + 62
    for ln in lines:
        if isinstance(ln, (list, tuple)):
            if len(ln) == 1 and isinstance(ln[0], (list, tuple)):
                ln = ln[0]
            t, c = (ln[0], ln[1]) if len(ln) >= 2 and isinstance(ln[0], str) else ((str(ln[0]) if ln else ""), CI)
        else:
            t, c = ln, CI
        o.append(text(x + pad, yy, t, fs, c, "400", ff=MONO))
        yy += lh
    return "".join(o)
