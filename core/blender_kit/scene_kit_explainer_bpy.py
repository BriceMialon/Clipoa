# -*- coding: utf-8 -*-
# Style « Explainer 2D » (dessin animé illustré chaleureux, vue de face — réf. vidéos @rosoai) — exécuté DANS Blender.
# Contours épais brun foncé sur tout, décors intérieurs détaillés (bibliothèque, fenêtre, lambris, parquet),
# héros chibi dessinés par paper2d_bpy.py (placé avant ce fichier par BlenderEngine).
# Caméra orthographique de face, éclairage plat, contours fins foncés : chaque lieu est un « panneau »
# (ciel, soleil, nuages, collines, sol, décor) et la caméra glisse latéralement d'un panneau à l'autre.
import bpy
import math
import random
from mathutils import Vector

random.seed(SEED)
scene = bpy.context.scene
_sh = scene.display.shading
for _attr, _val in (("light", "FLAT"), ("color_type", "MATERIAL"), ("show_shadows", False), ("show_cavity", False),
                    ("show_object_outline", True), ("object_outline_color", (0.23, 0.16, 0.12)), ("show_specular_highlight", False)):
    try:
        setattr(_sh, _attr, _val)
    except Exception:
        pass
try:
    scene.display.render_aa = "11"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
except Exception:
    pass


def hex_rgba(h, default=(0.5, 0.5, 0.5, 1.0)):
    try:
        h = str(h).lstrip("#")
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0, 1.0)
    except Exception:
        return default


_M = {}


def _lin(c):
    # couleurs données en sRGB (comme un code #hex) -> linéaire attendu par Blender
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def mat(rgba):
    k = tuple(round(c, 3) for c in rgba)
    if k not in _M:
        m = bpy.data.materials.new("E%d" % len(_M))
        m.diffuse_color = (_lin(rgba[0]), _lin(rgba[1]), _lin(rgba[2]), rgba[3])
        _M[k] = m
    return _M[k]


INK_E = (0.23, 0.16, 0.12, 1.0)   # contour brun foncé #3B2A20 des références
T_INK = 0.07


def rect(x, z, w, h, col, y=0.0, d=0.1, parent=None, ink=True):
    if ink and w < 20 and h < 20:
        _rect(x, z, w + 2 * T_INK, h + 2 * T_INK, INK_E, y + d / 2 + 0.04, d * 0.5, parent)
    return _rect(x, z, w, h, col, y, d, parent)


