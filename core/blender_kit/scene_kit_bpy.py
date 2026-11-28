# -*- coding: utf-8 -*-
# Constructeur de scène Blender (exécuté DANS Blender). Lit SPEC (décor décrit en JSON pour CETTE vidéo)
# et SHOTS (plans calés sur la voix), puis construit lieux, objets, personnages et caméra multi-plans.
# Ne pas importer depuis ClipRoll : ce fichier est concaténé au script Blender par BlenderEngine.
import bpy
import math
import os
import random
from mathutils import Vector

random.seed(SEED)
scene = bpy.context.scene

# ---------------------------------------------------------------- rendu selon le style choisi
# roblox      : vrais modèles 3D en blocs (bibliothèque GLB), ombrage studio, ombres, contours
# paper2d     : personnages 2D plats « papier découpé » dans un décor 3D (DA 2D × Monde 3D)
# flat_vector : aplats de couleur saturés sans ombre (DA Fête en folie / motion design vectoriel)
STYLE = SPEC.get("_style", "roblox")
_sh = scene.display.shading
for _attr, _val in (
    ("light", "FLAT" if STYLE == "flat_vector" else "STUDIO"),
    ("color_type", "TEXTURE"),
    ("show_shadows", STYLE != "flat_vector"),
    ("show_cavity", STYLE == "roblox"),
    ("cavity_type", "BOTH"),
    ("show_object_outline", STYLE != "flat_vector"),
    ("show_specular_highlight", STYLE == "roblox"),
):
    try:
        setattr(_sh, _attr, _val)
    except Exception:
        pass
if STYLE == "roblox":
    for _attr, _val in (("shadow_intensity", 0.6), ("cavity_ridge_factor", 1.2), ("cavity_valley_factor", 1.5),
                        ("curvature_ridge_factor", 1.0), ("curvature_valley_factor", 0.9)):
        try:
            setattr(_sh, _attr, _val)
        except Exception:
            pass
    try:
        scene.display.light_direction = (0.45, -0.55, 0.70)
        scene.display.shadow_shift = 0.05
        scene.display.shadow_focus = 0.3
    except Exception:
        pass
if STYLE == "paper2d":
    # lumière douce de jour, ombres légères, relief du décor (les persos 2D restent plats)
    for _attr, _val in (("shadow_intensity", 0.4), ("show_cavity", True), ("cavity_type", "WORLD"),
                        ("cavity_ridge_factor", 0.6), ("cavity_valley_factor", 1.0), ("show_object_outline", False)):
        try:
            setattr(_sh, _attr, _val)
        except Exception:
            pass
    try:
        scene.display.light_direction = (0.35, -0.6, 0.72)
        scene.display.shadow_shift = 0.1
        scene.display.shadow_focus = 0.6
    except Exception:
        pass
    try:
        # les références sont claires et lumineuses : on relève l'exposition (persos blancs bien blancs)
        scene.view_settings.exposure = 0.8 if globals().get("P2_STICK") else 0.45
    except Exception:
        pass
try:
    scene.display.render_aa = "11"
except Exception:
    pass
try:
    # Couleurs franches (AgX/Filmic désature tout et rend les styles ternes)
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


_MATS = {}


CUR_TINT = None  # teinte appliquée aux objets du lieu en construction (nuit extérieure)


def _is_glow(rgba):
    r, g, b = rgba[:3]
    return r > 0.9 and g > 0.7 and b < 0.65  # fenêtres allumées, lampes : restent lumineuses la nuit


