"""
Kit de dessin vectoriel « Dessin à compteur » (SVG écrit en Python, aucun code exécuté venant de l'IA).

L'IA décrit chaque image en JSON (lieu, cadrage, persos, expression, pose, bulle, compteur) ;
ce module la DESSINE : persos chibi (grosse tête, grands yeux, lunettes rondes, casquette à compteur),
décors plats à contours épais, bulles, carton « règlement », en-tête fixe avec pastille compteur.
Toutes les coordonnées sont en pixels d'une image 1080x1920.
"""
import html
import math
import random
import re
from typing import Any, Dict, List, Optional, Tuple

W, H = 1080, 1920
INK = "#25212B"
PINK = "#F0508C"
FONT = "Fredoka"

EXPRESSIONS = ("neutral", "happy", "laugh", "shocked", "scared", "sad", "angry", "smug", "worried", "talk", "sleepy", "love")
POSES = ("idle", "arms_up", "wave", "hands_face", "point", "shrug", "crossed", "cheer", "think")
HAIR_STYLES = ("short", "curly", "long", "bun", "pigtails", "spiky", "bald", "afro")
TOP_STYLES = ("hoodie", "tshirt", "vest", "stripes", "shirt", "dress")
LOCATIONS = ("park_day", "park_night", "building", "room", "street", "classroom", "kitchen", "beach", "plain")
FRAMES = ("close", "medium", "wide", "card", "object", "choices")
POP_SLOTS = {"left": (250, 1020), "right": (830, 1020), "top": (540, 700), "low": (540, 1450)}
# en gros plan, la tête occupe le centre : les objets vont dans les coins hauts, plus petits
POP_SLOTS_CLOSE = {"left": (250, 500), "right": (830, 500), "top": (830, 500), "low": (250, 500)}
PROPS = ("hands", "phone", "clock", "book", "heart", "star", "trophy", "money", "ball", "letter", "plate", "cap",
         "gift", "pizza", "bell", "lock", "key", "camera", "flag", "fire", "bulb", "sign",
         "chalkboard", "chart_up", "chart_down", "plant", "coin", "piggy", "house", "egg")

SKINS = ("#F6D3B3", "#EBC09A", "#D9A47C", "#B97C55", "#8D5A3B", "#6B4128")
HAIRS = ("#3B2A20", "#1F1A1C", "#6B4128", "#A8652F", "#E3B35A", "#7A7A7A")
TOPS = ("#3F8E5E", "#E8823A", "#4E7FCB", "#E2574C", "#8E6BC9", "#F2C14E", "#3BB3A8", "#E86FA6")
CAPS = ("#F4B63F", "#3D6FCB", "#E2574C", "#3FA56A", "#8E6BC9", "#F2873A")

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def hexcol(v: Any, default: str) -> str:
    s = str(v or "").strip()
    return ("#" + s.lstrip("#").upper()) if _HEX.match(s) else default


def esc(t: Any) -> str:
    return html.escape(str(t or ""), quote=True)