def _rect(x, z, w, h, col, y=0.0, d=0.1, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.scale = (w, d, h)
    o.data.materials.append(mat(col))
    if parent is not None:
        o.parent = parent
    return o


def disc(x, z, r, col, y=0.0, verts=32, parent=None, sz=1.0, ink=True):
    if ink and r < 10:
        _disc(x, z, r + T_INK, INK_E, y + 0.05, verts, parent, sz)
    return _disc(x, z, r, col, y, verts, parent, sz)


def _disc(x, z, r, col, y=0.0, verts=32, parent=None, sz=1.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=0.08, location=(x, y, z), rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object
    o.scale = (1.0, 1.0 * sz, 1.0)
    o.data.materials.append(mat(col))
    if parent is not None:
        o.parent = parent
    return o


def tri(x, z, w, h, col, y=0.0, ink=True):
    if ink:
        tri(x, z, w + 0.26, h + 0.16, INK_E, y + 0.05, ink=False)
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=w / 1.7, depth=0.08, location=(x, y, z), rotation=(math.radians(90), math.radians(30), 0))
    o = bpy.context.active_object
    o.scale = (1.0, h / (w / 1.7) / 1.5, 1.0)
    o.data.materials.append(mat(col))
    return o


def label(body, x, z, size, col, y=-0.3):
    cu = bpy.data.curves.new(type="FONT", name="L")
    cu.body = str(body)[:24]
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("L", cu)
    scene.collection.objects.link(o)
    o.location = (x, y, z)
    o.rotation_euler = (math.radians(90), 0, 0)
    o.data.materials.append(mat(col))
    return o


PAL = SPEC.get("palette", {})
SKY = hex_rgba(PAL.get("sky"), (0.78, 0.89, 0.96, 1.0))
GROUND = hex_rgba(PAL.get("ground"), (0.86, 0.72, 0.5, 1.0))
ACCENT = hex_rgba(PAL.get("accent"), (0.85, 0.33, 0.31, 1.0))
TOD = SPEC.get("time_of_day", "day")
WOOD = (0.79, 0.54, 0.29, 1.0)
WOOD_D = (0.62, 0.4, 0.22, 1.0)
SLATE = (0.31, 0.43, 0.56, 1.0)
CREAM = (1.0, 0.96, 0.86, 1.0)
SAGE = (0.62, 0.74, 0.62, 1.0)
SAGE_D = (0.48, 0.62, 0.5, 1.0)
NAVY = (0.12, 0.13, 0.2, 1.0)
WHITE = (0.99, 0.99, 0.99, 1.0)
SUN = (0.99, 0.82, 0.35, 1.0)
world = bpy.data.worlds.new("W")
scene.world = world
world.color = tuple(_lin(c) for c in SKY[:3])

PANEL_W = 40.0
INDOOR = ("house", "room", "school", "shop", "office", "hospital", "stage")
LOC_X = {}


def outdoor_panel(ox, t, sign):
    rect(ox, 7, 30, 22, SKY, y=24, d=0.1)
    s = disc(ox + 2.6, 12.6, 0.7, SUN, y=20)
    for k in range(8):
        a = k * math.pi / 4
        rect(ox + 2.6 + math.cos(a) * 1.15, 12.6 + math.sin(a) * 1.15, 0.08, 0.35, (0.95, 0.45, 0.55, 1.0), y=20, ink=False).rotation_euler = (0, -a + math.pi / 2, 0)
    for cx, cz in ((-2.8, 12.2), (1.0, 10.6)):
        for dx, r in ((-0.35, 0.35), (0.1, 0.48), (0.55, 0.33)):
            disc(ox + cx + dx, cz + (0.08 if r > 0.4 else 0), r, WHITE, y=19)
    # collines
    for hx, hr in ((-4, 5.5), (2.5, 6.5), (8, 5)):
        disc(ox + hx, 1.6, hr, SAGE if hx != 2.5 else SAGE_D, y=16, sz=1.0)
    if t in ("city", "vertical_city", "market"):
        for k in range(7):
            h = random.uniform(3, 7)
            rect(ox - 6 + k * 2.0, 2.5 + h / 2, 1.8, h, (0.8, 0.85, 0.8, 1.0), y=14)
    if t in ("village", "street", "field", "park", "forest"):
        for k in range(2 if t != "forest" else 5):
            tx = ox + random.choice([-1, 1]) * random.uniform(2.5, 4.0)
            rect(tx, 3.6, 0.25, 1.6, (0.45, 0.33, 0.22, 1.0), y=8)
            disc(tx, 4.9, 0.9, (0.48, 0.66, 0.42, 1.0), y=7.9)
        hx = ox + random.uniform(-1.5, 1.5)
        rect(hx, 3.9, 1.6, 1.3, (0.97, 0.94, 0.88, 1.0), y=12)
        tri(hx, 4.9, 1.9, 0.8, (0.78, 0.38, 0.3, 1.0), y=12)
    # sol
    rect(ox, -2.5, 30, 10, GROUND, y=6, ink=False)
    rect(ox, 2.5, 30, 0.1, INK_E, y=5.95, ink=False)
    if t in ("street", "village"):
        rect(ox, 2.0, 30, 0.9, (0.55, 0.55, 0.58, 1.0), y=5.5)
        for k in range(-6, 7):
            rect(ox + k * 1.6, 2.0, 0.7, 0.08, WHITE, y=5.3)
    if t == "beach":
        rect(ox, 2.2, 30, 1.4, (0.45, 0.7, 0.9, 1.0), y=5.8)


def window(x, z, w=2.4, h=2.6):
    """Fenêtre à croisillons + rideaux, jour (ciel) ou nuit (bleu nuit + lune)."""
    night = TOD == "night"
    glass = (0.16, 0.22, 0.38, 1.0) if night else SKY
    rect(x, z, w + 0.3, h + 0.3, WOOD, y=20)
    rect(x, z, w, h, glass, y=19.9, ink=False)
    if night:
        disc(x + w * 0.25, z + h * 0.25, 0.22, (0.99, 0.96, 0.85, 1.0), y=19.85)
        for k in range(5):
            disc(x + random.uniform(-w / 2.4, w / 2.4), z + random.uniform(-h / 2.6, h / 2.6), 0.03, WHITE, y=19.86, ink=False)
    rect(x, z, 0.1, h, WOOD, y=19.8, ink=False)
    rect(x, z, w, 0.1, WOOD, y=19.8, ink=False)
    for sx in (-1, 1):
        rect(x + sx * (w / 2 + 0.35), z + 0.1, 0.55, h + 0.6, ACCENT if not night else SLATE, y=19.6)
    rect(x, z - h / 2 - 0.25, w + 0.7, 0.2, WOOD_D, y=19.5)


def bookshelf(x, z0=2.6, w=2.4, h=5.0, rows=4):
    rect(x, z0 + h / 2, w, h, WOOD_D, y=19)
    rect(x, z0 + h / 2, w - 0.3, h - 0.3, (0.42, 0.27, 0.16, 1.0), y=18.9, ink=False)
    cols = [(0.85, 0.33, 0.31, 1.0), (0.31, 0.43, 0.56, 1.0), (0.25, 0.5, 0.37, 1.0), (0.95, 0.75, 0.3, 1.0), (0.93, 0.9, 0.82, 1.0), (0.55, 0.36, 0.55, 1.0)]
    for rI in range(rows):
        zb = z0 + 0.15 + rI * (h - 0.3) / rows
        rect(x, zb, w - 0.2, 0.1, WOOD, y=18.7, ink=False)
        bx = x - w / 2 + 0.25
        while bx < x + w / 2 - 0.35:
            bw = random.uniform(0.12, 0.22)
            bh = random.uniform(0.55, 0.85) * (h - 0.3) / rows
            rect(bx + bw / 2, zb + 0.05 + bh / 2, bw, bh, random.choice(cols), y=18.6)
            bx += bw + 0.05


def jar_shelf(x, z):
    rect(x, z, 2.6, 0.14, WOOD, y=18.8)
    for k in range(3):
        jx = x - 0.85 + k * 0.85
        rect(jx, z + 0.42, 0.5, 0.62, CREAM, y=18.7)
        rect(jx, z + 0.45, 0.32, 0.22, random.choice([(0.95, 0.75, 0.3, 1.0), (0.85, 0.33, 0.31, 1.0), (0.25, 0.5, 0.37, 1.0)]), y=18.6, ink=False)
        rect(jx, z + 0.8, 0.56, 0.14, random.choice([ACCENT, SLATE, (0.25, 0.5, 0.37, 1.0)]), y=18.65)


def indoor_panel(ox, t, sign):
    wall = {"shop": (0.97, 0.9, 0.76, 1.0), "office": (0.93, 0.87, 0.74, 1.0), "school": (0.96, 0.9, 0.72, 1.0),
            "hospital": (0.86, 0.94, 0.9, 1.0)}.get(t, (0.96, 0.89, 0.71, 1.0))
    rect(ox, 7, 30, 22, wall, y=24, ink=False)
    # lambris + plinthe + parquet à lattes (intérieurs cosy des références)
    rect(ox, 3.4, 30, 1.8, tuple(c * 0.86 for c in wall[:3]) + (1.0,), y=23, ink=False)
    rect(ox, 4.35, 30, 0.14, WOOD, y=22.9, ink=False)
    rect(ox, 2.65, 30, 0.3, WOOD_D, y=22.8, ink=False)
    rect(ox, -2.5, 30, 10, WOOD, y=6, ink=False)
    rect(ox, 2.5, 30, 0.1, INK_E, y=5.95, ink=False)
    for k in range(-12, 13):
        rect(ox + k * 1.25, -2.5, 0.04, 10, WOOD_D, y=5.9, ink=False)
    window(ox - 2.0, 7.2)
    if t in ("house", "room"):
        bookshelf(ox + 2.4, w=2.2, h=4.6)
        rect(ox - 2.0, 10.0, 1.4, 1.0, WOOD_D, y=20)  # cadre
        rect(ox - 2.0, 10.0, 1.1, 0.7, (0.55, 0.72, 0.85, 1.0), y=19.9, ink=False)
        rect(ox - 3.6, 3.1, 1.6, 1.3, (0.75, 0.32, 0.3, 1.0), y=10)  # fauteuil
        rect(ox - 3.6, 4.1, 1.6, 1.0, (0.68, 0.28, 0.27, 1.0), y=10.2)
    elif t in ("office", "school"):
        bookshelf(ox + 2.4, w=2.4, h=5.4, rows=5)
        rect(ox, 2.0, 4.6, 0.3, WOOD, y=8)  # bureau
        rect(ox, 1.0, 4.4, 1.8, WOOD_D, y=8.1)
        rect(ox + 1.3, 2.55, 0.18, 0.6, CREAM, y=7.9)  # bougie
        disc(ox + 1.3, 3.0, 0.1, (1.0, 0.8, 0.3, 1.0), y=7.85)
        rect(ox - 1.2, 2.25, 1.2, 0.08, CREAM, y=7.9)  # feuille
        if t == "school":
            rect(ox - 2.0, 10.4, 4.0, 1.8, (0.2, 0.36, 0.28, 1.0), y=19)
    elif t in ("shop",):
        # carrelage + étagère à bocaux + comptoir (cuisine / boutique)
        for kx in range(-6, 7):
            for kz in range(0, 3):
                rect(ox + kx * 0.6, 4.75 + kz * 0.6, 0.56, 0.56, (0.97, 0.97, 0.95, 1.0), y=22.5, ink=False)
        jar_shelf(ox + 2.3, 7.0)
        rect(ox, 1.7, 7, 1.6, SLATE, y=4)
        rect(ox, 2.6, 7.2, 0.25, WOOD, y=3.9)
        for kx in (-2.3, 0.0, 2.3):
            rect(ox + kx, 1.6, 2.0, 1.2, (0.36, 0.5, 0.64, 1.0), y=3.9)
            rect(ox + kx, 2.0, 0.5, 0.08, (0.95, 0.75, 0.3, 1.0), y=3.85, ink=False)
    elif t == "hospital":
        rect(ox + 2.2, 3.0, 2.6, 0.9, WHITE, y=10)


def storefront(ox, sign):
    rect(ox, 5.0, 6.5, 6.5, WHITE, y=10)
    for k in range(3):
        rect(ox - 2 + 2 * k, 7.4, 1.2, 0.9, SKY, y=9.9)
    rect(ox, 5.8, 4.6, 0.8, NAVY, y=9.8)
    if sign:
        label(sign.upper(), ox, 5.8, 0.42, WHITE, y=9.6)
    for k in range(6):
        rect(ox - 2.7 + k * 1.08, 4.7, 1.08, 0.7, ACCENT if k % 2 == 0 else WHITE, y=9.5)
    rect(ox - 1.2, 3.0, 2.6, 2.6, SKY, y=9.9)


def flat_prop(kind, x, col=None, text=""):
    """Objets dessinés à plat (vue de face), posés sur le sol du panneau, derrière les personnages."""
    c = hex_rgba(col, None) if col else None
    wood = (0.62, 0.42, 0.28, 1.0)
    y = 4.0
    if kind in ("sign", "price_sign", "stock_screen", "subscribe"):
        rect(x, 2.6, 0.12, 2.2, wood, y=y + 0.2)
        rect(x, 4.0, 2.4, 1.2, c or (WHITE if kind != "stock_screen" else NAVY), y=y)
        if text:
            label(text.upper(), x, 4.0, 0.32, NAVY if kind != "stock_screen" else (0.95, 0.4, 0.45, 1.0), y=y - 0.12)
    elif kind in ("box", "coins"):
        for k in range(2 if kind == "box" else 4):
            if kind == "box":
                rect(x + k * 0.9, 2.0, 0.8, 0.7, c or (0.82, 0.62, 0.38, 1.0), y=y)
            else:
                disc(x + k * 0.3, 1.8 + 0.12 * k, 0.22, SUN, y=y - 0.1 * k)
    elif kind in ("table", "desk"):
        rect(x, 2.4, 2.4, 0.15, c or wood, y=y)
        rect(x - 1.0, 1.7, 0.12, 1.3, c or wood, y=y)
        rect(x + 1.0, 1.7, 0.12, 1.3, c or wood, y=y)
    elif kind == "shelf":
        for row in (5.2, 6.4):
            rect(x, row, 2.6, 0.12, wood, y=y + 2)
            for k in range(3):
                disc(x - 0.8 + k * 0.8, row + 0.3, 0.22, c or ACCENT, y=y + 1.9)
    elif kind == "door":
        rect(x, 2.6, 1.3, 2.6, c or (0.55, 0.38, 0.25, 1.0), y=y + 1)
        disc(x + 0.4, 2.6, 0.07, SUN, y=y + 0.9)
    elif kind == "fridge":
        rect(x, 2.4, 1.1, 2.6, c or (0.93, 0.95, 0.97, 1.0), y=y)
        rect(x + 0.35, 2.9, 0.06, 0.6, NAVY, y=y - 0.1)
    elif kind in ("lamp",):
        rect(x, 3.0, 0.08, 3.4, NAVY, y=y)
        tri(x, 4.9, 0.9, 0.6, SUN, y=y)
    elif kind in ("tree", "pine"):
        rect(x, 2.4, 0.25, 1.8, (0.45, 0.33, 0.22, 1.0), y=y)
        disc(x, 3.9, 0.95, c or (0.48, 0.66, 0.42, 1.0), y=y - 0.1)
    elif kind in ("house", "townhall", "market", "castle"):
        rect(x, 2.8, 2.2, 1.9, c or (0.97, 0.94, 0.88, 1.0), y=y + 3)
        tri(x, 4.2, 2.6, 1.0, (0.78, 0.38, 0.3, 1.0), y=y + 3)
    elif kind == "car":
        rect(x, 1.9, 2.4, 0.8, c or ACCENT, y=y)
        rect(x, 2.5, 1.4, 0.6, SKY, y=y + 0.05)
        disc(x - 0.7, 1.45, 0.3, NAVY, y=y - 0.1)
        disc(x + 0.7, 1.45, 0.3, NAVY, y=y - 0.1)
    elif kind == "bench":
        rect(x, 1.9, 2.2, 0.15, c or wood, y=y)
        rect(x, 2.5, 2.2, 0.12, c or wood, y=y + 0.1)
    elif kind == "bed":
        rect(x, 1.8, 2.8, 0.7, c or (0.72, 0.8, 0.92, 1.0), y=y)
        rect(x - 1.0, 2.3, 0.8, 0.35, WHITE, y=y - 0.1)
    elif kind in ("tv", "monitor"):
        rect(x, 3.2, 1.8, 1.1, NAVY, y=y)
    elif kind == "moon":
        disc(x + 2.5, 12.0, 0.8, (0.97, 0.95, 0.85, 1.0), y=19)
    # autres objets : ignorés (le décor du panneau suffit)


PROP_SLOTS = [-3.2, 3.2, -1.9, 2.0, -4.0, 4.0]

for li, L in enumerate(SPEC.get("locations", [])):
    ox = li * PANEL_W
    LOC_X[L["id"]] = ox
    t = L.get("type", "village")
    if t in INDOOR:
        indoor_panel(ox, t, L.get("sign_text"))
    else:
        outdoor_panel(ox, t, L.get("sign_text"))
        if t in ("shop", "market") or L.get("sign_text"):
            storefront(ox + 0.5, L.get("sign_text") or "")
    if t in INDOOR and L.get("sign_text"):
        rect(ox + 1.0, 10.2, 4.0, 0.9, NAVY, y=18)
        label(L["sign_text"].upper(), ox + 1.0, 10.2, 0.45, WHITE, y=17.8)
    slot = 0
    for P in (L.get("props") or [])[:6]:
        if P.get("kind") in ("mountain", "star"):
            continue
        flat_prop(P.get("kind", "box"), ox + PROP_SLOTS[slot % len(PROP_SLOTS)], P.get("color"), P.get("text", ""))
        slot += 1


CHARS = {c["id"]: c for c in SPEC.get("characters", [])}
FACE_INFO = {}
# héros chibi des références : grosse tête, grands yeux à pupille brune, nez, joues roses, contour brun
P2_CHIBI = True
P2_INK = INK_E
P2_SKIN = (0.97, 0.83, 0.71, 1.0)
P2_SKIN_MIX = 0.0
P2_LINE = 0.055


def make_char(cid, x, z0=1.0, y=2.0):
    return make_char_2d(cid, (x, y, z0))


def animate(parts, action, f0, f1):
    root, al, ar, ll, lr = parts
    base = root.location.copy()
    if action in ("point", "idle"):
        ar.rotation_euler = (0, math.radians(-60 if action == "point" else -8), 0)
        ar.keyframe_insert("rotation_euler", frame=f0)
        if action == "idle":
            for k, f in enumerate(range(f0, f1 + 1, 6)):
                ar.rotation_euler = (0, math.radians(-8 if k % 2 else 4), 0)
                ar.keyframe_insert("rotation_euler", frame=f)
        ar.rotation_euler = (0, 0, 0)
        ar.keyframe_insert("rotation_euler", frame=f1 + 1)
    elif action in ("walk", "run"):
        root.location = base + Vector((-0.8, 0, 0))
        root.keyframe_insert("location", frame=f0)
        root.location = base + Vector((0.8, 0, 0))
        root.keyframe_insert("location", frame=f1)
        root.location = base
        root.keyframe_insert("location", frame=f1 + 1)
        for k, f in enumerate(range(f0, f1 + 1, 3)):
            for o, sg in ((ll, 1), (lr, -1)):
                o.rotation_euler = (0, 0.35 * sg * (1 if k % 2 == 0 else -1), 0)
                o.keyframe_insert("rotation_euler", frame=f)
    elif action == "jump":
        for k, f in enumerate(range(f0, f1 + 1, 3)):
            root.location = base + Vector((0, 0, 0.6 if k % 2 else 0.0))
            root.keyframe_insert("location", frame=f)
        root.location = base
        root.keyframe_insert("location", frame=f1 + 1)
    else:  # wave (salut) par défaut pour sit/fall
        for k, f in enumerate(range(f0, f1 + 1, 4)):
            ar.rotation_euler = (0, math.radians(-150 if k % 2 else -120), 0)
            ar.keyframe_insert("rotation_euler", frame=f)
        ar.rotation_euler = (0, 0, 0)
        ar.keyframe_insert("rotation_euler", frame=f1 + 1)


cam_d = bpy.data.cameras.new("Cam")
cam_d.type = "ORTHO"
cam = bpy.data.objects.new("Cam", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0)
FRAMING = {"drone": (17.0, 6.8), "wide": (15.0, 6.2), "tilt": (15.0, 6.2), "medium": (10.0, 3.6), "low": (10.0, 3.6),
           "close": (6.0, 3.3), "pov": (10.0, 3.6), "face": (4.6, 3.55), "back": (10.0, 3.6), "high": (15.0, 6.2)}
SPOTS = [0.0, -2.0, 2.0, -3.8, 3.8]
placed = {}
prev_loc = None


def _show_holder(name, before, pivot):
    """Regroupe les objets créés pour un « show » sous un pivot qu'on peut faire apparaître / disparaître."""
    bpy.context.view_layer.update()
    holder = bpy.data.objects.new(name, None)
    scene.collection.objects.link(holder)
    holder.location = pivot
    bpy.context.view_layer.update()
    inv = holder.matrix_world.inverted()
    for o in list(scene.objects):
        if o.name in before or o.parent is not None or o is holder:
            continue
        mw = o.matrix_world.copy()
        o.parent = holder
        o.matrix_parent_inverse = inv
        o.matrix_world = mw
    return holder


def _show_pop(holder, f0, f1):
    """Le « show » surgit au début de la phrase (petit rebond) et disparaît à la coupe."""
    for fr, sc in ((0, 0.0), (max(1, f0 - 1), 0.0), (f0 + 2, 1.15), (f0 + 4, 1.0), (max(f0 + 5, f1), 1.0), (f1 + 1, 0.0)):
        holder.scale = (sc, sc, sc)
        holder.keyframe_insert("scale", frame=fr)


def show_item(sh, x, f0, f1, idx):
    """Ce que dit la phrase, montré pendant le plan : objet dessiné à côté du héros ou carton-mot crème qui surgit."""
    side = 1 if idx % 2 == 0 else -1
    before = set(o.name for o in scene.objects)
    kind = str(sh.get("kind") or "")
    txt = str(sh.get("text") or "")
    if kind == "text" or kind not in ("sign", "price_sign", "stock_screen", "subscribe", "box", "coins", "table", "desk", "shelf", "door",
                                      "fridge", "lamp", "tree", "pine", "house", "townhall", "market", "castle", "car", "bench", "bed", "tv", "monitor"):
        w = max(1.6, 0.34 * len(txt or "!") + 0.6)
        rect(x, 5.7, w, 1.0, CREAM, y=1.2)
        label(txt or "!", x, 5.7, 0.5, hex_rgba(sh.get("color"), INK_E), y=1.05)
        pivot = Vector((x, 1.1, 5.7))
    else:
        flat_prop(kind, x + side * 2.2, sh.get("color"), txt)
        pivot = Vector((x + side * 2.2, 4.0, 2.4))
    holder = _show_holder("Show_%d" % idx, before, pivot)
    if kind != "text":
        holder.location.y -= 2.6  # devant le décor, juste derrière le héros
    _show_pop(holder, f0, f1)


for si, S in enumerate(SHOTS):
    f0, f1 = int(S["f0"]), int(S["f1"])
    ox = LOC_X.get(S.get("location"), 0.0)
    who = [w for w in ([S.get("focus")] + list(S.get("others") or [])) if w in CHARS][:4]
    fx = ox
    for k, cid in enumerate(who):
        key = (S.get("location"), cid)
        if key not in placed:
            n = len([1 for kk in placed if kk[0] == S.get("location")])
            placed[key] = make_char(cid, ox + SPOTS[n % len(SPOTS)])
        parts = placed[key]
        emo = S.get("emotion") or "neutral"
        if k == 0:
            fx = parts[0].location.x
            animate(parts, S.get("action", "idle"), f0, f1)
            p2_set_emotion(parts[0], emo, f0)
        else:
            animate(parts, "idle", f0, f1)
            p2_set_emotion(parts[0], emo if emo in ("happy", "sad", "surprised") else "neutral", f0)
    scale, cz = FRAMING.get(S.get("camera"), FRAMING["medium"])
    cx = fx if scale < 14 else ox
    # glissé latéral rapide (whip-pan) quand on change de lieu, coupe nette sinon
    if prev_loc is not None and prev_loc != S.get("location") and f0 > 4:
        cam.keyframe_insert("location", frame=f0 - 3)
        cam_d.keyframe_insert("ortho_scale", frame=f0 - 3)
    cam.location = (cx, -40.0, cz)
    cam_d.ortho_scale = scale
    cam.keyframe_insert("location", frame=f0)
    cam_d.keyframe_insert("ortho_scale", frame=f0)
    cam.location = (cx, -40.0, cz)
    cam_d.ortho_scale = scale * 0.94  # léger zoom avant pendant le plan
    cam.keyframe_insert("location", frame=max(f0 + 1, f1 - 1))
    cam_d.keyframe_insert("ortho_scale", frame=max(f0 + 1, f1 - 1))
    prev_loc = S.get("location")
    if S.get("show"):
        try:
            show_item(S["show"], fx, f0, f1, si)
        except Exception as _e:
            print("show:", _e)