def mat(rgba, name=None):
    if rgba is None:
        rgba = (0.6, 0.6, 0.6, 1.0)
    if CUR_TINT and not _is_glow(rgba):
        rgba = (rgba[0] * CUR_TINT[0], rgba[1] * CUR_TINT[1], rgba[2] * CUR_TINT[2], rgba[3])
    if STYLE == "paper2d" and not _is_glow(rgba):
        # références : décor lisible et lumineux même la nuit (jamais de bouillie sombre)
        rgba = tuple(max(0.0, min(1.0, c)) ** 0.8 for c in rgba[:3]) + (rgba[3],)
    key = tuple(round(c, 3) for c in rgba)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name=name or ("M%d" % len(_MATS)))
    # couleurs données en sRGB (comme un code #hex) -> linéaire attendu par Blender
    m.diffuse_color = tuple((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in rgba[:3]) + (rgba[3],)
    try:
        m.roughness = 0.6
    except Exception:
        pass
    _MATS[key] = m
    return m


def box(loc, size, rgba, rot=(0, 0, 0), parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    o.data.materials.append(mat(rgba))
    if parent is not None:
        o.parent = parent
    return o


def cyl(loc, r, depth, rgba, verts=12, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.data.materials.append(mat(rgba))
    return o


def cone(loc, r, depth, rgba, verts=6):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, depth=depth, location=loc)
    o = bpy.context.active_object
    o.data.materials.append(mat(rgba))
    return o


def sphere(loc, r, rgba, seg=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=max(6, seg // 2), radius=r, location=loc)
    o = bpy.context.active_object
    for poly in o.data.polygons:
        poly.use_smooth = True
    o.data.materials.append(mat(rgba))
    return o


def text3d(body, loc, size, rgba, rot=(math.radians(90), 0, 0)):
    cu = bpy.data.curves.new(type="FONT", name="Txt")
    cu.body = str(body)[:28]
    cu.size = size
    cu.extrude = 0.02
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    o = bpy.data.objects.new("Txt", cu)
    scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat(rgba))
    return o


# ---------------------------------------------------------------- ambiance
TOD = SPEC.get("time_of_day", "day")
PAL = SPEC.get("palette", {})
SKY = hex_rgba(PAL.get("sky"), (0.30, 0.62, 0.98, 1.0) if TOD == "day" else ((0.95, 0.55, 0.35, 1.0) if TOD == "sunset" else (0.03, 0.05, 0.12, 1.0)))
GROUND = hex_rgba(PAL.get("ground"), (0.30, 0.68, 0.32, 1.0))
ACCENT = hex_rgba(PAL.get("accent"), (1.0, 0.85, 0.25, 1.0))
NIGHT = TOD == "night"
if STYLE == "paper2d" and NIGHT:
    SKY = tuple(SKY[i] * 0.5 + (0.30, 0.37, 0.55)[i] * 0.5 for i in range(3)) + (1.0,)
FLAT2D = STYLE in ("paper2d", "flat_vector")

world = bpy.data.worlds.new("ClipoaWorld")
scene.world = world
world.color = tuple((c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4) for c in SKY[:3])

sun_d = bpy.data.lights.new("Sun", type="SUN")
sun_d.energy = 1.6 if NIGHT else 3.0
sun_d.color = (0.65, 0.75, 1.0) if NIGHT else ((1.0, 0.8, 0.6) if TOD == "sunset" else (1.0, 0.97, 0.9))
sun_o = bpy.data.objects.new("Sun", sun_d)
scene.collection.objects.link(sun_o)
sun_o.rotation_euler = (math.radians(50), math.radians(12), math.radians(-35))

WIN_ON = (1.0, 0.82, 0.40, 1.0)
WIN_OFF = (0.10, 0.12, 0.16, 1.0)


# ---------------------------------------------------------------- bibliothèque de modèles 3D (GLB Docteur Shark)
_LIB = {}


def _world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    found = False
    for o in objs:
        if o.type != "MESH":
            continue
        for v in o.bound_box:
            w = o.matrix_world @ Vector(v)
            lo = Vector((min(lo.x, w.x), min(lo.y, w.y), min(lo.z, w.z)))
            hi = Vector((max(hi.x, w.x), max(hi.y, w.y), max(hi.z, w.z)))
            found = True
    return (lo, hi) if found else (Vector((0, 0, 0)), Vector((1, 1, 1)))


_DONE_IMAGES = set()


def _flatten_decals(objs):
    """
    Les visages / enseignes des GLB sont des autocollants à fond transparent. Workbench ne gère pas la
    transparence (fond noir) : on remplit le transparent avec la couleur de la pièce voisine (la tête).
    """
    try:
        import numpy as np
    except Exception:
        return
    for o in objs:
        if o.type != "MESH":
            continue
        for slot in o.material_slots:
            m = slot.material
            if not (m and m.use_nodes):
                continue
            img_nodes = [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
            if not img_nodes:
                continue
            img = img_nodes[0].image
            if img.name in _DONE_IMAGES:
                continue
            fill = None
            # la pièce DERRIÈRE l'autocollant (la tête, pas les cheveux) : sa boîte contient le centre du visage
            bpy.context.view_layer.update()
            dlo, dhi = _world_bbox([o])
            dc = (dlo + dhi) / 2
            best = None
            for sb in objs:
                if sb.type != "MESH" or sb is o:
                    continue
                if not any(sl.material and not any(n.type == "TEX_IMAGE" for n in (sl.material.node_tree.nodes if sl.material.use_nodes else [])) for sl in sb.material_slots):
                    continue
                lo, hi = _world_bbox([sb])
                if lo.x - 0.01 <= dc.x <= hi.x + 0.01 and lo.z - 0.01 <= dc.z <= hi.z + 0.01:
                    dist = min(abs(dc.y - lo.y), abs(dc.y - hi.y))
                    vol = (hi.x - lo.x) * (hi.y - lo.y) * (hi.z - lo.z)
                    key = (round(dist, 2), -vol)
                    if best is None or key < best[0]:
                        best = (key, sb)
            if best:
                for sl in best[1].material_slots:
                    if sl.material:
                        fill = tuple(sl.material.diffuse_color)[:3]
                        break
            if fill is None:
                fill = (0.93, 0.78, 0.62)
            try:
                w, h = img.size
                if not w or not h:
                    continue
                px = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)
                a = px[:, 3:4]
                # le fond reçoit la couleur voisine (dans l'espace de l'image, sRGB approx.)
                fc = np.array([c ** (1 / 2.2) for c in fill], dtype=np.float32)
                px[:, :3] = px[:, :3] * a + fc * (1.0 - a)
                px[:, 3] = 1.0
                img.pixels = px.ravel().tolist()
                img.update()
                _DONE_IMAGES.add(img.name)
            except Exception as e:
                print("decal flatten skipped", e)


def glb_template(rel):
    if rel in _LIB:
        return _LIB[rel]
    path = os.path.join(ASSET_DIR, rel) if ASSET_DIR else ""
    if not path or not os.path.exists(path):
        _LIB[rel] = None
        return None
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as e:
        print("GLB import failed", rel, e)
        _LIB[rel] = None
        return None
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if m and m.use_nodes:
                b = m.node_tree.nodes.get("Principled BSDF")
                if b:
                    try:
                        m.diffuse_color = tuple(b.inputs["Base Color"].default_value)
                    except Exception:
                        pass
    _flatten_decals(new)
    roots = [o for o in new if o.parent is None]
    if len(roots) == 1:
        root = roots[0]
    else:
        root = bpy.data.objects.new("GLBRoot", None)
        scene.collection.objects.link(root)
        for r in roots:
            r.parent = root
        new.append(root)
    bpy.context.view_layer.update()
    lo, hi = _world_bbox(new)
    for o in new:
        o.hide_render = True
        o.hide_set(True)
    _LIB[rel] = (root, new, max(0.01, hi.z - lo.z), lo.z)
    return _LIB[rel]


def glb_instance(rel, loc, height, rot_z=0.0):
    t = glb_template(rel)
    if not t:
        return None
    root, objs, h, minz = t
    mp = {}
    for o in objs:
        c = o.copy()
        scene.collection.objects.link(c)
        c.hide_render = False
        c.hide_set(False)
        mp[o] = c
    for o in objs:
        if o.parent in mp:
            mp[o].parent = mp[o.parent]
    r = mp[root]
    sc = height / h
    r.scale = (r.scale[0] * sc, r.scale[1] * sc, r.scale[2] * sc)
    r.rotation_euler = (r.rotation_euler[0], r.rotation_euler[1], r.rotation_euler[2] + rot_z)
    r.location = (loc[0], loc[1], loc[2] - minz * sc)
    return r, [mp[o] for o in objs]


GLB_PROPS = {
    "house": (["batiments/maison_bleue.glb", "batiments/maison_rose.glb", "batiments/maison_menthe.glb", "batiments/maison_jaune_tuiles.glb", "batiments/maison_creme_ardoise.glb"], 6.5),
    "townhall": (["batiments/mairie.glb"], 7.5),
    "tree": (["decor/arbre.glb"], 4.6),
    "lamp": (["decor/lampadaire.glb"], 3.8),
    "car": (["accessoires/voiture_doree.glb"], 1.7),
    "fountain": (["decor/fontaine.glb"], 1.6),
    "castle": (["decor/chateau.glb"], 9.0),
    "mountain": (["decor/montagne.glb"], 16.0),
    "market": (["decor/etal_marche.glb"], 3.2),
    "gate": (["decor/portail_marche.glb"], 4.2),
    "stock_screen": (["accessoires/ecran_bourse.glb"], 2.6),
    "price_sign": (["accessoires/panneau_prix.glb"], 2.2),
    "subscribe": (["accessoires/bouton_abonne_toi.glb"], 1.2),
}
CHAR_MODELS = {
    "villageois_%02d" % i: "personnages/villageois_%02d.glb" % i for i in range(1, 11)
}
CHAR_MODELS.update({
    "marcel_vieux": "personnages/marcel_vieux.glb",
    "marcel_riche": "personnages/marcel_riche.glb",
    "ours": "personnages/ours.glb",
    "docteur_shark": "personnages/docteur_shark.glb",
})


# ---------------------------------------------------------------- objets (props)
def prop(kind, x, y, color=None, text=""):
    c = hex_rgba(color, None) if color else None
    if kind in GLB_PROPS and not (kind == "house" and c is not None and STYLE == "flat_vector") and not (STYLE == "paper2d" and globals().get("P2_STICK")):
        files, hgt = GLB_PROPS[kind]
        rot = math.pi if (kind in ("house", "townhall") and x > LOC_X_CUR + 0.1) else 0.0
        if kind in ("house", "townhall"):
            rot = -math.pi / 2 if x > LOC_X_CUR else math.pi / 2
        if glb_instance(random.choice(files), (x, y, 0.0), hgt * random.uniform(0.92, 1.08), rot_z=rot):
            return
    if kind in ("townhall", "castle", "market", "gate"):
        kind = "house"
    elif kind == "fountain":
        cyl((x, y, 0.3), 1.6, 0.6, (0.85, 0.82, 0.75, 1.0), verts=24)
        cyl((x, y, 0.5), 1.4, 0.2, (0.35, 0.6, 0.9, 1.0), verts=24)
        return
    elif kind == "mountain":
        cone((x, y + 20, 7), 9, 14, c or (0.45, 0.55, 0.5, 1.0), verts=5)
        return
    elif kind in ("stock_screen", "price_sign", "subscribe"):
        kind = "sign"
    if kind == "tree":
        box((x, y, 0.7), (0.3, 0.3, 1.4), (0.36, 0.23, 0.14, 1.0))
        cone((x, y, 2.3), 1.0, 2.4, c or (0.16, 0.55, 0.25, 1.0))
    elif kind == "pine":
        box((x, y, 0.5), (0.25, 0.25, 1.0), (0.32, 0.2, 0.12, 1.0))
        for i in range(3):
            cone((x, y, 1.4 + 0.8 * i), 1.1 - 0.3 * i, 1.4, c or (0.12, 0.40, 0.26, 1.0))
    elif kind == "house":
        h = random.uniform(3.0, 4.6)
        col = c or random.choice([(0.92, 0.45, 0.42, 1.0), (0.45, 0.66, 0.95, 1.0), (0.96, 0.84, 0.45, 1.0), (0.55, 0.82, 0.55, 1.0)])
        box((x, y, h / 2), (4.0, 4.0, h), col)
        box((x, y, h + 0.4), (4.4, 4.4, 0.8), (0.35, 0.22, 0.2, 1.0))
        for wx in (-1.0, 1.0):
            box((x + wx, y - 2.02, h * 0.6), (0.8, 0.06, 0.8), WIN_ON if NIGHT else (0.6, 0.85, 1.0, 1.0))
        box((x, y - 2.02, 0.9), (0.9, 0.06, 1.8), (0.4, 0.25, 0.15, 1.0))
    elif kind == "tower":
        h = random.uniform(9, 22)
        col = c or random.choice([(0.55, 0.45, 0.95, 1.0), (0.35, 0.6, 0.95, 1.0), (0.4, 0.85, 0.65, 1.0), (0.95, 0.55, 0.75, 1.0)])
        box((x, y, h / 2), (3.0, 3.0, h), col)
        for k in range(int(h // 2)):
            box((x, y - 1.52, 1.2 + 2 * k), (2.2, 0.05, 0.6), WIN_ON if NIGHT else (0.75, 0.9, 1.0, 1.0))
    elif kind == "car":
        col = c or random.choice([(0.9, 0.2, 0.2, 1.0), (0.2, 0.45, 0.9, 1.0), (0.95, 0.8, 0.2, 1.0)])
        box((x, y, 0.55), (1.8, 3.6, 0.8), col)
        box((x, y + 0.2, 1.15), (1.6, 1.8, 0.6), (0.7, 0.85, 1.0, 1.0))
        for dx in (-0.9, 0.9):
            for dy in (-1.2, 1.2):
                cyl((x + dx, y + dy, 0.3), 0.32, 0.25, (0.08, 0.08, 0.08, 1.0), rot=(0, math.radians(90), 0))
    elif kind == "lamp":
        box((x, y, 1.6), (0.12, 0.12, 3.2), (0.2, 0.2, 0.22, 1.0))
        sphere((x, y, 3.3), 0.3, (1.0, 0.9, 0.55, 1.0))
        if NIGHT:
            ld = bpy.data.lights.new("Lamp", type="POINT")
            ld.energy = 120
            ld.color = (1.0, 0.82, 0.5)
            lo = bpy.data.objects.new("Lamp", ld)
            scene.collection.objects.link(lo)
            lo.location = (x, y, 3.0)
    elif kind == "table":
        box((x, y, 0.75), (1.8, 1.0, 0.1), c or (0.55, 0.36, 0.2, 1.0))
        for dx in (-0.8, 0.8):
            for dy in (-0.4, 0.4):
                box((x + dx, y + dy, 0.37), (0.08, 0.08, 0.75), (0.4, 0.26, 0.15, 1.0))
    elif kind == "bed":
        box((x, y, 0.35), (1.6, 2.6, 0.5), c or (0.45, 0.55, 0.85, 1.0))
        box((x, y + 1.1, 0.7), (1.4, 0.5, 0.25), (0.97, 0.97, 0.97, 1.0))
    elif kind == "door":
        box((x, y, 1.1), (1.1, 0.12, 2.2), c or (0.45, 0.28, 0.16, 1.0))
        sphere((x + 0.35, y - 0.08, 1.1), 0.06, (0.95, 0.8, 0.3, 1.0), seg=8)
    elif kind == "sign":
        box((x, y, 1.0), (0.1, 0.1, 2.0), (0.35, 0.25, 0.15, 1.0))
        box((x, y, 2.2), (2.4, 0.12, 0.9), c or (0.95, 0.95, 0.9, 1.0))
        if text:
            text3d(text.upper(), (x, y - 0.08, 2.2), 0.32, (0.1, 0.1, 0.12, 1.0))
    elif kind == "fence":
        for k in range(6):
            box((x - 2.5 + k, y, 0.5), (0.12, 0.12, 1.0), c or (0.9, 0.88, 0.8, 1.0))
        box((x, y, 0.75), (5.2, 0.08, 0.12), c or (0.9, 0.88, 0.8, 1.0))
    elif kind == "rock":
        sphere((x, y, 0.3), random.uniform(0.4, 0.9), c or (0.5, 0.5, 0.52, 1.0), seg=6)
    elif kind == "box":
        s = random.uniform(0.5, 1.0)
        box((x, y, s / 2), (s, s, s), c or (0.75, 0.55, 0.3, 1.0))
    elif kind == "bench":
        box((x, y, 0.45), (2.0, 0.6, 0.1), c or (0.55, 0.35, 0.2, 1.0))
        box((x, y + 0.28, 0.8), (2.0, 0.08, 0.6), c or (0.55, 0.35, 0.2, 1.0))
    elif kind == "tv":
        box((x, y, 1.3), (1.6, 0.12, 0.95), (0.08, 0.08, 0.1, 1.0))
        box((x, y - 0.07, 1.3), (1.45, 0.02, 0.8), c or (0.3, 0.6, 1.0, 1.0))
    elif kind == "fridge":
        box((x, y, 1.0), (0.9, 0.8, 2.0), c or (0.92, 0.93, 0.95, 1.0))
    elif kind == "coins":
        for k in range(7):
            cyl((x + random.uniform(-0.5, 0.5), y + random.uniform(-0.5, 0.5), 0.05 + 0.06 * k), 0.25, 0.06, (1.0, 0.8, 0.2, 1.0), verts=16)
    elif kind == "ladder":
        for dx in (-0.4, 0.4):
            box((x + dx, y, 2.5), (0.08, 0.08, 5.0), c or (0.6, 0.45, 0.25, 1.0))
        for k in range(9):
            box((x, y, 0.5 + 0.5 * k), (0.8, 0.06, 0.06), c or (0.6, 0.45, 0.25, 1.0))
    elif kind == "stage":
        box((x, y, 0.4), (6, 3, 0.8), (0.4, 0.25, 0.15, 1.0))
        for dx in (-3.2, 3.2):
            box((x + dx, y + 1.2, 2.5), (0.6, 0.3, 5.0), (0.75, 0.08, 0.1, 1.0))
    elif kind == "moon":
        sphere((x, y + 30, 18), 6, (0.95, 0.95, 0.85, 1.0), seg=24)
    elif kind == "monitor":
        box((x, y, 1.4), (0.9, 0.12, 0.6), (0.06, 0.06, 0.08, 1.0))
        box((x, y - 0.07, 1.4), (0.8, 0.02, 0.5), (0.24, 1.0, 0.54, 1.0))
    elif kind == "desk":
        box((x, y, 0.75), (1.4, 0.8, 0.08), c or (0.7, 0.55, 0.35, 1.0))
        box((x, y, 0.37), (1.3, 0.7, 0.72), c or (0.62, 0.48, 0.3, 1.0))
    elif kind == "shelf":
        box((x, y, 1.1), (2.0, 0.5, 2.2), c or (0.55, 0.38, 0.22, 1.0))
        for k in range(3):
            for j in range(4):
                box((x - 0.7 + 0.45 * j, y - 0.2, 0.5 + 0.7 * k), (0.3, 0.2, 0.35), random.choice([(0.9, 0.3, 0.3, 1.0), (0.3, 0.6, 0.9, 1.0), (0.95, 0.8, 0.3, 1.0), (0.4, 0.8, 0.45, 1.0)]))
    elif kind == "umbrella":
        box((x, y, 1.2), (0.08, 0.08, 2.4), (0.9, 0.9, 0.9, 1.0))
        cone((x, y, 2.5), 1.4, 0.6, c or (0.95, 0.35, 0.35, 1.0), verts=10)
    elif kind == "star":
        for k in range(40):
            box((x + random.uniform(-25, 25), y + random.uniform(10, 40), random.uniform(2, 25)), (0.08, 0.08, 0.08), (1.0, 1.0, 0.9, 1.0))
    elif kind == "sofa":
        col = c or (0.72, 0.16, 0.18, 1.0)
        box((x, y, 0.35), (2.6, 1.0, 0.5), col)
        box((x, y + 0.42, 0.9), (2.6, 0.22, 0.9), col)
        for dx in (-1.25, 1.25):
            box((x + dx, y, 0.65), (0.22, 1.0, 0.6), col)
        for dx in (-0.62, 0.62):
            box((x + dx, y - 0.05, 0.66), (1.15, 0.85, 0.14), tuple(min(1.0, v * 1.12) for v in col[:3]) + (1.0,))
    elif kind == "armchair":
        col = c or (0.35, 0.45, 0.65, 1.0)
        box((x, y, 0.35), (1.1, 1.0, 0.5), col)
        box((x, y + 0.42, 0.9), (1.1, 0.22, 0.9), col)
        for dx in (-0.5, 0.5):
            box((x + dx, y, 0.65), (0.18, 1.0, 0.55), col)
    elif kind == "pancakes":
        box((x, y, 0.75), (1.4, 0.8, 0.08), (0.6, 0.42, 0.26, 1.0))
        box((x, y, 0.37), (1.3, 0.7, 0.72), (0.52, 0.36, 0.22, 1.0))
        cyl((x, y, 0.81), 0.36, 0.03, (0.97, 0.97, 0.97, 1.0), verts=24)
        for k in range(5):
            cyl((x, y, 0.85 + 0.055 * k), 0.27, 0.05, (0.88, 0.62, 0.3, 1.0), verts=20)
        box((x, y, 1.13), (0.12, 0.12, 0.05), (1.0, 0.93, 0.55, 1.0))
        cyl((x + 0.5, y + 0.1, 0.9), 0.08, 0.2, c or (0.15, 0.3, 0.55, 1.0), verts=12)
    elif kind == "plate":
        cyl((x, y, 0.81), 0.32, 0.03, (0.97, 0.97, 0.97, 1.0), verts=24)
    elif kind == "mug":
        cyl((x, y, 0.9), 0.1, 0.22, c or (0.15, 0.3, 0.55, 1.0), verts=12)
    elif kind == "frame":
        box((x, 6.8, 3.6), (1.2, 0.06, 0.9), (0.45, 0.28, 0.15, 1.0))
        box((x, 6.76, 3.6), (1.0, 0.04, 0.72), c or random.choice([(0.85, 0.55, 0.45, 1.0), (0.5, 0.7, 0.85, 1.0), (0.85, 0.8, 0.5, 1.0)]))
    elif kind == "window":
        box((x, 6.8, 3.2), (1.8, 0.08, 2.0), (0.97, 0.97, 0.95, 1.0))
        box((x, 6.76, 3.2), (1.6, 0.04, 1.8), (0.08, 0.12, 0.25, 1.0) if NIGHT else (0.72, 0.86, 0.97, 1.0))
        box((x, 6.74, 3.2), (0.06, 0.04, 1.8), (0.97, 0.97, 0.95, 1.0))
        for dx in (-1.05, 1.05):
            box((x + dx, 6.7, 3.0), (0.45, 0.08, 2.5), c or (0.78, 0.2, 0.22, 1.0))
    elif kind == "rug":
        box((x, y, 0.01), (3.6, 2.4, 0.02), c or (0.62, 0.12, 0.14, 1.0))
        box((x, y, 0.02), (3.0, 1.8, 0.02), (0.85, 0.7, 0.45, 1.0))
    elif kind == "bus":
        col = c or (0.98, 0.78, 0.12, 1.0)
        box((x, y, 1.6), (6.5, 2.4, 2.6), col)
        for k in range(5):
            box((x - 2.4 + 1.2 * k, y - 1.22, 2.1), (0.9, 0.04, 0.8), (0.2, 0.25, 0.32, 1.0))
        box((x, y - 1.22, 1.15), (6.5, 0.04, 0.12), (0.1, 0.1, 0.1, 1.0))
        for dx in (-2.2, 2.2):
            cyl((x + dx, y - 1.0, 0.45), 0.45, 0.3, (0.08, 0.08, 0.08, 1.0), verts=16, rot=(math.radians(90), 0, 0))
    elif kind == "snowman":
        sphere((x, y, 0.6), 0.65, (0.97, 0.98, 1.0, 1.0))
        sphere((x, y, 1.5), 0.45, (0.97, 0.98, 1.0, 1.0))
        cone((x, y - 0.45, 1.5), 0.07, 0.35, (1.0, 0.5, 0.1, 1.0), verts=8)
        box((x, y, 2.0), (0.6, 0.6, 0.4), (0.1, 0.1, 0.12, 1.0))
    elif kind == "bookshelf":
        box((x, 6.5, 1.3), (1.6, 0.5, 2.6), c or (0.5, 0.33, 0.2, 1.0))
        for k in range(4):
            for j in range(5):
                box((x - 0.6 + 0.3 * j, 6.28, 0.45 + 0.6 * k), (0.2, 0.1, 0.4), random.choice([(0.85, 0.25, 0.25, 1.0), (0.25, 0.5, 0.85, 1.0), (0.95, 0.8, 0.3, 1.0), (0.35, 0.7, 0.4, 1.0)]))
    elif kind == "mirror":
        box((x, 6.8, 2.4), (1.1, 0.06, 2.2), (0.55, 0.38, 0.22, 1.0))
        box((x, 6.76, 2.4), (0.95, 0.04, 2.0), c or (0.82, 0.88, 0.92, 1.0))
    elif kind == "lamp_floor":
        box((x, y, 0.9), (0.08, 0.08, 1.8), (0.25, 0.22, 0.2, 1.0))
        cone((x, y, 1.95), 0.35, 0.4, (1.0, 0.85, 0.55, 1.0), verts=12)
    else:
        box((x, y, 0.5), (1.0, 1.0, 1.0), c or ACCENT)


# ---------------------------------------------------------------- lieux
LOC_DEFAULT_PROPS = {
    "street": ["house", "house", "house", "house", "tree", "lamp", "car"],
    "city": ["tower", "tower", "tower", "tower", "tower", "car", "lamp"],
    "house": ["sofa", "tv", "rug", "frame", "window", "table", "lamp_floor", "bookshelf"],
    "room": ["bed", "rug", "window", "frame", "lamp_floor", "box"],
    "school": ["desk", "desk", "desk", "desk", "sign"],
    "shop": ["shelf", "shelf", "table", "coins"],
    "office": ["desk", "desk", "monitor", "monitor"],
    "hospital": ["bed", "monitor", "door"],
    "forest": ["pine", "pine", "pine", "tree", "pine", "rock", "tree"],
    "park": ["tree", "tree", "bench", "lamp", "fence"],
    "field": ["fence", "tree", "rock"],
    "beach": ["umbrella", "rock", "box"],
    "lake": ["pine", "pine", "rock", "sign"],
    "space": ["star", "moon"],
    "stage": ["stage", "lamp", "lamp"],
    "vertical_city": ["tower", "tower", "tower", "tower", "tower", "tower", "box", "box"],
    "village": ["house", "house", "house", "house", "tree", "tree", "lamp", "fountain"],
    "market": ["market", "market", "gate", "lamp", "house", "house"],
}
INDOOR = ("house", "room", "school", "shop", "office", "hospital")

LOC_POS = {}
LOC_X_CUR = 0.0
WEATHER = SPEC.get("weather", "none")


def _fcurves_of(obj):
    ad = obj.animation_data
    act = ad.action if ad else None
    if act is None:
        return []
    fcs = getattr(act, "fcurves", None)
    if fcs is not None:
        return list(fcs)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


def _set_interp(obj, mode):
    for fc in _fcurves_of(obj):
        for kp in fc.keyframe_points:
            kp.interpolation = mode


def precipitation(ox, kind="snow", count=170):
    """Flocons (ou pluie) qui tombent en boucle devant la caméra."""
    if kind == "rain":
        size, col, period, n = (0.025, 0.025, 0.5), (0.7, 0.8, 0.95, 1.0), 8, count
    else:
        size, col, period, n = (0.07, 0.07, 0.07), (1.0, 1.0, 1.0, 1.0), 48, count
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(ox, 0, -50))
    base = bpy.context.active_object
    base.scale = size
    base.data.materials.append(mat(col))
    for k in range(n):
        o = bpy.data.objects.new("Flake", base.data)
        scene.collection.objects.link(o)
        o.scale = size
        o.location = (ox + random.uniform(-9, 9), random.uniform(-9, 10), 9.0)
        ph = random.uniform(0, period)
        o.keyframe_insert("location", index=2, frame=1 - ph)
        o.location.z = -0.2
        o.keyframe_insert("location", index=2, frame=1 - ph + period)
        for fc in _fcurves_of(o):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
            try:
                fc.modifiers.new("CYCLES")
            except Exception:
                pass


def furnish_interior(ox, t, wall):
    """Papier peint rayé, parquet, plinthes : l'intérieur chaleureux de la vidéo de référence."""
    dark = tuple(v * 0.95 for v in wall[:3]) + (1.0,)
    for k in range(-14, 14, 2):
        box((ox + k * 0.5 + 0.25, 6.83, 3.0), (0.25, 0.02, 6.0), dark)
    for k in range(-5, 12, 2):
        for sx in (-6.83, 6.83):
            box((ox + sx, k * 0.5 + 0.25, 3.0), (0.02, 0.25, 6.0), dark)
    floor_a, floor_b = (0.55, 0.33, 0.2, 1.0), (0.5, 0.3, 0.18, 1.0)
    for k in range(-14, 14):
        box((ox + k * 0.5 + 0.25, 1.5, 0.005), (0.48, 12, 0.01), floor_a if k % 2 else floor_b)
    for (bx, by, sx, sy) in ((ox, 6.82, 14, 0.06), (ox - 6.82, 1.5, 0.06, 12), (ox + 6.82, 1.5, 0.06, 12)):
        box((bx, by, 0.15), (sx, sy, 0.3), (0.96, 0.95, 0.92, 1.0))


for li, L in enumerate(SPEC.get("locations", [])):
    ox = li * 140.0
    LOC_X_CUR = ox
    LOC_POS[L["id"]] = ox
    t = L.get("type", "street")
    _loc_tod = L.get("time_of_day") or TOD
    CUR_TINT = (0.42, 0.5, 0.78) if (_loc_tod == "night" and t not in INDOOR and STYLE == "roblox") else None
    if WEATHER == "snow" and t not in INDOOR and not L.get("ground"):
        L["ground"] = "#EEF3F8"
    gcol = hex_rgba(L.get("ground"), None) or {
        "beach": (0.93, 0.85, 0.6, 1.0), "lake": (0.62, 0.8, 0.92, 1.0), "space": (0.25, 0.25, 0.3, 1.0),
        "city": (0.35, 0.36, 0.4, 1.0), "field": (0.55, 0.75, 0.3, 1.0),
    }.get(t, GROUND if t not in INDOOR else (0.55, 0.4, 0.28, 1.0))
    box((ox, 6, -0.25), (60, 70, 0.5), gcol)
    if t in ("street", "city"):
        box((ox, 6, -0.01), (5.0, 70, 0.04), (0.17, 0.18, 0.22, 1.0))
        for k in range(-4, 16):
            box((ox, k * 3.5, 0.02), (0.2, 1.4, 0.02), (0.95, 0.95, 0.95, 1.0))
    if t == "beach":
        box((ox, 30, -0.05), (60, 30, 0.1), (0.2, 0.55, 0.85, 1.0))
    if t == "village":
        box((ox, 6, -0.01), (4.0, 70, 0.04), (0.78, 0.72, 0.6, 1.0))
    if t == "vertical_city":
        # Plus on est riche, plus on vit haut : décharge en bas, plateformes et villas en haut
        tower_cols = [(0.55, 0.35, 0.95, 1.0), (0.25, 0.55, 1.0, 1.0), (0.2, 0.85, 0.6, 1.0), (1.0, 0.45, 0.7, 1.0), (1.0, 0.6, 0.2, 1.0)]
        for k in range(5):
            tx = ox + (k - 2) * 4.2
            th = 6 + k * 6 if k % 2 == 0 else 9 + k * 4
            box((tx, 9.0, th / 2), (2.4, 2.4, th), tower_cols[k])
            box((tx, 9.0, th + 0.2), (4.0, 4.0, 0.4), (0.98, 0.95, 0.85, 1.0))
            box((tx, 9.0, th + 1.4), (2.6, 2.6, 2.0), random.choice([(1.0, 0.85, 0.35, 1.0), (0.98, 0.98, 0.98, 1.0), (0.6, 0.9, 1.0, 1.0)]))
        for k in range(10):
            box((ox + random.uniform(-6, 6), random.uniform(1, 5), 0.3), (random.uniform(0.6, 1.4), random.uniform(0.6, 1.4), 0.6), random.choice([(0.4, 0.3, 0.25, 1.0), (0.3, 0.35, 0.3, 1.0), (0.55, 0.5, 0.45, 1.0)]))
    if t in INDOOR:
        wall = hex_rgba(L.get("wall"), None) or {"hospital": (0.75, 0.88, 0.82, 1.0), "school": (0.95, 0.9, 0.75, 1.0), "office": (0.85, 0.87, 0.9, 1.0)}.get(t, (0.93, 0.88, 0.77, 1.0) if STYLE == "roblox" else (0.85, 0.72, 0.6, 1.0))
        box((ox, 7.0, 3.0), (14, 0.3, 6.0), wall)
        box((ox - 7.0, 1.5, 3.0), (0.3, 12, 6.0), wall)
        box((ox + 7.0, 1.5, 3.0), (0.3, 12, 6.0), wall)
        if t == "school":
            box((ox, 6.8, 2.8), (6, 0.1, 2.4), (0.12, 0.3, 0.2, 1.0))
        if STYLE in ("roblox", "paper2d"):
            furnish_interior(ox, t, wall)
        il = bpy.data.lights.new("Indoor", type="POINT")
        il.energy = 380
        il.color = (1.0, 0.85, 0.65)
        ilo = bpy.data.objects.new("Indoor", il)
        scene.collection.objects.link(ilo)
        ilo.location = (ox, 1.5, 5.2)
    # objets : ceux décrits par l'IA, sinon le kit du lieu
    props = L.get("props") or [{"kind": k} for k in LOC_DEFAULT_PROPS.get(t, ["tree", "rock"])]
    slots = []
    for pi, P in enumerate(props[:14]):
        kind = P.get("kind", "box")
        count = max(1, min(6, int(P.get("count", 1) or 1)))
        for c_i in range(count):
            if kind in ("house", "tower"):
                side = -1 if (len(slots) % 2 == 0) else 1
                px, py = ox + side * random.uniform(7.0, 9.5), 2.0 + 7.0 * (len(slots) // 2) + random.uniform(-1, 1)
            elif kind in ("moon", "star"):
                px, py = ox, 0
            elif t in INDOOR:
                px, py = ox + random.choice([-4.5, -3.0, 3.0, 4.5]), random.uniform(2.5, 6.0)
            else:
                px, py = ox + random.choice([-1, 1]) * random.uniform(3.0, 8.0), random.uniform(1.0, 16.0)
            prop(kind, px, py, P.get("color"), P.get("text", ""))
            slots.append((px, py))
    if L.get("sign_text"):
        prop("sign", ox + 2.6, 3.2, None, L["sign_text"])
    if t not in INDOOR and STYLE in ("roblox", "paper2d"):
        # profondeur : fond de décor (maisons / sapins lointains) + toile de ciel par lieu
        for k in range(9):
            prop("pine", ox + random.uniform(-26, 26), random.uniform(18, 30))
        if WEATHER == "snow":
            for k in range(6):
                mound = sphere((ox + random.uniform(-12, 12), random.uniform(4, 16), 0.0), random.uniform(0.9, 1.7), (0.95, 0.97, 1.0, 1.0), seg=24)
                mound.scale = (1.4, 1.0, 0.35)
        sky_c = SKY if _loc_tod == TOD else ((0.04, 0.06, 0.16, 1.0) if _loc_tod == "night" else (0.45, 0.7, 0.98, 1.0))
        _t = CUR_TINT
        CUR_TINT = None
        box((ox, 44, 20), (140, 0.2, 60), sky_c)
        CUR_TINT = _t
        if WEATHER in ("snow", "rain"):
            precipitation(ox, WEATHER)
    CUR_TINT = None
    if STYLE == "paper2d" and globals().get("P2_STICK"):
        try:
            p2_alive(ox, t in INDOOR, slots, seed=li)
        except Exception as _e:
            print("p2_alive:", _e)


# ---------------------------------------------------------------- personnages
CHARS = {c["id"]: c for c in SPEC.get("characters", [])}


def _rig_glb_char(root, objs):
    """Retrouve tête / torse / bras / jambes d'un modèle GLB (groupes sans nom) et pose des pivots articulés."""
    bpy.context.view_layer.update()
    groups = [o for o in objs if o.parent == root and o.type == "EMPTY"]
    if len(groups) < 6:
        return None
    info = []
    for g in groups:
        meshes = [m for m in objs if m.type == "MESH" and (m.parent == g or (m.parent and m.parent.parent == g))]
        if not meshes:
            continue
        lo, hi = _world_bbox(meshes)
        info.append((g, (lo + hi) / 2, lo, hi))
    if len(info) < 6:
        return None
    info.sort(key=lambda t: t[1].z)
    legs = info[:2]
    head = info[-1]
    try:
        hg = head[0]
        hm = [m for m in objs if m.type == "MESH" and (m.parent == hg or (m.parent and m.parent.parent == hg))]
        solid = []
        for m in hm:
            lo_m, hi_m = _world_bbox([m])
            dims = hi_m - lo_m
            if min(dims.x, dims.y, dims.z) > 0.08:
                solid.append(((lo_m + hi_m) / 2, lo_m, hi_m))
        if solid:
            solid.sort(key=lambda t: t[0].z)
            c_m, lo_m, hi_m = solid[0]
            FACE_INFO[root.name] = (hg, (c_m.x, lo_m.y - 0.01, c_m.z - 0.03 * (hi_m.z - lo_m.z)),
                                    (hi_m.x - lo_m.x) * 0.95, (hi_m.z - lo_m.z) * 0.95)
    except Exception:
        pass
    mid = info[2:-1]
    mid.sort(key=lambda t: abs(t[1].x - root.location.x))
    torso = mid[0]
    arms = mid[1:3] if len(mid) >= 3 else mid[1:]
    piv = {}
    for name, (g, ctr, lo, hi) in (("legL", legs[0]), ("legR", legs[1]), ("armL", arms[0] if arms else torso), ("armR", arms[1] if len(arms) > 1 else torso)):
        e = bpy.data.objects.new("Pivot_" + name, None)
        scene.collection.objects.link(e)
        e.location = Vector((ctr.x, ctr.y, hi.z - 0.1 * (hi.z - lo.z)))
        bpy.context.view_layer.update()
        mw = g.matrix_world.copy()
        e.parent = root
        e.matrix_parent_inverse = root.matrix_world.inverted()
        bpy.context.view_layer.update()
        g.parent = e
        g.matrix_parent_inverse = e.matrix_world.inverted()
        g.matrix_world = mw
        piv[name] = e
    return piv


FACE_INFO = {}   # root.name -> (head_obj, centre_face, largeur, hauteur)
FACES = {}       # (root.name, emotion) -> empty
INK = (0.07, 0.05, 0.05, 1.0)


def _attach(o, parent):
    bpy.context.view_layer.update()
    mw = o.matrix_world.copy()
    o.parent = parent
    o.matrix_parent_inverse = parent.matrix_world.inverted()
    o.matrix_world = mw


def _seg(fr, p0, p1, thick, col, root):
    """Trait plat entre deux points (x, z) sur le plan du visage."""
    (x0, z0), (x1, z1) = p0, p1
    ln = math.hypot(x1 - x0, z1 - z0)
    o = box((fr[0] + (x0 + x1) / 2, fr[1], fr[2] + (z0 + z1) / 2), (ln + thick * 0.6, 0.02, thick), col,
            rot=(0, -math.atan2(z1 - z0, x1 - x0), 0))
    _attach(o, root)
    return o


def _arc(fr, cx, cz, half_w, depth, thick, col, root, n=5):
    """Arc de bouche : depth > 0 = sourire, < 0 = moue triste."""
    pts = []
    for k in range(n + 1):
        u = -1 + 2 * k / n
        pts.append((cx + u * half_w, cz - depth * (1 - u * u)))
    for a, b in zip(pts[:-1], pts[1:]):
        _seg(fr, a, b, thick, col, root)


def _oval(fr, x, z, rx, rz, col, root, dy=0.0):
    o = sphere((fr[0] + x, fr[1] + dy, fr[2] + z), 1.0, col, seg=12)
    o.scale = (rx, 0.012, rz)
    _attach(o, root)
    return o


def build_face(rootname, emotion):
    """Visage expressif façon vidéo de référence : yeux brillants, sourcils, bouche, larmes, joues roses."""
    head, ctr, w, h = FACE_INFO[rootname]
    fr = (ctr[0], ctr[1] - 0.012, ctr[2])
    root = bpy.data.objects.new("Face_" + emotion, None)
    scene.collection.objects.link(root)
    root.location = ctr
    _attach(root, head)
    big = emotion in ("surprised", "scared")
    ex, ez = 0.2 * w, 0.06 * h
    er = (0.075 * w * (1.35 if big else 1.0), 0.1 * h * (1.35 if big else 1.0))
    for sx in (-1, 1):
        if emotion == "happy":
            _arc(fr, sx * ex, ez + 0.02 * h, er[0], -0.05 * h, 0.035 * w, INK, root, n=4)
        else:
            if emotion == "scared":
                _oval(fr, sx * ex, ez, er[0] * 1.2, er[1] * 1.15, (0.98, 0.98, 0.98, 1.0), root)
                _oval(fr, sx * ex, ez, er[0] * 0.45, er[1] * 0.45, INK, root, dy=-0.006)
            else:
                _oval(fr, sx * ex, ez, er[0], er[1], INK, root)
                _oval(fr, sx * ex - 0.025 * w, ez + 0.035 * h, er[0] * 0.32, er[1] * 0.3, (1.0, 1.0, 1.0, 1.0), root, dy=-0.006)
        bz = ez + 0.21 * h + (0.05 * h if big else 0.0)
        inner, outer = sx * 0.09 * w, sx * 0.3 * w
        if emotion in ("sad", "cry", "scared"):
            _seg(fr, (inner, bz + 0.05 * h), (outer, bz - 0.03 * h), 0.03 * w, INK, root)
        elif emotion == "angry":
            _seg(fr, (inner, bz - 0.06 * h), (outer, bz + 0.04 * h), 0.04 * w, INK, root)
        elif emotion != "happy":
            _seg(fr, (inner, bz), (outer, bz + 0.015 * h), 0.028 * w, (0.35, 0.22, 0.15, 1.0), root)
        if emotion in ("happy", "cry", "smirk"):
            _oval(fr, sx * 0.33 * w, -0.1 * h, 0.07 * w, 0.045 * h, (0.98, 0.6, 0.62, 1.0), root)
        if emotion == "cry":
            o = box((fr[0] + sx * (ex + 0.03 * w), fr[1] - 0.01, fr[2] - 0.17 * h), (0.045 * w, 0.02, 0.32 * h), (0.55, 0.8, 1.0, 1.0))
            _attach(o, root)
    mz = -0.24 * h
    if emotion == "happy":
        _arc(fr, 0, mz + 0.03 * h, 0.17 * w, 0.09 * h, 0.035 * w, INK, root)
    elif emotion in ("sad", "cry"):
        _arc(fr, 0, mz - 0.05 * h, 0.13 * w, -0.06 * h, 0.032 * w, INK, root, n=4)
    elif emotion == "surprised":
        _oval(fr, 0, mz - 0.02 * h, 0.07 * w, 0.09 * h, INK, root)
    elif emotion == "scared":
        _oval(fr, 0, mz - 0.02 * h, 0.05 * w, 0.05 * h, INK, root)
    elif emotion == "angry":
        _arc(fr, 0, mz - 0.03 * h, 0.12 * w, -0.03 * h, 0.035 * w, INK, root, n=3)
    elif emotion == "smirk":
        _seg(fr, (-0.12 * w, mz), (0.05 * w, mz), 0.032 * w, INK, root)
        _seg(fr, (0.05 * w, mz), (0.15 * w, mz + 0.05 * h), 0.032 * w, INK, root)
    else:
        _arc(fr, 0, mz, 0.11 * w, 0.03 * h, 0.03 * w, INK, root, n=4)
    return root


def set_emotion(parts, emotion, frame):
    """Affiche le visage de l'émotion voulue à partir de `frame` (les autres sont réduits à zéro)."""
    rn = parts[0].name
    if rn not in FACE_INFO:
        return
    key = (rn, emotion)
    if key not in FACES:
        e = build_face_2d(rn, emotion) if STYLE == "paper2d" else build_face(rn, emotion)
        e.scale = (0, 0, 0)
        e.keyframe_insert("scale", frame=0)
        FACES[key] = e
    for (r2, emo2), e in FACES.items():
        if r2 != rn:
            continue
        e.scale = (1, 1, 1) if emo2 == emotion else (0, 0, 0)
        e.keyframe_insert("scale", frame=frame)


def make_char(cid, loc, rot_z=0.0):
    if STYLE == "paper2d":
        return make_char_2d(cid, loc, rot_z)
    c = CHARS.get(cid, {})
    model = CHAR_MODELS.get(str(c.get("model") or ""))
    if STYLE == "roblox" and model:
        res = glb_instance(model, loc, 3.4 * float(c.get("scale", 1.0) or 1.0), rot_z=rot_z)
        if res:
            r, objs = res
            bpy.context.view_layer.update()
            piv = _rig_glb_char(r, objs)
            if piv:
                return r, piv["armL"], piv["armR"], piv["legL"], piv["legR"]
            dummy = bpy.data.objects.new("NoLimb", None)
            scene.collection.objects.link(dummy)
            return r, dummy, dummy, dummy, dummy
    root = bpy.data.objects.new("Char_" + cid, None)
    scene.collection.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, rot_z)
    sc = float(c.get("scale", 1.0) or 1.0)
    root.scale = (sc, sc, sc)
    skin = hex_rgba(c.get("skin"), (1.0, 0.86, 0.72, 1.0) if FLAT2D else (0.96, 0.82, 0.25, 1.0))
    shirt = hex_rgba(c.get("shirt"), (0.2, 0.45, 0.9, 1.0))
    pants = hex_rgba(c.get("pants"), (0.15, 0.17, 0.24, 1.0))
    dep = 0.12 if FLAT2D else 1.0

    def part(ploc, psize, col):
        return box((ploc[0], ploc[1] * dep, ploc[2]), (psize[0], max(0.04, psize[1] * dep), psize[2]), col, parent=root)

    part((0, 0, 1.65), (1.05, 0.55, 1.15), shirt)
    head_z = 2.75 if FLAT2D else 2.6
    part((0, 0, head_z), (1.0, 0.72, 0.95) if FLAT2D else (0.72, 0.72, 0.72), skin)
    hat = c.get("hat")
    if hat and str(hat).lower() not in ("none", "", "no"):
        part((0, 0, head_z + 0.45), (1.05 if FLAT2D else 0.78, 0.78, 0.28), hex_rgba(hat))
    hair = c.get("hair")
    if hair and (not hat or str(hat).lower() in ("none", "", "no")):
        part((0, 0.05, head_z + 0.38), (1.02 if FLAT2D else 0.76, 0.76, 0.18), hex_rgba(hair))
    front = -0.45 if FLAT2D else -0.37
    eye = (0.02, 0.02, 0.02, 1.0)
    if FLAT2D:
        for sx in (-0.22, 0.22):
            part((sx, front, head_z + 0.05), (0.26, 0.04, 0.3), (0.98, 0.98, 0.98, 1.0))
            part((sx, front - 0.07, head_z + 0.03), (0.11, 0.04, 0.14), eye)
            part((sx * 1.7, front, head_z - 0.22), (0.18, 0.04, 0.1), (0.98, 0.55, 0.62, 1.0))
        part((0, front, head_z - 0.18), (0.24, 0.04, 0.05), eye)
    elif STYLE == "roblox":
        bpy.context.view_layer.update()
        hw = root.matrix_world @ Vector((0, -0.36, head_z))
        FACE_INFO[root.name] = (root, (hw.x, hw.y - 0.01, hw.z), 0.72 * sc, 0.72 * sc)
    else:
        for sx in (-0.16, 0.16):
            part((sx, front, head_z + 0.06), (0.09, 0.04, 0.11), eye)
        part((0, front, head_z - 0.18), (0.24, 0.04, 0.05), eye)
    al = part((-0.75, 0, 1.65), (0.42, 0.45, 1.1), shirt)
    ar = part((0.75, 0, 1.65), (0.42, 0.45, 1.1), shirt)
    ll = part((-0.27, 0, 0.55), (0.46, 0.48, 1.1), pants)
    lr = part((0.27, 0, 0.55), (0.46, 0.48, 1.1), pants)
    return root, al, ar, ll, lr


def animate(parts, action, f0, f1):
    root, al, ar, ll, lr = parts
    base = root.location.copy()
    span = max(2, f1 - f0)
    if action in ("walk", "run"):
        step = 4 if action == "walk" else 2
        dist = 1.2 if action == "walk" else 2.4
        root.location = base + Vector((-dist / 2, 0, 0))
        root.keyframe_insert("location", frame=f0)
        root.location = base + Vector((dist / 2, 0, 0))
        root.keyframe_insert("location", frame=f1)
        # retour à la place de départ sur la coupe (invisible) : le plan suivant est cadré correctement
        root.location = base
        root.keyframe_insert("location", frame=f1 + 1)
        for f in range(f0, f1 + 1, step):
            a = 0.5 if ((f - f0) // step) % 2 == 0 else -0.5
            for o, s in ((al, 1), (ar, -1), (ll, -1), (lr, 1)):
                o.rotation_euler = p2_limb_rot(a * s) if STYLE == "paper2d" else (a * s, 0, 0)
                o.keyframe_insert("rotation_euler", frame=f)
    elif action == "jump":
        for k, f in enumerate(range(f0, f1 + 1, 3)):
            root.location = base + Vector((0, 0, 0.8 if k % 2 else 0.0))
            root.keyframe_insert("location", frame=f)
        root.location = base
        root.keyframe_insert("location", frame=f1 + 1)
    elif action == "point":
        ar.rotation_euler = p2_limb_rot(math.radians(-75)) if STYLE == "paper2d" else (math.radians(-80), 0, 0)
        ar.keyframe_insert("rotation_euler", frame=f0)
        ar.rotation_euler = (0, 0, 0)
        ar.keyframe_insert("rotation_euler", frame=f1 + 1)
    elif action == "fall":
        if root.rotation_mode != "XYZ":
            root.rotation_mode = "XYZ"
        root.rotation_euler = (0, 0, root.rotation_euler[2])
        root.keyframe_insert("rotation_euler", frame=f0)
        root.rotation_euler = (math.radians(80), 0, root.rotation_euler[2])
        root.keyframe_insert("rotation_euler", frame=min(f1, f0 + 8))
        root.rotation_euler = (0, 0, root.rotation_euler[2])
        root.keyframe_insert("rotation_euler", frame=f1 + 1)
    elif action == "sit":
        root.location = base + Vector((0, 0, -0.5))
        root.keyframe_insert("location", frame=f0)
        root.location = base
        root.keyframe_insert("location", frame=f1 + 1)
    else:  # idle / talk : léger balancement des bras
        for k, f in enumerate(range(f0, f1 + 1, 6)):
            _a = 0.12 if k % 2 else -0.05
            al.rotation_euler = p2_limb_rot(-_a) if STYLE == "paper2d" else (_a, 0, 0)
            al.keyframe_insert("rotation_euler", frame=f)


# ---------------------------------------------------------------- plans & caméra
cam_d = bpy.data.cameras.new("Camera")
cam_d.lens = 30
cam = bpy.data.objects.new("Camera", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam


def look(frm, to):
    d = Vector(to) - Vector(frm)
    return d.to_track_quat("-Z", "Y").to_euler()


CAM_OFF = {
    #          début (dx, dy, dz)        fin              hauteur visée
    "drone":  ((0.0, -14.0, 11.0), (0.0, -9.0, 8.0), 1.0),
    "wide":   ((1.5, -9.0, 3.2), (0.5, -7.0, 3.0), 1.6),
    "medium": ((0.8, -5.6, 2.7), (0.3, -4.6, 2.7), 2.1),
    "close":  ((0.3, -3.1, 2.95), (0.1, -2.6, 2.95), 2.85),
    "face":   ((0.12, -1.95, 2.85), (0.04, -1.6, 2.85), 2.8),
    "back":   ((0.9, -3.6, 3.1), (0.6, -3.1, 3.0), 2.4),
    "high":   ((2.6, -5.5, 8.5), (1.9, -4.6, 7.6), 1.0),
    "low":    ((1.0, -3.4, 0.6), (0.6, -3.0, 0.8), 2.2),
    # « pov » : trois-quarts face (l'ancienne caméra derrière la tête ne montrait qu'un dos sans tête)
    "pov":    ((2.4, -4.4, 3.0), (1.8, -3.8, 2.9), 1.9),
    # « tilt » : montée jusqu'au haut des bâtiments, sans finir sur un ciel vide
    "tilt":   ((0.0, -12.0, 1.5), (0.0, -12.0, 7.0), 3.0),
}
if STYLE == "paper2d":
    # références : caméra à hauteur d'yeux, persos grands dans le cadre, jamais de dos (découpes face caméra)
    CAM_OFF.update({
        "wide":   ((1.2, -8.0, 2.4), (0.5, -6.8, 2.3), 1.7),
        "medium": ((0.7, -4.6, 2.35), (0.25, -4.0, 2.35), 2.0),
        "close":  ((0.25, -2.9, 2.6), (0.08, -2.5, 2.6), 2.4),
        "face":   ((0.1, -1.9, 2.6), (0.03, -1.6, 2.6), 2.55),
        "back":   ((0.7, -4.6, 2.35), (0.25, -4.0, 2.35), 2.0),
        "low":    ((0.9, -3.6, 0.9), (0.5, -3.2, 1.0), 2.2),
    })
    cam_d.lens = 32
    try:
        cam_d.dof.use_dof = True
        cam_d.dof.aperture_fstop = 1.6
    except Exception:
        pass
CHAR_SPOT = [(0.0, 2.0), (-1.8, 2.8), (1.8, 2.8), (-3.2, 3.6), (3.2, 3.6)]
cut_frames = set()
placed = {}
# Stickman : un seul vol de caméra continu (aucune coupe sèche, la caméra bouge sur ~85 % des images)
P2_FLOW = STYLE == "paper2d" and bool(globals().get("P2_STICK"))
_flow_prev = None  # (frame de fin, position, cible, lieu)



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


def show_item(sh, at, f0, f1, idx):
    """Ce que dit la phrase, montré pendant le plan : un objet à côté du perso ou un grand mot qui surgit."""
    side = 1 if idx % 2 == 0 else -1
    before = set(o.name for o in scene.objects)
    kind = str(sh.get("kind") or "")
    txt = str(sh.get("text") or "")
    if kind == "text":
        col = hex_rgba(sh.get("color"), ACCENT)
        _tz = 3.6 if STYLE == "paper2d" else 4.3
        o = text3d(txt, (at.x, at.y - 1.2, _tz), 0.62, col)
        try:
            o.data.extrude = 0.06
            o.data.bevel_depth = 0.015
        except Exception:
            pass
        pivot = Vector((at.x, at.y - 1.2, _tz))
    else:
        _dx, _dy = (1.05, -0.9) if STYLE == "paper2d" else (1.9, -0.6)
        prop(kind, at.x + side * _dx, at.y + _dy, sh.get("color"), txt)
        pivot = Vector((at.x + side * _dx, at.y + _dy, 0.0))
    holder = _show_holder("Show_%d" % idx, before, pivot)
    if STYLE == "paper2d":
        try:
            _p2_billboard(holder)
        except Exception:
            pass
    _show_pop(holder, f0, f1)


for si, S in enumerate(SHOTS):
    f0, f1 = int(S["f0"]), int(S["f1"])
    ox = LOC_POS.get(S.get("location"), 0.0)
    who = [S.get("focus")] + list(S.get("others") or [])
    who = [w for w in who if w in CHARS][:4]
    focus_pos = Vector((ox, 2.0, 0.0))
    for k, cid in enumerate(who):
        key = (S.get("location"), cid)
        if key not in placed:
            sx, sy = CHAR_SPOT[len([1 for kk in placed if kk[0] == S.get("location")]) % len(CHAR_SPOT)]
            placed[key] = make_char(cid, (ox + sx, sy, 0.0), rot_z=0.0)
        parts = placed[key]
        emo = S.get("emotion", "neutral")
        if k == 0:
            focus_pos = parts[0].location.copy()
            animate(parts, S.get("action", "idle"), f0, f1)
            set_emotion(parts, emo, f0)
            if S.get("camera") == "back" and STYLE != "paper2d":
                # le perso se retourne vers ce qu'il regarde (télé, fenêtre, lac) : on le voit de dos
                r0 = parts[0]
                if r0.rotation_mode != "XYZ":
                    r0.rotation_mode = "XYZ"  # modèles GLB importés en quaternion
                rz = r0.rotation_euler[2]
                r0.keyframe_insert("rotation_euler", frame=max(0, f0 - 1))
                r0.rotation_euler = (r0.rotation_euler[0], r0.rotation_euler[1], rz + math.pi)
                r0.keyframe_insert("rotation_euler", frame=f0)
                r0.rotation_euler = (r0.rotation_euler[0], r0.rotation_euler[1], rz)
                r0.keyframe_insert("rotation_euler", frame=f1 + 1)
                for fc in _fcurves_of(r0):
                    if fc.data_path == "rotation_euler":
                        for kp in fc.keyframe_points:
                            kp.interpolation = "CONSTANT"
        else:
            animate(parts, "idle", f0, f1)
            set_emotion(parts, emo if emo in ("sad", "cry", "happy", "scared") else "neutral", f0)
    kind = S.get("camera", "medium") if S.get("camera") in CAM_OFF else "medium"
    _act = S.get("action", "idle")
    _show = S.get("show") if isinstance(S.get("show"), dict) else {}
    if (P2_FLOW and _show or _show.get("kind") == "text") and kind in ("face", "close"):
        kind = "medium"  # l'objet ou le grand mot qui illustre la phrase doit être dans le cadre
    if _act == "fall" and kind in ("face", "close", "low", "pov", "back", "medium"):
        kind = "wide"  # le perso bascule vers la caméra : de près, il sort du cadre
    if _act == "sit" and kind in ("face", "close", "low"):
        kind = "medium"
    a, b, aim_z = CAM_OFF[kind]
    if _act == "fall":
        aim_z = 0.9
    elif _act == "sit":
        aim_z = max(0.8, aim_z - 0.5)
    side = -1 if si % 2 else 1
    p0 = focus_pos + Vector((a[0] * side, a[1], a[2]))
    p1 = focus_pos + Vector((b[0] * side, b[1], b[2]))
    tgt = focus_pos + Vector((0, 0, aim_z))
    if kind == "back" and STYLE != "paper2d":
        tgt = focus_pos + Vector((0, 4.5, aim_z))
    tgt1 = focus_pos + Vector((0, 6, 8)) if kind == "tilt" else tgt
    if STYLE == "paper2d":
        try:
            cam_d.dof.focus_distance = max(1.0, (focus_pos + Vector((0, 0, 2.3)) - p0).length)
            cam_d.dof.keyframe_insert("focus_distance", frame=f0)
        except Exception:
            pass
    fe = max(f0 + 1, f1 - 1)
    fs = f0
    if P2_FLOW and _flow_prev is not None:
        # le début du plan sert de transition : la caméra vole depuis la fin du plan précédent
        # même lieu : glissé de caméra ; autre lieu : envolée éclair (2 images) avec un souffle
        _lead = max(2, min(6, (f1 - f0) // 3)) if _flow_prev[3] == S.get("location") else 1
        fs = min(fe - 1, f0 + _lead)
        fs = max(f0, fs)
    _r = look(p0, tgt)
    if P2_FLOW:
        _r.make_compatible(cam.rotation_euler)
    cam.location = p0
    cam.rotation_euler = _r
    cam.keyframe_insert("location", frame=fs)
    cam.keyframe_insert("rotation_euler", frame=fs)
    _r = look(p1, tgt1)
    if P2_FLOW:
        _r.make_compatible(cam.rotation_euler)
    cam.location = p1
    cam.rotation_euler = _r
    cam.keyframe_insert("location", frame=fe)
    cam.keyframe_insert("rotation_euler", frame=fe)
    if P2_FLOW:
        _flow_prev = (fe, p1.copy(), tgt1.copy(), S.get("location"))
    else:
        cut_frames.add(fe)
    if S.get("show"):
        try:
            show_item(S["show"], focus_pos, f0, f1, si)
        except Exception as _e:
            print("show:", _e)

# Stickman : figurants qui réagissent + visages vivants (regard, clignements, bouche sur les mots)
if P2_FLOW:
    _tot = int(scene.frame_end)
    try:
        _outdoor = [(L["id"], LOC_POS[L["id"]]) for L in SPEC.get("locations", []) if L.get("type", "street") not in INDOOR and L["id"] in LOC_POS]
        p2_extras(_outdoor, SHOTS, _tot)
    except Exception as _e:
        print("p2_extras:", _e)
    _word_fr = set()
    for _w in globals().get("WORD_FR") or []:
        try:
            _word_fr.update(range(int(_w[0]), int(_w[1]) + 1))
        except Exception:
            pass
    _talk = {}
    for S in SHOTS:
        _fc = S.get("focus")
        _key = (S.get("location"), _fc)
        if _key in placed:
            _rn = placed[_key][0].name
            _rng = set(range(int(S["f0"]), int(S["f1"]) + 1))
            _talk.setdefault(_rn, set()).update(_rng & _word_fr if _word_fr else set())
    for _i, (_key, _parts) in enumerate(placed.items()):
        try:
            p2_face_life(_parts[0].name, _talk.get(_parts[0].name, set()), _tot, seed=_i + 1)
        except Exception as _e:
            print("p2_face_life:", _e)

# coupes nettes entre plans, mouvement adouci dans chaque plan
act = cam.animation_data.action if cam.animation_data else None
fcurves = getattr(act, "fcurves", None) if act else None
if act is not None and fcurves is None and hasattr(act, "layers"):
    fcurves = []
    for layer in act.layers:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                fcurves.extend(bag.fcurves)
for fc in (fcurves or []):
    for kp in fc.keyframe_points:
        if int(round(kp.co[0])) in cut_frames:
            kp.interpolation = "CONSTANT"
        else:
            kp.interpolation = "BEZIER"


# visages : bascule nette d'une émotion à l'autre
for _e in FACES.values():
    _set_interp(_e, "CONSTANT")

# style 2D × Monde 3D : décor texturé (pavés, bois, enduit, neige) et mise au point nette d'un plan à l'autre
if STYLE == "paper2d":
    p2_apply_textures(dict(_MATS))
    if P2_FLOW:
        try:
            p2_ink_outlines()
        except Exception as _e:
            print("p2_ink_outlines:", _e)
    else:
        try:
            _set_interp(cam_d, "CONSTANT")
        except Exception:
            pass