def shade(col: str, f: float) -> str:
    """f < 1 assombrit, f > 1 éclaircit (vers le blanc)."""
    c = col.lstrip("#")
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    if f <= 1:
        r, g, b = (int(x * f) for x in (r, g, b))
    else:
        k = min(1.0, f - 1)
        r, g, b = (int(x + (255 - x) * k) for x in (r, g, b))
    return "#%02X%02X%02X" % (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def S(w: float = 7) -> str:
    return f'stroke="{INK}" stroke-width="{w:g}" stroke-linejoin="round" stroke-linecap="round"'


def text(x: float, y: float, t: str, size: float, fill: str = "#FFFFFF", weight: int = 700, anchor: str = "middle",
         stroke: Optional[str] = None, sw: float = 0, extra: str = "") -> str:
    st = f' stroke="{stroke}" stroke-width="{sw:g}" stroke-linejoin="round" paint-order="stroke"' if stroke and sw else ""
    return (f'<text x="{x:g}" y="{y:g}" font-family="{FONT}" font-weight="{weight}" font-size="{size:g}" '
            f'fill="{fill}" text-anchor="{anchor}"{st} {extra}>{esc(t)}</text>')


def fit_size(t: str, max_w: float, size: float, ratio: float = 0.58) -> float:
    """Taille de police qui fait tenir le texte dans max_w (estimation par largeur moyenne des lettres)."""
    n = max(1, len(t))
    return max(16.0, min(size, max_w / (n * ratio)))


def wrap(t: str, max_chars: int) -> List[str]:
    words, lines, cur = str(t or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


# ───────────────────────────── Personnages ─────────────────────────────

def limb(points: List[Tuple[float, float]], col: str, width: float) -> str:
    d = "M" + " L".join(f"{x:g},{y:g}" for x, y in points)
    return (f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{width + 9:g}" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{width:g}" stroke-linejoin="round" stroke-linecap="round"/>')


ARM_POSES: Dict[str, Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]] = {
    # (bras gauche du perso = côté x négatif), points : épaule -> coude -> main
    "idle": ([(-82, -228), (-112, -150), (-104, -82)], [(82, -228), (112, -150), (104, -82)]),
    "arms_up": ([(-82, -228), (-150, -330), (-178, -440)], [(82, -228), (150, -330), (178, -440)]),
    "wave": ([(-82, -228), (-112, -150), (-104, -82)], [(82, -228), (165, -300), (190, -410)]),
    "hands_face": ([(-82, -228), (-160, -250), (-118, -330)], [(82, -228), (160, -250), (118, -330)]),
    "point": ([(-82, -228), (-112, -150), (-104, -82)], [(82, -228), (180, -250), (275, -262)]),
    "shrug": ([(-82, -228), (-175, -205), (-205, -285)], [(82, -228), (175, -205), (205, -285)]),
    "crossed": ([(-82, -228), (-120, -160), (-30, -150)], [(82, -228), (120, -160), (30, -165)]),
    "cheer": ([(-82, -228), (-120, -320), (-110, -430)], [(82, -228), (175, -290), (240, -360)]),
    "think": ([(-82, -228), (-112, -150), (-104, -82)], [(82, -228), (120, -170), (40, -300)]),
}


def _eyes(expr: str, glasses: bool) -> str:
    out = []
    for sx in (-1, 1):
        ex, ey = 52 * sx, -385
        if expr in ("happy", "laugh"):
            out.append(f'<path d="M{ex - 28},{ey + 8} Q{ex},{ey - 26} {ex + 28},{ey + 8}" fill="none" {S(9)}/>')
        elif expr == "sleepy":
            out.append(f'<path d="M{ex - 26},{ey + 4} Q{ex},{ey + 18} {ex + 26},{ey + 4}" fill="none" {S(8)}/>')
        elif expr == "love":
            out.append(f'<path d="M{ex},{ey + 22} C{ex - 40},{ey - 6} {ex - 22},{ey - 36} {ex},{ey - 16} '
                       f'C{ex + 22},{ey - 36} {ex + 40},{ey - 6} {ex},{ey + 22}Z" fill="#E2574C" {S(5)}/>')
        else:
            r = 36 if expr in ("shocked", "scared") else 33
            pr = 10 if expr in ("shocked", "scared") else 15
            px = ex + (6 * sx if expr == "smug" else 0)
            py = ey + (6 if expr in ("sad", "worried") else 0)
            out.append(f'<circle cx="{ex}" cy="{ey}" r="{r}" fill="#FFFFFF" {S(6)}/>')
            out.append(f'<circle cx="{px}" cy="{py}" r="{pr}" fill="{INK}"/>')
            out.append(f'<circle cx="{px - pr * 0.35:g}" cy="{py - pr * 0.4:g}" r="{max(3, pr * 0.32):g}" fill="#FFFFFF"/>')
            if expr == "smug":
                out.append(f'<path d="M{ex - r - 2},{ey - 2} L{ex + r + 2},{ey - 2} L{ex + r},{ey - r} L{ex - r},{ey - r}Z" fill="{{SKIN}}" {S(6)}/>')
        if glasses:
            out.append(f'<circle cx="{ex}" cy="{ey}" r="48" fill="#FFFFFF" fill-opacity="0.12" {S(9)}/>')
    if glasses:
        out.append(f'<path d="M-6,-390 Q0,-398 6,-390" fill="none" {S(9)}/>')
        out.append(f'<path d="M-100,-392 L-130,-398 M100,-392 L130,-398" fill="none" {S(8)}/>')
    return "".join(out)


def _brows(expr: str, hair: str) -> str:
    y = -448
    shapes = {
        "angry": ((-82, y - 6, -24, y + 14), (24, y + 14, 82, y - 6)),
        "sad": ((-80, y + 8, -26, y - 10), (26, y - 10, 80, y + 8)),
        "worried": ((-80, y + 6, -26, y - 12), (26, y - 12, 80, y + 6)),
        "scared": ((-80, y - 2, -26, y - 16), (26, y - 16, 80, y - 2)),
        "shocked": ((-78, y - 18, -28, y - 22), (28, y - 22, 78, y - 18)),
        "smug": ((-78, y - 4, -28, y - 4), (28, y - 14, 78, y - 2)),
    }
    if expr not in shapes:
        return ""
    return "".join(f'<path d="M{a},{b} L{c},{d}" fill="none" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>' for a, b, c, d in shapes[expr])


def _mouth(expr: str) -> str:
    y = -318
    if expr in ("happy", "laugh", "cheer"):
        w = 58 if expr == "laugh" else 48
        return (f'<path d="M{-w},{y - 6} Q0,{y + 70} {w},{y - 6} Z" fill="#8E2A3A" {S(7)}/>'
                f'<path d="M{-w * 0.5:g},{y + 26} Q0,{y + 8} {w * 0.5:g},{y + 26} Q0,{y + 48} {-w * 0.5:g},{y + 26}Z" fill="#F07C8C"/>'
                f'<path d="M{-w + 8},{y - 2} L{w - 8},{y - 2} L{w - 14},{y + 10} L{-w + 14},{y + 10}Z" fill="#FFFFFF"/>')
    if expr in ("shocked", "scared"):
        rx, ry = (26, 34) if expr == "shocked" else (22, 18)
        return f'<ellipse cx="0" cy="{y + 8}" rx="{rx}" ry="{ry}" fill="#8E2A3A" {S(7)}/>'
    if expr == "talk":
        return f'<ellipse cx="0" cy="{y + 4}" rx="24" ry="16" fill="#8E2A3A" {S(6)}/>'
    if expr == "sad":
        return f'<path d="M-30,{y + 14} Q0,{y - 14} 30,{y + 14}" fill="none" {S(8)}/>'
    if expr == "angry":
        return (f'<path d="M-38,{y + 12} Q0,{y - 12} 38,{y + 12} Z" fill="#FFFFFF" {S(7)}/>'
                f'<path d="M-30,{y + 6} L30,{y + 6}" {S(4)}/>')
    if expr == "worried":
        return f'<path d="M-30,{y + 6} q10,-10 20,0 t20,0 t20,0" fill="none" {S(7)}/>'
    if expr == "smug":
        return f'<path d="M-30,{y + 2} Q10,{y + 22} 36,{y - 8}" fill="none" {S(8)}/>'
    if expr == "sleepy":
        return f'<ellipse cx="0" cy="{y + 6}" rx="12" ry="9" fill="#8E2A3A" {S(5)}/>'
    if expr == "love":
        return f'<path d="M-34,{y} Q0,{y + 34} 34,{y}" fill="none" {S(8)}/>'
    return f'<path d="M-28,{y} Q0,{y + 20} 28,{y}" fill="none" {S(8)}/>'


def _extras(expr: str) -> str:
    if expr == "scared":
        return f'<path d="M128,-450 q16,26 0,40 q-16,-14 0,-40Z" fill="#9AD7F5" {S(5)}/>'
    if expr == "sad":
        return f'<path d="M-60,-345 q12,24 0,36 q-12,-12 0,-36Z" fill="#9AD7F5" {S(5)}/>'
    if expr == "sleepy":
        return text(150, -500, "Z", 60, "#FFFFFF", 700, stroke=INK, sw=10) + text(200, -560, "z", 44, "#FFFFFF", 700, stroke=INK, sw=8)
    if expr == "angry":
        return f'<path d="M110,-500 l20,20 m0,-20 l-20,20 M135,-485 l14,0" {S(8)}/>'
    return ""


def _hair_back(style: str, col: str) -> str:
    if style == "long":
        return f'<path d="M-150,-420 Q-170,-250 -120,-200 L120,-200 Q170,-250 150,-420 Z" fill="{col}" {S(7)}/>'
    if style == "pigtails":
        return (f'<circle cx="-160" cy="-360" r="48" fill="{col}" {S(7)}/>'
                f'<circle cx="160" cy="-360" r="48" fill="{col}" {S(7)}/>')
    if style == "afro":
        return f'<circle cx="0" cy="-430" r="185" fill="{col}" {S(7)}/>'
    if style == "bun":
        return f'<circle cx="0" cy="-545" r="52" fill="{col}" {S(7)}/>'
    return ""


def _hair_front(style: str, col: str, has_cap: bool) -> str:
    if style in ("bald",):
        return ""
    if has_cap:
        # mèches visibles sous la casquette
        if style in ("long", "pigtails", "afro"):
            return ""
        return (f'<path d="M-136,-430 Q-140,-395 -122,-372 L-112,-414 Z" fill="{col}" {S(5)}/>'
                f'<path d="M136,-430 Q140,-395 122,-372 L112,-414 Z" fill="{col}" {S(5)}/>')
    if style == "curly":
        bumps = "".join(f'<circle cx="{x}" cy="{y}" r="40" fill="{col}" {S(6)}/>' for x, y in
                        ((-110, -470), (-60, -510), (0, -522), (60, -510), (110, -470)))
        return bumps
    if style == "spiky":
        return f'<path d="M-135,-430 L-120,-520 L-80,-470 L-50,-545 L-10,-480 L30,-550 L60,-480 L100,-530 L112,-460 L138,-430 Q0,-470 -135,-430Z" fill="{col}" {S(7)}/>'
    if style == "afro":
        return ""
    return f'<path d="M-138,-410 Q-140,-530 0,-528 Q140,-530 138,-410 Q90,-470 20,-440 Q-40,-480 -138,-410Z" fill="{col}" {S(7)}/>'


def _cap(col: str, counter: Optional[str]) -> str:
    out = (f'<path d="M-142,-428 Q-150,-575 0,-580 Q150,-575 142,-428 Z" fill="{col}" {S(8)}/>'
           f'<path d="M-60,-574 Q-70,-500 -64,-432 M60,-574 Q70,-500 64,-432" fill="none" stroke="{shade(col, 0.8)}" stroke-width="5"/>'
           f'<path d="M-158,-430 Q0,-462 158,-430 L170,-412 Q0,-440 -170,-412 Z" fill="{shade(col, 0.85)}" {S(8)}/>'
           f'<circle cx="0" cy="-582" r="14" fill="{shade(col, 0.85)}" {S(6)}/>')
    if counter:
        num, _, unit = str(counter).partition(" ")
        out += (f'<rect x="-82" y="-532" width="164" height="70" rx="20" fill="{INK}"/>'
                + text(-8 if unit else 0, -480, num, 50, "#FFFFFF", 700, "middle" if not unit else "end", extra='dx="20"')
                + (text(18, -480, unit, 28, "#FFFFFF", 600, "start") if unit else ""))
    return out


def _torso(style: str, col: str, pants: str) -> str:
    dark = shade(col, 0.8)
    legs = (f'<rect x="-62" y="-80" width="52" height="82" rx="14" fill="{pants}" {S(7)}/>'
            f'<rect x="10" y="-80" width="52" height="82" rx="14" fill="{pants}" {S(7)}/>'
            f'<ellipse cx="-42" cy="4" rx="40" ry="18" fill="{INK}"/><ellipse cx="42" cy="4" rx="40" ry="18" fill="{INK}"/>')
    if style == "dress":
        body = f'<path d="M-80,-250 Q0,-268 80,-250 L120,-60 Q0,-40 -120,-60 Z" fill="{col}" {S(8)}/>'
    else:
        body = f'<path d="M-88,-252 Q0,-272 88,-252 Q104,-160 100,-62 Q0,-48 -100,-62 Q-104,-160 -88,-252 Z" fill="{col}" {S(8)}/>'
    deco = ""
    if style == "hoodie":
        deco = (f'<path d="M-62,-258 Q0,-210 62,-258" fill="none" {S(7)}/>'
                f'<path d="M-22,-236 L-26,-180 M22,-236 L26,-180" {S(5)}/>'
                f'<circle cx="-26" cy="-176" r="6" fill="#FFFFFF" {S(4)}/><circle cx="26" cy="-176" r="6" fill="#FFFFFF" {S(4)}/>'
                f'<path d="M-58,-130 L58,-130 L68,-80 L-68,-80 Z" fill="{dark}" {S(6)}/>')
    elif style == "vest":
        deco = (f'<path d="M-96,-150 L96,-150 L98,-120 L-98,-120 Z" fill="#DADFE6" {S(5)}/>'
                f'<path d="M-100,-104 L100,-104 L100,-80 L-100,-80 Z" fill="#DADFE6" {S(5)}/>'
                f'<path d="M-6,-262 L-6,-60 M6,-262 L6,-60" stroke="{dark}" stroke-width="4"/>')
    elif style == "stripes":
        deco = "".join(f'<path d="M-98,{y} L98,{y}" stroke="#FFFFFF" stroke-width="14" stroke-opacity="0.85"/>' for y in (-205, -160, -115))
    elif style == "shirt":
        deco = (f'<path d="M-40,-262 L0,-215 L40,-262" fill="#FFFFFF" {S(6)}/>'
                f'<path d="M0,-215 L0,-70" {S(4)}/>' + "".join(f'<circle cx="0" cy="{y}" r="5" fill="{INK}"/>' for y in (-180, -140, -100)))
    elif style == "tshirt":
        deco = f'<path d="M-36,-262 Q0,-232 36,-262" fill="none" {S(6)}/>'
    return legs + body + deco


def character(c: Dict[str, Any], expr: str = "neutral", pose: str = "idle", counter: Optional[str] = None,
              say: str = "", ghost: float = 0.0, flip: bool = False) -> str:
    """Perso chibi, pieds à (0,0), ~600 px de haut à l'échelle 1."""
    skin = hexcol(c.get("skin"), SKINS[0])
    hair = hexcol(c.get("hair"), HAIRS[0])
    top = hexcol(c.get("top"), TOPS[0])
    pants = hexcol(c.get("pants"), "#3C4A66")
    hs = c.get("hair_style") if c.get("hair_style") in HAIR_STYLES else "short"
    ts = c.get("top_style") if c.get("top_style") in TOP_STYLES else "hoodie"
    cap = c.get("cap")
    cap = hexcol(cap, CAPS[0]) if cap else None
    glasses = bool(c.get("glasses"))
    expr = expr if expr in EXPRESSIONS else "neutral"
    pose = pose if pose in ARM_POSES else "idle"
    la, ra = ARM_POSES[pose]
    arm_w = 34
    parts = [_hair_back(hs, hair)]
    parts.append(_torso(ts, top, pants))
    sleeve = top if ts != "vest" else hexcol(c.get("under"), "#4E7FCB")
    for arm in (la, ra):
        parts.append(limb(arm, sleeve, arm_w))
        hx, hy = arm[-1]
        parts.append(f'<circle cx="{hx}" cy="{hy}" r="24" fill="{skin}" {S(7)}/>')
    # tête
    parts.append(f'<circle cx="-136" cy="-382" r="26" fill="{skin}" {S(7)}/><circle cx="136" cy="-382" r="26" fill="{skin}" {S(7)}/>')
    parts.append(f'<circle cx="0" cy="-392" r="140" fill="{skin}" {S(8)}/>')
    parts.append(f'<ellipse cx="-88" cy="-332" rx="24" ry="14" fill="#F28A9A" fill-opacity="0.55"/>'
                 f'<ellipse cx="88" cy="-332" rx="24" ry="14" fill="#F28A9A" fill-opacity="0.55"/>')
    parts.append(_hair_front(hs, hair, bool(cap)))
    parts.append(_eyes(expr, glasses).replace("{SKIN}", skin))
    parts.append(_brows(expr, hair))
    parts.append(f'<path d="M-8,-352 Q0,-342 8,-352" fill="none" {S(6)}/>')
    parts.append(_mouth(expr))
    if cap:
        parts.append(_cap(cap, counter))
    if pose == "hands_face":
        # mains par-dessus les joues
        for arm in (la, ra):
            hx, hy = arm[-1]
            parts.append(f'<circle cx="{hx}" cy="{hy}" r="26" fill="{skin}" {S(7)}/>')
    parts.append(_extras(expr))
    body = "".join(parts)
    if flip:
        body = f'<g transform="scale(-1,1)">{body}</g>'
    op = max(0.18, min(1.0, 1.0 - float(ghost or 0)))
    g = f'<g opacity="{op:g}">{body}</g>' if op < 0.99 else body
    return g


def bubble(x: float, y: float, txt: str, tail_x: float, tail_y: float, size: float = 46) -> str:
    """Bulle de parole centrée en (x, y), pointe vers (tail_x, tail_y)."""
    lines = wrap(str(txt).upper(), 12)[:2] or ["…"]
    longest = max(len(l) for l in lines)
    fs = size
    w = max(150, longest * fs * 0.62 + 60)
    h = len(lines) * fs * 1.1 + 40
    x0, y0 = x - w / 2, y - h / 2
    tx = max(x0 + 40, min(x0 + w - 40, tail_x))
    tail = (f'<path d="M{tx - 22:g},{y0 + h - 4:g} L{tail_x:g},{tail_y:g} L{tx + 22:g},{y0 + h - 4:g}Z" fill="#FFFFFF" {S(7)}/>'
            f'<path d="M{tx - 18:g},{y0 + h - 6:g} L{tx + 18:g},{y0 + h - 6:g}" stroke="#FFFFFF" stroke-width="9"/>')
    body = f'<rect x="{x0:g}" y="{y0:g}" width="{w:g}" height="{h:g}" rx="{min(36, h / 2):g}" fill="#FFFFFF" {S(7)}/>'
    tx_out = "".join(text(x, y0 + 20 + fs * (i + 0.85), l, fs, INK, 700) for i, l in enumerate(lines))
    return f'<g>{body}{tail}{tx_out}</g>'


# ───────────────────────────── Décors ─────────────────────────────

def _cloud(x: float, y: float, s: float = 1.0) -> str:
    return (f'<g transform="translate({x:g},{y:g}) scale({s:g})">'
            f'<path d="M-90,30 Q-110,-10 -60,-20 Q-50,-70 0,-60 Q40,-90 75,-45 Q120,-40 105,10 Q120,40 80,40 L-70,40 Q-100,40 -90,30Z" '
            f'fill="#FFFFFF" {S(6)}/></g>')


def _pine(x: float, y: float, s: float, col: str) -> str:
    d = shade(col, 0.8)
    return (f'<g transform="translate({x:g},{y:g}) scale({s:g})">'
            f'<rect x="-14" y="-30" width="28" height="40" fill="#7A4E2D" {S(6)}/>'
            f'<path d="M-90,-20 L0,-150 L90,-20Z" fill="{col}" {S(7)}/>'
            f'<path d="M-72,-110 L0,-230 L72,-110Z" fill="{col}" {S(7)}/>'
            f'<path d="M-52,-195 L0,-300 L52,-195Z" fill="{col}" {S(7)}/>'
            f'<path d="M0,-150 L60,-40 M0,-230 L45,-125" stroke="{d}" stroke-width="6" stroke-linecap="round"/></g>')


def _tent(x: float, y: float, s: float, col: str) -> str:
    return (f'<g transform="translate({x:g},{y:g}) scale({s:g})">'
            f'<path d="M-110,0 L0,-140 L110,0Z" fill="{col}" {S(7)}/>'
            f'<path d="M-30,0 L0,-140 L30,0Z" fill="{shade(col, 0.7)}" {S(6)}/></g>')


def _flowers(rng: random.Random, y0: float, y1: float, n: int = 12) -> str:
    out = []
    for _ in range(n):
        x, y = rng.uniform(20, W - 20), rng.uniform(y0, y1)
        col = rng.choice(("#FFFFFF", "#F7D046", "#F28AB2"))
        out.append(f'<g transform="translate({x:.0f},{y:.0f})">' + "".join(
            f'<circle cx="{8 * math.cos(a):.1f}" cy="{8 * math.sin(a):.1f}" r="7" fill="{col}" stroke="{INK}" stroke-width="2.5"/>'
            for a in (0, 1.26, 2.51, 3.77, 5.03)) + f'<circle r="5" fill="#F2A33A"/></g>')
    return "".join(out)


def _tufts(rng: random.Random, y0: float, y1: float, col: str, n: int = 16) -> str:
    out = []
    for _ in range(n):
        x, y = rng.uniform(20, W - 20), rng.uniform(y0, y1)
        out.append(f'<path d="M{x - 14:.0f},{y:.0f} L{x - 6:.0f},{y - 26:.0f} L{x:.0f},{y - 6:.0f} L{x + 7:.0f},{y - 30:.0f} L{x + 14:.0f},{y:.0f}" '
                   f'fill="none" stroke="{col}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(out)


def _outdoor(rng: random.Random, night: bool, horizon: float = 1130, pal: Optional[Dict[str, str]] = None) -> str:
    pal = pal or {}
    if night:
        sky_a, sky_b = "#1B2546", "#33446E"
        grass, tree = hexcol(pal.get("ground"), "#2F5140"), "#1E3B33"
    else:
        sky_a, sky_b = hexcol(pal.get("sky"), "#9FD4F2"), "#DDF1FB"
        grass, tree = hexcol(pal.get("ground"), "#86C76A"), "#2F7048"
    out = [f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky_a}"/>'
           f'<stop offset="1" stop-color="{sky_b}"/></linearGradient></defs>',
           f'<rect width="{W}" height="{H}" fill="url(#sky)"/>']
    if night:
        out.append(f'<circle cx="840" cy="420" r="90" fill="#F6E7A8" fill-opacity="0.18"/><circle cx="840" cy="420" r="62" fill="#F6E7A8" {S(6)}/>')
        out += [f'<circle cx="{rng.uniform(30, W - 30):.0f}" cy="{rng.uniform(320, horizon - 250):.0f}" r="{rng.uniform(3, 6):.1f}" fill="#FFF6C8"/>' for _ in range(40)]
    else:
        out.append(f'<circle cx="880" cy="430" r="70" fill="#FFE07A" {S(6)}/>')
        out += [_cloud(rng.uniform(120, 960), rng.uniform(380, 640), rng.uniform(0.8, 1.3)) for _ in range(3)]
    out.append(f'<path d="M0,{horizon - 60} Q270,{horizon - 140} 540,{horizon - 70} T1080,{horizon - 90} L1080,{horizon + 20} L0,{horizon + 20}Z" '
               f'fill="{shade(grass, 0.88)}" {S(6)}/>')
    for i in range(9):
        x = -40 + i * 145 + rng.uniform(-30, 30)
        out.append(_pine(x, horizon + 10 - rng.uniform(0, 30), rng.uniform(0.75, 1.05), tree))
    out.append(f'<rect x="-10" y="{horizon}" width="{W + 20}" height="{H - horizon + 10}" fill="{grass}" {S(7)}/>')
    out.append(_tufts(rng, horizon + 60, H - 40, shade(grass, 0.78), 22))
    if not night:
        out.append(_flowers(rng, horizon + 80, H - 60, 14))
    else:
        out += [f'<circle cx="{rng.uniform(30, W - 30):.0f}" cy="{rng.uniform(horizon - 200, horizon + 300):.0f}" r="5" fill="#FFF29A" fill-opacity="0.9"/>' for _ in range(10)]
    return "".join(out)


def _plank_wall(x0: float, y0: float, x1: float, y1: float, col: str, horizontal: bool = True, step: float = 62) -> str:
    out = [f'<rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" fill="{col}" {S(7)}/>']
    line = shade(col, 0.82)
    if horizontal:
        y = y0 + step
        while y < y1 - 6:
            out.append(f'<path d="M{x0 + 4:g},{y:g} L{x1 - 4:g},{y:g}" stroke="{line}" stroke-width="5"/>')
            y += step
    else:
        x = x0 + step
        while x < x1 - 6:
            out.append(f'<path d="M{x:g},{y0 + 4:g} L{x:g},{y1 - 4:g}" stroke="{line}" stroke-width="5"/>')
            x += step
    return "".join(out)


def _window(x: float, y: float, w: float, h: float, night: bool = False, shutters: Optional[str] = "#3F7F5F") -> str:
    glass = "#2B3B66" if night else "#A9D8F5"
    out = ""
    if shutters:
        out += (f'<rect x="{x - w / 2 - 44:g}" y="{y - h / 2:g}" width="40" height="{h:g}" rx="4" fill="{shutters}" {S(6)}/>'
                f'<rect x="{x + w / 2 + 4:g}" y="{y - h / 2:g}" width="40" height="{h:g}" rx="4" fill="{shutters}" {S(6)}/>')
    out += (f'<rect x="{x - w / 2:g}" y="{y - h / 2:g}" width="{w:g}" height="{h:g}" fill="{glass}" {S(8)}/>'
            f'<path d="M{x:g},{y - h / 2:g} L{x:g},{y + h / 2:g} M{x - w / 2:g},{y:g} L{x + w / 2:g},{y:g}" {S(7)}/>'
            f'<rect x="{x - w / 2 - 10:g}" y="{y + h / 2:g}" width="{w + 20:g}" height="16" fill="#8A5A34" {S(5)}/>')
    return out


def _sign(x: float, y: float, label: str, col: str = "#FFFFFF", size: float = 38) -> str:
    label = str(label or "").upper()[:18]
    fs = fit_size(label, 300, size)
    w = max(140, len(label) * fs * 0.62 + 50)
    return (f'<rect x="{x - w / 2:g}" y="{y - 34:g}" width="{w:g}" height="68" rx="12" fill="{col}" {S(7)}/>'
            + text(x, y + fs * 0.35, label, fs, INK, 700))


def _bunting(y: float, rng: random.Random) -> str:
    out = [f'<path d="M0,{y:g} Q540,{y + 70:g} 1080,{y:g}" fill="none" {S(5)}/>']
    cols = ("#E2574C", "#F2C14E", "#4E7FCB", "#3FA56A", "#E86FA6")
    for i in range(12):
        x = 45 + i * 90
        yy = y + 70 * (1 - ((x - 540) / 540) ** 2) * 0.98
        out.append(f'<path d="M{x - 30:.0f},{yy:.0f} L{x + 30:.0f},{yy:.0f} L{x:.0f},{yy + 58:.0f}Z" fill="{cols[i % 5]}" {S(5)}/>')
    return "".join(out)


def location_svg(loc: Dict[str, Any], seed: int = 1) -> str:
    """Décor plein cadre 1080x1920 (sans personnages)."""
    rng = random.Random(seed)
    kind = loc.get("kind") if loc.get("kind") in LOCATIONS else "park_day"
    pal = loc.get("palette") if isinstance(loc.get("palette"), dict) else {}
    label = str(loc.get("label") or "")
    night = bool(loc.get("night")) or kind == "park_night"
    if kind in ("park_day", "park_night"):
        out = _outdoor(rng, night, pal=pal)
        for _ in range(2 if not night else 0):
            out += _tent(rng.choice((120, 960)) + rng.uniform(-40, 40), 1180 + rng.uniform(0, 40), rng.uniform(0.8, 1.0), rng.choice(TOPS))
        if night or loc.get("campfire"):
            out += _campfire(540, 1640)
        if label:
            out += _sign(540, 980, label)
        return out
    if kind == "building":
        out = _outdoor(rng, night, pal=pal)
        wall = hexcol(loc.get("wall"), "#C99A66")
        roof = shade(wall, 0.55)
        out += f'<path d="M150,700 L540,420 L930,700Z" fill="{shade(wall, 1.12)}" {S(8)}/>'
        out += f'<path d="M110,712 L540,400 L970,712 L940,736 L540,446 L140,736Z" fill="{roof}" {S(8)}/>'
        out += _plank_wall(180, 720, 900, 1260, wall, True, 58)
        out += f'<circle cx="540" cy="600" r="54" fill="{"#2B3B66" if night else "#A9D8F5"}" {S(8)}/>'
        out += _window(330, 950, 170, 170, night)
        out += _window(750, 950, 170, 170, night)
        out += f'<rect x="465" y="1010" width="150" height="250" fill="#7A4E2D" {S(8)}/><circle cx="590" cy="1140" r="9" fill="#F2C14E" {S(4)}/>'
        if label:
            out += _sign(540, 800, label)
        return out
    if kind in ("room", "classroom", "kitchen"):
        wall = hexcol(loc.get("wall"), {"room": "#D6A872", "classroom": "#BFD8C6", "kitchen": "#F2E3C2"}[kind])
        floor_y = 1380
        out = ""
        if kind == "room":
            out += _plank_wall(-10, -10, W + 10, floor_y, wall, False, 70)
        elif kind == "kitchen":
            out += f'<rect x="-10" y="-10" width="{W + 20}" height="{floor_y + 10}" fill="{wall}"/>'
            out += "".join(f'<path d="M0,{y} L{W},{y}" stroke="{shade(wall, 0.85)}" stroke-width="4"/>' for y in range(260, floor_y, 90))
            out += "".join(f'<path d="M{x},260 L{x},{floor_y}" stroke="{shade(wall, 0.85)}" stroke-width="4"/>' for x in range(0, W, 90))
        else:
            out += f'<rect x="-10" y="-10" width="{W + 20}" height="{floor_y + 10}" fill="{wall}"/>'
        out += _window(230, 640, 200, 230, night, None) + _window(850, 640, 200, 230, night, None)
        if kind == "room":
            out += _bunting(330, rng)
        if kind == "classroom":
            out += f'<rect x="330" y="470" width="420" height="300" rx="10" fill="#2F5D4A" {S(10)}/>'
            out += f'<rect x="330" y="770" width="420" height="22" fill="#8A5A34" {S(6)}/>'
            if label:
                out += text(540, 640, label.upper()[:16], fit_size(label, 380, 56), "#FFFFFF", 600)
        elif label:
            out += _sign(540, 520, label, "#FFF4DC")
        if kind == "kitchen":
            out += f'<rect x="-10" y="1180" width="{W + 20}" height="60" fill="#C98A4B" {S(7)}/>'
            out += f'<rect x="-10" y="1240" width="{W + 20}" height="{floor_y - 1240}" fill="#4E6E8E" {S(7)}/>'
        floor = hexcol(pal.get("ground"), "#B9825A" if kind != "classroom" else "#C9A27A")
        out += _plank_wall(-10, floor_y, W + 10, H + 10, floor, True, 90)
        if night:
            out += f'<rect width="{W}" height="{H}" fill="#101A3A" fill-opacity="0.32"/>'
        return out
    if kind == "street":
        out = _outdoor(rng, night, horizon=1240, pal=pal)
        x = -30
        while x < W:
            bw, bh = rng.uniform(220, 320), rng.uniform(520, 820)
            col = rng.choice(("#E9A26B", "#D9785F", "#8FB3D9", "#E8C86A", "#B7A1D6"))
            out += f'<rect x="{x:.0f}" y="{1250 - bh:.0f}" width="{bw:.0f}" height="{bh + 10:.0f}" fill="{col}" {S(7)}/>'
            for wy in range(int(1250 - bh + 50), 1180, 120):
                for wx in (x + 40, x + bw - 100):
                    out += f'<rect x="{wx:.0f}" y="{wy}" width="60" height="70" fill="{"#F6E7A8" if night else "#A9D8F5"}" {S(5)}/>'
            x += bw
        out += f'<rect x="-10" y="1240" width="{W + 20}" height="120" fill="#C9C3B8" {S(7)}/>'
        out += f'<rect x="-10" y="1360" width="{W + 20}" height="{H - 1350}" fill="#5D6470" {S(7)}/>'
        out += "".join(f'<rect x="{x}" y="1600" width="110" height="18" rx="9" fill="#F2F2F2"/>' for x in range(40, W, 220))
        if label:
            out += _sign(540, 760, label)
        return out
    if kind == "beach":
        out = (f'<rect width="{W}" height="{H}" fill="#9FD4F2"/><circle cx="820" cy="470" r="80" fill="#FFE07A" {S(6)}/>'
               + _cloud(260, 520, 1.1) + f'<rect x="-10" y="1000" width="{W + 20}" height="300" fill="#3FA7D6" {S(7)}/>'
               + "".join(f'<path d="M{x},{y} q30,-18 60,0 t60,0" fill="none" stroke="#FFFFFF" stroke-width="6"/>' for x, y in ((80, 1080), (520, 1140), (760, 1060), (300, 1220)))
               + f'<path d="M-10,1260 Q540,1200 1090,1260 L1090,{H + 10} L-10,{H + 10}Z" fill="#F2D49B" {S(7)}/>')
        return out
    bg = hexcol(loc.get("color") or pal.get("sky"), "#F6D365")
    return (f'<defs><radialGradient id="pl" cx="0.5" cy="0.45" r="0.75"><stop offset="0" stop-color="{shade(bg, 1.35)}"/>'
            f'<stop offset="1" stop-color="{bg}"/></radialGradient></defs><rect width="{W}" height="{H}" fill="url(#pl)"/>')


def _campfire(x: float, y: float) -> str:
    return (f'<g transform="translate({x:g},{y:g})">'
            f'<ellipse cx="0" cy="10" rx="170" ry="40" fill="#7A7A7A" {S(6)}/>'
            + "".join(f'<ellipse cx="{dx}" cy="{dy}" rx="34" ry="22" fill="#9A9A9A" {S(5)}/>' for dx, dy in ((-140, 0), (-80, 24), (0, 30), (80, 24), (140, 0)))
            + f'<path d="M-90,0 L90,-30 M-90,-30 L90,0" stroke="#7A4E2D" stroke-width="26" stroke-linecap="round"/>'
            f'<path d="M-70,-20 Q-80,-120 -20,-190 Q-10,-120 20,-160 Q40,-220 30,-280 Q110,-180 80,-20Z" fill="#F28A2E" {S(7)}/>'
            f'<path d="M-30,-20 Q-40,-90 0,-130 Q20,-90 40,-110 Q60,-60 40,-20Z" fill="#FFD447"/>'
            f'<ellipse cx="0" cy="-80" rx="260" ry="200" fill="#FFB347" fill-opacity="0.12"/></g>')


# ───────────────────────────── Objets (plan « objet ») ─────────────────────────────

def prop_svg(kind: str, label: str = "") -> str:
    """Objet dessiné centré en (0,0), ~500 px."""
    k = kind if kind in PROPS else "sign"
    if k == "hands":
        palm = "#F6D3B3"
        one = (f'<path d="M-60,120 L-70,-40 Q-75,-60 -55,-62 L-50,-10 L-52,-120 Q-50,-140 -32,-138 L-25,-20 L-22,-150 Q-20,-170 0,-168 '
               f'L5,-20 L12,-140 Q16,-160 34,-156 L32,-10 L45,-90 Q52,-108 68,-100 L60,40 Q55,100 20,120Z" fill="{palm}" {S(8)}/>')
        return f'<g transform="translate(-140,0) scale(1.3)">{one}</g><g transform="translate(140,0) scale(-1.3,1.3)">{one}</g>'
    if k == "phone":
        return (f'<rect x="-130" y="-240" width="260" height="480" rx="40" fill="{INK}" {S(8)}/>'
                f'<rect x="-108" y="-200" width="216" height="380" rx="16" fill="#A9D8F5"/>'
                f'<circle cx="0" cy="212" r="14" fill="#555"/>' + (text(0, 0, label.upper()[:10], fit_size(label, 190, 52), INK, 700) if label else ""))
    if k == "clock":
        return (f'<circle r="230" fill="#FFFFFF" {S(12)}/>' + "".join(
            f'<path d="M{200 * math.cos(a):.0f},{200 * math.sin(a):.0f} L{176 * math.cos(a):.0f},{176 * math.sin(a):.0f}" {S(10)}/>'
            for a in [i * math.pi / 6 for i in range(12)]) + f'<path d="M0,0 L0,-150 M0,0 L110,40" {S(16)}/><circle r="16" fill="{INK}"/>')
    if k == "book":
        return (f'<path d="M0,-180 Q-130,-230 -260,-180 L-260,180 Q-130,130 0,180Z" fill="#FFF4DC" {S(9)}/>'
                f'<path d="M0,-180 Q130,-230 260,-180 L260,180 Q130,130 0,180Z" fill="#FFF4DC" {S(9)}/>'
                + "".join(f'<path d="M{-220 + 260 * s},{y} L{-40 + 260 * s},{y}" stroke="#B9A58A" stroke-width="8"/>' for s in (0, 1) for y in (-100, -40, 20, 80)))
    if k == "heart":
        return f'<path d="M0,180 C-300,-20 -180,-260 0,-110 C180,-260 300,-20 0,180Z" fill="#E2574C" {S(12)}/>'
    if k == "star":
        pts = " ".join(f"{(220 if i % 2 == 0 else 95) * math.cos(-math.pi / 2 + i * math.pi / 5):.0f},{(220 if i % 2 == 0 else 95) * math.sin(-math.pi / 2 + i * math.pi / 5):.0f}" for i in range(10))
        return f'<polygon points="{pts}" fill="#F7D046" {S(12)}/>'
    if k == "trophy":
        return (f'<path d="M-150,-200 L150,-200 Q150,40 0,60 Q-150,40 -150,-200Z" fill="#F2C14E" {S(10)}/>'
                f'<path d="M-150,-160 Q-260,-150 -220,-60 Q-190,0 -120,0 M150,-160 Q260,-150 220,-60 Q190,0 120,0" fill="none" {S(14)}/>'
                f'<rect x="-30" y="60" width="60" height="90" fill="#E0A93A" {S(8)}/><rect x="-120" y="150" width="240" height="60" rx="10" fill="#7A4E2D" {S(8)}/>')
    if k == "money":
        return "".join(f'<g transform="rotate({r}) translate({dx},{dy})"><rect x="-200" y="-100" width="400" height="200" rx="16" fill="#7FC77A" {S(9)}/>'
                       f'<circle r="60" fill="#5FAF5A" {S(7)}/>' + text(0, 22, "€", 70, "#FFFFFF", 700) + '</g>' for r, dx, dy in ((-12, -20, 40), (8, 20, -30)))
    if k == "ball":
        return f'<circle r="200" fill="#FFFFFF" {S(10)}/><polygon points="0,-70 66,-22 41,57 -41,57 -66,-22" fill="{INK}"/>'
    if k == "letter":
        return (f'<rect x="-250" y="-160" width="500" height="320" rx="12" fill="#FFF4DC" {S(10)}/>'
                f'<path d="M-250,-160 L0,40 L250,-160" fill="none" {S(10)}/><circle cx="0" cy="40" r="34" fill="#E2574C" {S(7)}/>')
    if k == "plate":
        return (f'<ellipse rx="270" ry="120" fill="#FFFFFF" {S(10)}/><ellipse rx="190" ry="80" fill="#F2E3C2" {S(6)}/>'
                f'<path d="M-120,-20 Q0,-120 120,-20 Q0,30 -120,-20Z" fill="#E8823A" {S(8)}/>')
    if k == "cap":
        return f'<g transform="scale(1.6) translate(0,480)">{_cap(CAPS[0], label or "0 min")}</g>'
    if k == "gift":
        return (f'<rect x="-200" y="-120" width="400" height="300" fill="#E2574C" {S(10)}/><rect x="-230" y="-190" width="460" height="80" fill="#E86F64" {S(10)}/>'
                f'<rect x="-30" y="-190" width="60" height="370" fill="#F7D046" {S(8)}/>'
                f'<path d="M0,-190 Q-120,-320 -140,-210Z M0,-190 Q120,-320 140,-210Z" fill="#F7D046" {S(8)}/>')
    if k == "pizza":
        return (f'<path d="M0,220 L-220,-180 Q0,-260 220,-180Z" fill="#F2C14E" {S(10)}/><path d="M-220,-180 Q0,-260 220,-180 L200,-150 Q0,-225 -200,-150Z" fill="#C98A4B" {S(8)}/>'
                + "".join(f'<circle cx="{x}" cy="{y}" r="34" fill="#E2574C" {S(6)}/>' for x, y in ((-70, -100), (60, -80), (0, 30))))
    if k == "bell":
        return (f'<path d="M-170,120 Q-150,-200 0,-210 Q150,-200 170,120 L210,160 L-210,160Z" fill="#F2C14E" {S(10)}/>'
                f'<circle cx="0" cy="190" r="40" fill="#E0A93A" {S(8)}/><circle cx="0" cy="-230" r="24" fill="#E0A93A" {S(8)}/>')
    if k == "lock":
        return (f'<path d="M-120,-40 L-120,-140 Q-120,-260 0,-260 Q120,-260 120,-140 L120,-40" fill="none" stroke="{INK}" stroke-width="56"/>'
                f'<path d="M-120,-40 L-120,-140 Q-120,-260 0,-260 Q120,-260 120,-140 L120,-40" fill="none" stroke="#B9C2CC" stroke-width="38"/>'
                f'<rect x="-200" y="-60" width="400" height="300" rx="30" fill="#F2C14E" {S(10)}/><circle cx="0" cy="70" r="30" fill="{INK}"/>')
    if k == "key":
        return (f'<circle cx="-140" cy="0" r="100" fill="#F2C14E" {S(10)}/><circle cx="-140" cy="0" r="40" fill="#FFF4DC" {S(8)}/>'
                f'<path d="M-40,-24 L240,-24 L240,24 L190,24 L190,80 L140,80 L140,24 L-40,24Z" fill="#F2C14E" {S(10)}/>')
    if k == "camera":
        return (f'<rect x="-240" y="-140" width="480" height="300" rx="34" fill="#4E5566" {S(10)}/><rect x="-100" y="-190" width="200" height="60" rx="14" fill="#4E5566" {S(9)}/>'
                f'<circle cx="0" cy="10" r="110" fill="#2B3B66" {S(10)}/><circle cx="0" cy="10" r="60" fill="#A9D8F5" {S(7)}/>')
    if k == "flag":
        return (f'<rect x="-170" y="-260" width="24" height="520" fill="#7A4E2D" {S(8)}/>'
                f'<path d="M-146,-250 Q0,-300 180,-240 L180,-40 Q0,-100 -146,-50Z" fill="#E2574C" {S(10)}/>')
    if k == "fire":
        return f'<g transform="scale(1.5) translate(0,120)">{_campfire(0, 0)}</g>'
    if k == "bulb":
        return (f'<circle cx="0" cy="-60" r="170" fill="#FFE07A" {S(10)}/><rect x="-80" y="100" width="160" height="110" rx="20" fill="#B9C2CC" {S(9)}/>'
                f'<path d="M-40,40 L-20,-60 L0,20 L20,-60 L40,40" fill="none" {S(8)}/>')
    if k == "chalkboard":
        lab = (label or "").upper()[:16]
        return (f'<rect x="-330" y="-230" width="660" height="440" rx="18" fill="#7A4E2D" {S(10)}/>'
                f'<rect x="-295" y="-195" width="590" height="370" rx="8" fill="#2F5245"/>'
                f'<path d="M-60,210 L-120,320 M60,210 L120,320" {S(10)}/>'
                + (text(0, 10, lab, fit_size(lab, 520, 90), "#F4F1E6", 700) if lab else
                   f'<path d="M-230,110 Q-60,60 0,-20 T230,-140" fill="none" stroke="#F4F1E6" stroke-width="12" stroke-linecap="round"/>'))
    if k in ("chart_up", "chart_down"):
        up = k == "chart_up"
        col = "#3FA56A" if up else "#E2574C"
        bars = [(-210, 120), (-90, 190), (30, 260), (150, 340)] if up else [(-210, 340), (-90, 260), (30, 190), (150, 120)]
        return (f'<rect x="-300" y="-260" width="600" height="520" rx="24" fill="#FFFFFF" {S(10)}/>'
                f'<path d="M-250,200 L260,200 M-250,200 L-250,-220" {S(9)}/>'
                + "".join(f'<rect x="{x}" y="{200 - h}" width="80" height="{h}" fill="{col}" {S(7)}/>' for x, h in bars)
                + (f'<path d="M-230,60 L-60,-20 L40,20 L230,-180 M170,-190 L235,-185 L225,-120" fill="none" stroke="{INK}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>' if up else
                   f'<path d="M-230,-180 L-60,-80 L40,-110 L230,60 M170,70 L235,65 L225,0" fill="none" stroke="{INK}" stroke-width="14" stroke-linecap="round" stroke-linejoin="round"/>'))
    if k == "plant":
        return (f'<path d="M-150,80 L150,80 L115,260 L-115,260Z" fill="#C9743F" {S(10)}/><rect x="-170" y="40" width="340" height="60" rx="12" fill="#D9844F" {S(9)}/>'
                f'<path d="M0,40 L0,-200" stroke="#3F8E5E" stroke-width="22"/>'
                f'<path d="M0,-60 Q-180,-80 -200,-220 Q-40,-200 0,-60Z M0,-120 Q180,-140 200,-280 Q40,-260 0,-120Z" fill="#5FB46A" {S(8)}/>')
    if k == "coin":
        return (f'<circle r="210" fill="#F2C14E" {S(12)}/><circle r="160" fill="none" stroke="#E0A93A" stroke-width="14"/>'
                + text(0, 46, label[:3] if label else "€", 150, "#FFFFFF", 700, stroke=INK, sw=10))
    if k == "piggy":
        return (f'<ellipse cx="0" cy="20" rx="250" ry="190" fill="#F4A6B8" {S(10)}/><circle cx="170" cy="-120" r="60" fill="#F4A6B8" {S(9)}/>'
                f'<ellipse cx="250" cy="40" rx="60" ry="50" fill="#F28AA2" {S(8)}/><circle cx="235" cy="35" r="9" fill="{INK}"/><circle cx="265" cy="35" r="9" fill="{INK}"/>'
                f'<circle cx="150" cy="-40" r="16" fill="{INK}"/><rect x="-60" y="-178" width="120" height="22" rx="10" fill="{INK}"/>'
                + "".join(f'<rect x="{x}" y="170" width="60" height="80" rx="14" fill="#F28AA2" {S(8)}/>' for x in (-170, -60, 50, 140)))
    if k == "house":
        return (f'<path d="M-260,-40 L0,-260 L260,-40Z" fill="#E2574C" {S(10)}/><rect x="-210" y="-40" width="420" height="300" fill="#FFF4DC" {S(10)}/>'
                f'<rect x="-50" y="100" width="100" height="160" fill="#7A4E2D" {S(8)}/><rect x="-170" y="20" width="90" height="90" fill="#A9D8F5" {S(7)}/>'
                f'<rect x="80" y="20" width="90" height="90" fill="#A9D8F5" {S(7)}/>')
    if k == "egg":
        return f'<path d="M0,-240 C170,-240 220,40 200,110 C170,230 -170,230 -200,110 C-220,40 -170,-240 0,-240Z" fill="#FFF8EC" {S(12)}/>'
    lab = (label or "?").upper()[:14]
    return (f'<rect x="-280" y="-150" width="560" height="300" rx="30" fill="#FFF4DC" {S(10)}/>'
            + text(0, 30, lab, fit_size(lab, 480, 110), INK, 700))


# ───────────────────────────── Composition d'une image ─────────────────────────────

FRAMINGS = {
    # échelle du perso, y des pieds, écart horizontal entre persos
    "close": (2.55, 1960, 0),
    "medium": (1.45, 1720, 330),
    "wide": (1.05, 1640, 215),
}


def _slots(n: int, gap: float) -> List[float]:
    if n <= 1:
        return [540.0]
    total = gap * (n - 1)
    return [540 - total / 2 + i * gap for i in range(n)]


def panel_svg(panel: Dict[str, Any], cast: Dict[str, Dict[str, Any]], loc: Dict[str, Any], seed: int = 1) -> str:
    """Une image plein cadre (décor + persos + bulles), sans l'en-tête."""
    frame = panel.get("frame") if panel.get("frame") in FRAMES else "medium"
    if frame == "card":
        return card_svg(panel.get("card") or {}, panel.get("card_bg"))
    if frame == "choices":
        return choices_svg(panel.get("choices") or {})
    return _panel_body(panel, frame, cast, loc, seed) + pops_svg(panel.get("pops") or [], close=frame == "close")


def pops_svg(pops: List[Dict[str, Any]], close: bool = False) -> str:
    """Objets qui « apparaissent » par-dessus l'image (Parabole) : petit objet dessiné à un emplacement fixe."""
    out = []
    slots, sc = (POP_SLOTS_CLOSE, 0.4) if close else (POP_SLOTS, 0.42)
    for p in pops[:3]:
        if not isinstance(p, dict) or p.get("prop") not in PROPS:
            continue
        x, y = slots.get(p.get("at"), slots["top"])
        out.append(f'<g transform="translate({x},{y}) scale({sc})">{prop_svg(p["prop"], str(p.get("label") or ""))}</g>')
    return "".join(out)


def _panel_body(panel: Dict[str, Any], frame: str, cast: Dict[str, Dict[str, Any]], loc: Dict[str, Any], seed: int) -> str:
    out = [location_svg(loc, seed)]
    if frame == "object":
        out.append(f'<rect width="{W}" height="{H}" fill="#FFFFFF" fill-opacity="0.18"/>')
        ghost = float(panel.get("ghost") or 0)
        g = f' opacity="{max(0.2, 1 - ghost):g}"' if ghost > 0.01 else ""
        out.append(f'<g transform="translate(540,1000) scale(1.25)"{g}>{prop_svg(str(panel.get("prop") or ""), str(panel.get("prop_label") or ""))}</g>')
        return "".join(out)
    chars = [c for c in (panel.get("chars") or []) if isinstance(c, dict)][:5]
    crowd = int(panel.get("crowd") or 0)
    sc, foot, gap = FRAMINGS[frame]
    rng = random.Random(seed * 7 + 3)
    if frame == "wide" and crowd:
        # figurants derrière, plus petits
        n_back = min(8, crowd)
        for i, x in enumerate(_slots(n_back, 128)):
            fake = {"skin": rng.choice(SKINS), "hair": rng.choice(HAIRS), "top": rng.choice(TOPS), "cap": rng.choice(CAPS) if rng.random() < 0.7 else None,
                    "hair_style": rng.choice(HAIR_STYLES[:6]), "top_style": rng.choice(("hoodie", "tshirt", "vest", "stripes")), "glasses": rng.random() < 0.3}
            out.append(f'<g transform="translate({x:.0f},{foot - 120}) scale({sc * 0.72:.3f})">'
                       f'{character(fake, rng.choice(("neutral", "happy", "talk", "shocked")), rng.choice(("idle", "wave", "idle")), None)}</g>')
    n = len(chars)
    if frame == "close" and n > 1:
        chars = chars[:1]
        n = 1
    if frame == "medium" and n > 3:
        chars, n = chars[:3], 3
    if frame == "medium" and n == 3:
        sc, gap = 1.15, 300
    xs = _slots(n, gap)
    bubbles = []
    for i, (c, x) in enumerate(zip(chars, xs)):
        who = cast.get(str(c.get("id"))) or {}
        cnt = c.get("counter")
        cnt_txt = None
        if who.get("cap") and cnt not in (None, ""):
            unit = str(panel.get("_unit") or "").strip().lower()
            cnt_txt = f"{cnt} {unit}".strip()
        flip = x > 560 and c.get("pose") == "point"
        body = character(who, str(c.get("expr") or "neutral"), str(c.get("pose") or "idle"), cnt_txt,
                         ghost=float(c.get("ghost") or 0), flip=flip)
        out.append(f'<g transform="translate({x:.0f},{foot}) scale({sc:.3f})">{body}</g>')
        if c.get("say"):
            head_top = foot - 600 * sc
            bx = max(170, min(910, x + (90 if x <= 540 else -90)))
            by = max(330, head_top - 70)
            bubbles.append(bubble(bx, by, str(c["say"]), x, head_top + 40, 44 if frame != "close" else 52))
    out += bubbles
    return "".join(out)


def card_svg(card: Dict[str, Any], bg: Optional[str] = None) -> str:
    """Carton « règlement » : panneau crème, articles, l'article courant net, les autres pâles."""
    bgc = hexcol(bg, "#E2574C")
    title = str(card.get("title") or "")[:40]
    items = [i for i in (card.get("items") or []) if isinstance(i, (list, tuple, dict))][:4]
    hi = card.get("hi")
    out = [f'<rect width="{W}" height="{H}" fill="{bgc}"/>',
           f'<rect x="90" y="430" width="900" height="1300" rx="44" fill="#FFF8EC" {S(10)}/>']
    y = 560
    if title:
        out.append(text(540, y, title.upper(), fit_size(title, 760, 44), "#6B5B4B", 700))
        out.append(f'<path d="M200,{y + 30} L880,{y + 30}" stroke="#E6D6BE" stroke-width="5"/>')
        y += 120
    for k, it in enumerate(items):
        if isinstance(it, dict):
            head, body = str(it.get("head") or ""), str(it.get("text") or "")
        else:
            head, body = str(it[0]) if it else "", str(it[1]) if len(it) > 1 else ""
        faded = hi is not None and str(hi) != str(k)
        op = ' opacity="0.3"' if faded else ""
        out.append(f'<g{op}>' + text(540, y, head[:30], 78, INK, 700))
        yy = y + 70
        for line in wrap(body, 26)[:3]:
            out.append(text(540, yy, line, 46, "#4A4452", 500))
            yy += 58
        out.append("</g>")
        y = yy + 60
    if card.get("sign"):
        out.append(text(540, 1680, str(card["sign"])[:30], 36, "#8A7A6A", 500))
    return "".join(out)


def choices_svg(ch: Dict[str, Any]) -> str:
    """Carton final « Et toi ? » : fond nuit, grande question, 2 ou 3 choix (objet + mot) pour faire commenter."""
    title = str(ch.get("title") or "ET TOI ?").upper()[:20]
    items = [i for i in (ch.get("items") or []) if isinstance(i, dict)][:3]
    accent = hexcol(ch.get("accent"), "#FFD23F")
    out = [f'<rect width="{W}" height="{H}" fill="#1E1B3A"/>',
           f'<circle cx="540" cy="980" r="620" fill="#2A2550"/>']
    out.append(text(540, 520, title, fit_size(title, 900, 150, 0.6), accent, 700, stroke=INK, sw=14))
    xs = _slots(len(items), 330) if items else []
    for it, x in zip(items, xs):
        out.append(f'<g transform="translate({x:.0f},1180) scale(0.5)">{prop_svg(str(it.get("prop") or ""), "")}</g>')
        lab = str(it.get("label") or "").upper()[:12]
        if lab:
            out.append(text(x, 1400, lab, fit_size(lab, 300, 46, 0.6), accent, 700))
    return "".join(out)


def chapter_svg(chapter: str, accent: str = "#FFFFFF") -> str:
    """Bandeau de chapitre en haut (Parabole) : pastille sombre « N°1 : … » (fond transparent)."""
    t = str(chapter or "").upper()[:30]
    if not t:
        return ""
    fs = fit_size(t, 820, 50, 0.62)
    w = len(t) * fs * 0.62 + 90
    return (f'<rect x="{540 - w / 2:g}" y="230" width="{w:g}" height="86" rx="43" fill="{INK}" stroke="{hexcol(accent, "#FFFFFF")}" stroke-width="5"/>'
            + text(540, 230 + 43 + fs * 0.36, t, fs, "#FFFFFF", 700))


def header_svg(header: Dict[str, Any], counter: Any = None) -> str:
    """En-tête fixe (fond transparent) : titre, sous-titre, pastille compteur."""
    title = str(header.get("title") or "").upper()[:34]
    sub = str(header.get("subtitle") or "").upper()[:46]
    label = str(header.get("counter_label") or "").upper()[:22]
    unit = str(header.get("counter_unit") or "").upper()[:8]
    sub_col = hexcol(header.get("accent"), PINK)
    out = []
    if title:
        out.append(text(540, 196, title, fit_size(title, 1010, 92, 0.6), "#FFFFFF", 700, stroke=INK, sw=16))
    if sub:
        out.append(text(540, 262, sub, fit_size(sub, 900, 40, 0.6), sub_col, 700, stroke=INK, sw=10))
    if label and counter not in (None, ""):
        pill = f"{label} : {counter} {unit}".strip()
        fs = fit_size(pill, 640, 42, 0.62)
        w = len(pill) * fs * 0.62 + 70
        out.append(f'<rect x="{540 - w / 2:g}" y="292" width="{w:g}" height="66" rx="33" fill="{hexcol(header.get("pill"), INK)}" stroke="#FFFFFF" stroke-width="4"/>')
        out.append(text(540, 292 + 33 + fs * 0.36, pill, fs, "#FFFFFF", 700))
    return "".join(out)


def wrap_svg(inner: str, transparent: bool = False) -> str:
    bg = "" if transparent else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{bg}{inner}</svg>')
