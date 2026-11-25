# -*- coding: utf-8 -*-
# Style « Explainer 2D » (dessin animé vectoriel pastel, vue de face) — exécuté DANS Blender.
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
                    ("show_object_outline", True), ("object_outline_color", (0.12, 0.13, 0.2)), ("show_specular_highlight", False)):
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


def rect(x, z, w, h, col, y=0.0, d=0.1, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    o = bpy.context.active_object
    o.scale = (w, d, h)
    o.data.materials.append(mat(col))
    if parent is not None:
        o.parent = parent
    return o


def disc(x, z, r, col, y=0.0, verts=32, parent=None, sz=1.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=0.08, location=(x, y, z), rotation=(math.radians(90), 0, 0))
    o = bpy.context.active_object
    o.scale = (1.0, 1.0 * sz, 1.0)
    o.data.materials.append(mat(col))
    if parent is not None:
        o.parent = parent
    return o


def tri(x, z, w, h, col, y=0.0):
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
SKY = hex_rgba(PAL.get("sky"), (0.86, 0.92, 0.96, 1.0))
GROUND = hex_rgba(PAL.get("ground"), (0.86, 0.76, 0.6, 1.0))
ACCENT = hex_rgba(PAL.get("accent"), (0.86, 0.25, 0.42, 1.0))
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
        rect(ox + 2.6 + math.cos(a) * 1.15, 12.6 + math.sin(a) * 1.15, 0.08, 0.35, (0.95, 0.45, 0.55, 1.0), y=20).rotation_euler = (0, -a + math.pi / 2, 0)
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
    rect(ox, -2.5, 30, 10, GROUND, y=6)
    if t in ("street", "village"):
        rect(ox, 2.0, 30, 0.9, (0.55, 0.55, 0.58, 1.0), y=5.5)
        for k in range(-6, 7):
            rect(ox + k * 1.6, 2.0, 0.7, 0.08, WHITE, y=5.3)
    if t == "beach":
        rect(ox, 2.2, 30, 1.4, (0.45, 0.7, 0.9, 1.0), y=5.8)


def indoor_panel(ox, t, sign):
    wall = {"shop": (0.97, 0.88, 0.9, 1.0), "office": (0.9, 0.92, 0.95, 1.0), "school": (0.98, 0.94, 0.82, 1.0),
            "hospital": (0.86, 0.94, 0.9, 1.0)}.get(t, (0.98, 0.88, 0.9, 1.0))
    rect(ox, 7, 30, 22, wall, y=24)
    rect(ox, -2.5, 30, 10, (0.82, 0.62, 0.45, 1.0), y=6)
    # fenêtre
    rect(ox - 2.2, 8.0, 2.4, 2.4, WHITE, y=20)
    rect(ox - 2.2, 8.0, 2.2, 2.2, SKY, y=19.9)
    rect(ox - 2.2, 8.0, 0.08, 2.2, WHITE, y=19.8)
    rect(ox - 2.2, 8.0, 2.2, 0.08, WHITE, y=19.8)
    if t in ("house", "room"):
        rect(ox + 1.0, 3.1, 4.2, 1.3, (0.55, 0.68, 0.55, 1.0), y=10)  # canapé
        rect(ox + 1.0, 4.2, 4.2, 1.2, (0.5, 0.63, 0.5, 1.0), y=10.2)
        rect(ox + 3.6, 4.4, 0.08, 3.2, NAVY, y=11)  # lampe
        tri(ox + 3.6, 6.2, 0.9, 0.7, SUN, y=11)
    elif t == "shop":
        rect(ox, 2.0, 7, 1.8, (0.62, 0.42, 0.28, 1.0), y=4)  # comptoir
        for row in (7.0, 9.0):
            rect(ox + 2.5, row - 0.35, 3.4, 0.12, (0.62, 0.42, 0.28, 1.0), y=18)
            for k in range(4):
                disc(ox + 1.2 + k * 0.85, row + 0.05, 0.25, ACCENT, y=17.9)
    elif t in ("office", "school"):
        rect(ox + 1.5, 2.6, 3.2, 0.15, (0.7, 0.55, 0.38, 1.0), y=8)
        rect(ox + 1.5, 3.4, 1.4, 0.9, NAVY, y=8.1)
        if t == "school":
            rect(ox + 1.0, 8.4, 5, 2.6, (0.2, 0.36, 0.28, 1.0), y=19)


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


CHARS = {c["id"]: c for c in SPEC.get("characters", [])}
SKIN_TONES = [(0.98, 0.84, 0.72, 1.0), (0.84, 0.62, 0.45, 1.0), (0.5, 0.33, 0.22, 1.0)]


def make_char(cid, x, z0=1.0, y=2.0):
    c = CHARS.get(cid, {})
    root = bpy.data.objects.new("C_" + cid, None)
    scene.collection.objects.link(root)
    root.location = (x, y, z0)
    sc = float(c.get("scale", 1.0) or 1.0)
    root.scale = (sc, 1, sc)
    skin = hex_rgba(c.get("skin"), SKIN_TONES[hash(cid) % 3])
    shirt = hex_rgba(c.get("shirt"), WHITE)
    pants = hex_rgba(c.get("pants"), (0.3, 0.45, 0.35, 1.0))
    hair = hex_rgba(c.get("hair"), (0.25, 0.17, 0.12, 1.0))
    apron = hex_rgba(c.get("hat"), None) if c.get("hat") and c.get("hat") != "none" else None
    # jambes
    ll = rect(-0.22, 0.55, 0.3, 1.1, pants, parent=root)
    lr = rect(0.22, 0.55, 0.3, 1.1, pants, parent=root)
    rect(-0.22, 0.02, 0.38, 0.14, NAVY, parent=root)
    rect(0.22, 0.02, 0.38, 0.14, NAVY, parent=root)
    # torse (+ tablier / salopette en couleur d'accent)
    rect(0, 1.65, 0.95, 1.2, shirt, parent=root)
    if apron:
        rect(0, 1.45, 0.7, 0.95, apron, y=-0.06, parent=root)
    # bras articulés à l'épaule
    arms = []
    for sx in (-1, 1):
        piv = bpy.data.objects.new("Sh", None)
        scene.collection.objects.link(piv)
        piv.parent = root
        piv.location = (sx * 0.6, 0, 2.15)
        rect(0, -0.5, 0.24, 1.0, shirt, y=0.01, parent=piv)
        disc(0, -1.05, 0.14, skin, y=0.0, parent=piv)
        arms.append(piv)
    # tête ronde
    disc(0, 2.75, 0.5, skin, y=-0.02, parent=root)
    disc(0, 3.05, 0.52, hair, y=0.03, parent=root, sz=1.0)
    rect(0, 3.12, 1.0, 0.35, hair, y=0.02, parent=root)
    for sx in (-0.17, 0.17):
        disc(sx, 2.78, 0.06, NAVY, y=-0.08, parent=root)
        disc(sx * 1.6, 2.6, 0.08, (0.98, 0.6, 0.62, 1.0), y=-0.07, parent=root)
    rect(0, 2.55, 0.22, 0.05, NAVY, y=-0.08, parent=root)
    return root, arms[0], arms[1], ll, lr


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
                o.location = (o.location[0], o.location[1], 0.55 + (0.12 if (k % 2 == 0) == (sg > 0) else 0.0))
                o.keyframe_insert("location", frame=f)
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
           "close": (6.0, 3.2), "pov": (10.0, 3.6)}
SPOTS = [0.0, -1.7, 1.7, -3.2, 3.2]
placed = {}
prev_loc = None
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
        if k == 0:
            fx = parts[0].location.x
            animate(parts, S.get("action", "idle"), f0, f1)
        else:
            animate(parts, "idle", f0, f1)
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
