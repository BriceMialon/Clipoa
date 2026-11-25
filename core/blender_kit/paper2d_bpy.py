# -*- coding: utf-8 -*-
# Style « Stickman » (ex « 2D × Monde 3D », paper2d) — exécuté DANS Blender, placé AVANT scene_kit_bpy.py par BlenderEngine.
# Ne définit que des fonctions : elles utilisent les globales du kit (scene, cam, FACE_INFO…) au moment de l'appel.
#
# Référence visuelle (TikTok @albertraconte0, « La monnaie des souvenirs », « tout le monde est aveugle sauf moi ») :
#   - personnages DESSIN ANIMÉ 2D : grosse tête ronde claire, grands yeux ronds cerclés d'encre avec pupille noire,
#     joues roses, pas de nez, petit torse trapèze, bras/jambes fins, contour encre épais, couleurs unies,
#     toujours tournés vers la caméra (découpe papier posée dans le monde) ;
#   - décor 3D TEXTURÉ (pavés, bois veiné, enduit, neige), lumière douce de jour, léger flou d'arrière-plan.
import math

try:
    import numpy as _np
except Exception:  # pragma: no cover - numpy est livré avec Blender
    _np = None

P2_INK = (0.12, 0.10, 0.20, 1.0)       # encre bleu-nuit des contours (#1E1A33)
P2_SKIN = (0.97, 0.95, 0.90, 1.0)      # peau blanc cassé des références
P2_LINE = 0.05                          # épaisseur du contour
P2_HEAD_Z = 2.55                        # centre de la tête (les cadrages close/face visent cette hauteur)
P2_HEAD_R = 0.6
P2_CHIBI = False                        # variante Explainer (réf. @rosoai) : grosse tête, nez, pupilles brunes, sourcils
P2_SKIN_MIX = 0.55                      # 2D × 3D : peau tirée vers le blanc ; Explainer : teint gardé
_P2_MATS = {}
P2_CHAR_OBJS = set()
P2_FACES = {}


def _p2_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _p2_mat(rgba):
    key = tuple(round(c, 3) for c in rgba[:3])
    if key in _P2_MATS:
        return _P2_MATS[key]
    m = bpy.data.materials.new("P2_%d" % len(_P2_MATS))
    m.diffuse_color = tuple(_p2_lin(c) for c in rgba[:3]) + (1.0,)
    for attr, val in (("roughness", 1.0), ("metallic", 0.0), ("specular_intensity", 0.0)):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    _P2_MATS[key] = m
    return m


def _p2_mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3)) + (1.0,)


def _p2_poly(pts, rgba, layer, parent, name="P2"):
    """Forme plate dans le plan du perso. pts = [(x, z)] dans le sens trigo ; layer haut = plus près de la caméra."""
    me = bpy.data.meshes.new(name)
    # face toujours tournée vers la caméra (-Y), même avec l'élimination des faces arrière (contours Stickman)
    if sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) < 0:
        pts = list(reversed(pts))
    me.from_pydata([(x, -0.012 * layer, z) for (x, z) in pts], [], [list(range(len(pts)))])
    me.update()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    o.data.materials.append(_p2_mat(rgba))
    o.parent = parent
    P2_CHAR_OBJS.add(o.name)
    return o


def _p2_ell(cx, cz, rx, rz, n=28, a0=0.0, a1=2 * math.pi):
    full = abs(a1 - a0 - 2 * math.pi) < 1e-6
    k = n if full else n + 1
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cz + rz * math.sin(a0 + (a1 - a0) * i / n)) for i in range(k)]


def _p2_capsule(p0, p1, w, n=8):
    (x0, z0), (x1, z1) = p0, p1
    a = math.atan2(z1 - z0, x1 - x0)
    pts = [(x1 + w * math.cos(a - math.pi / 2 + math.pi * i / n), z1 + w * math.sin(a - math.pi / 2 + math.pi * i / n)) for i in range(n + 1)]
    pts += [(x0 + w * math.cos(a + math.pi / 2 + math.pi * i / n), z0 + w * math.sin(a + math.pi / 2 + math.pi * i / n)) for i in range(n + 1)]
    return pts


def _p2_inked_ell(cx, cz, rx, rz, col, layer, parent, line=P2_LINE, n=28):
    _p2_poly(_p2_ell(cx, cz, rx + line, rz + line, n), P2_INK, layer - 0.45, parent, "P2ink")
    return _p2_poly(_p2_ell(cx, cz, rx, rz, n), col, layer, parent)


def _p2_inked_capsule(p0, p1, w, col, layer, parent, line=P2_LINE):
    _p2_poly(_p2_capsule(p0, p1, w + line), P2_INK, layer - 0.45, parent, "P2ink")
    return _p2_poly(_p2_capsule(p0, p1, w), col, layer, parent)


def _p2_stroke(pts, w, col, layer, parent):
    """Trait d'encre (sourcils, bouche) : suite de capsules."""
    for a, b in zip(pts[:-1], pts[1:]):
        _p2_poly(_p2_capsule(a, b, w, n=4), col, layer, parent, "P2line")


def _p2_arc(cx, cz, half_w, depth, n=6):
    """depth > 0 : sourire (creux vers le bas) ; depth < 0 : moue."""
    return [(cx + half_w * (-1 + 2 * k / n), cz - depth * (1 - (-1 + 2 * k / n) ** 2)) for k in range(n + 1)]


def _p2_pivot(name, parent, x, z):
    e = bpy.data.objects.new(name, None)
    scene.collection.objects.link(e)
    e.parent = parent
    e.location = (x, 0.0, z)
    return e


def _p2_billboard(root):
    """La découpe reste toujours face caméra (rotation autour de l'axe vertical seulement)."""
    cam_obj = bpy.data.objects.get("Camera")
    if cam_obj is None:
        return
    c = root.constraints.new("LOCKED_TRACK")
    c.target = cam_obj
    c.track_axis = "TRACK_NEGATIVE_Y"
    c.lock_axis = "LOCK_Z"


def make_char_2d(cid, loc, rot_z=0.0):
    if _p2_stick_on():
        return make_stick_2d(cid, loc, rot_z)
    c = CHARS.get(cid, {})
    root = bpy.data.objects.new("Char_" + cid, None)
    scene.collection.objects.link(root)
    root.location = loc
    sc = float(c.get("scale", 1.0) or 1.0)
    root.scale = (sc, sc, sc)
    skin_in = hex_rgba(c.get("skin"), None)
    skin = _p2_mix(skin_in, (1, 1, 1), P2_SKIN_MIX) if skin_in else P2_SKIN
    shirt = hex_rgba(c.get("shirt"), (0.24, 0.38, 0.62, 1.0))
    pants = hex_rgba(c.get("pants"), (0.20, 0.20, 0.32, 1.0))
    hz, r = P2_HEAD_Z, P2_HEAD_R
    if P2_CHIBI:
        hz, r = 2.55, 0.8
    acc = str(c.get("accessory") or "").lower()
    hstyle = str(c.get("hair_style") or "").lower()

    # jambes (derrière le torse), pivot à la hanche
    legs = []
    for sx in (-1, 1):
        pv = _p2_pivot("Leg", root, sx * 0.15, 1.02)
        _p2_inked_capsule((0, 0), (sx * 0.02, -0.86), 0.065, pants, 1, pv)
        _p2_inked_ell(sx * 0.09, -0.93, 0.15, 0.07, P2_INK, 1.6, pv, line=0.02, n=16)
        legs.append(pv)
    # torse trapèze arrondi
    L = P2_LINE
    body = [(-0.42, 0.98), (0.42, 0.98), (0.36, 1.86), (0.24, 1.98), (-0.24, 1.98), (-0.36, 1.86)]
    ink_body = [(-0.42 - L, 0.98 - L), (0.42 + L, 0.98 - L), (0.36 + L, 1.86 + L * 0.4), (0.24 + L * 0.4, 1.98 + L), (-0.24 - L * 0.4, 1.98 + L), (-0.36 - L, 1.86 + L * 0.4)]
    _p2_poly(ink_body, P2_INK, 1.55, root, "P2ink")
    _p2_poly(body, shirt, 2, root)
    # bras devant le torse, pivot à l'épaule
    arms = []
    for sx in (-1, 1):
        pv = _p2_pivot("Arm", root, sx * 0.33, 1.84)
        _p2_inked_capsule((0, 0), (sx * 0.14, -0.74), 0.06, shirt, 3, pv)
        _p2_inked_ell(sx * 0.15, -0.8, 0.085, 0.085, skin, 3.3, pv, line=0.03, n=14)
        arms.append(pv)
    # tête
    _p2_inked_ell(0, hz, r, r * 0.97, skin, 4, root, n=40)
    hat = c.get("hat")
    has_hat = bool(hat) and str(hat).lower() not in ("none", "", "no")
    hair = c.get("hair")
    if has_hat:
        hc = hex_rgba(hat)
        t = math.asin(0.45)
        cap = _p2_ell(0, hz, r + 0.07, r + 0.07, 24, t, math.pi - t)
        _p2_poly(_p2_ell(0, hz, r + 0.07 + L, r + 0.07 + L, 24, t - 0.04, math.pi - t + 0.04), P2_INK, 6.5, root, "P2ink")
        _p2_poly(cap, hc, 7, root)
        band = [(-r + 0.02, hz + 0.27), (r - 0.02, hz + 0.27), (r - 0.0, hz + 0.42), (-r + 0.0, hz + 0.42)]
        _p2_poly([(x + (L if x > 0 else -L), z + (L if z > hz + 0.35 else -L)) for x, z in band], P2_INK, 7.4, root, "P2ink")
        _p2_poly(band, _p2_mix(hc, (0, 0, 0), 0.15), 7.8, root)
        _p2_inked_ell(0, hz + r + 0.16, 0.12, 0.12, _p2_mix(hc, (1, 1, 1), 0.35), 7.2, root, line=0.035, n=16)
    elif hstyle == "wig":
        # perruque d'époque : boucles blanches sur les côtés + dessus bouffant
        wc = hex_rgba(hair, (0.95, 0.95, 0.93, 1.0)) if hair else (0.95, 0.95, 0.93, 1.0)
        t = math.asin(0.35)
        _p2_poly(_p2_ell(0, hz, r + L + 0.04, r + L + 0.04, 28, t - 0.05, math.pi - t + 0.05), P2_INK, 6.5, root, "P2ink")
        _p2_poly(_p2_ell(0, hz, r + 0.04, r + 0.04, 28, t, math.pi - t), wc, 7, root)
        for sx in (-1, 1):
            for k in range(2):
                _p2_inked_ell(sx * (r + 0.02), hz - 0.05 - k * 0.24, 0.16, 0.13, wc, 3.8 + k * 0.1, root, line=0.035, n=16)
    elif hair and str(hair).lower() not in ("none", "", "bald", "chauve") and hstyle != "bald":
        hc = hex_rgba(hair)
        t = math.asin(0.42)
        _p2_poly(_p2_ell(0, hz, r + L + 0.015, r * 0.97 + L + 0.015, 28, t - 0.05, math.pi - t + 0.05), P2_INK, 6.5, root, "P2ink")
        _p2_poly(_p2_ell(0, hz, r + 0.015, r * 0.97 + 0.015, 28, t, math.pi - t), hc, 7, root)
        if P2_CHIBI:
            # mèche rebelle sur le dessus (comme le héros de la vidéo cuisine)
            _p2_inked_capsule((0.02, hz + r * 0.95), (0.1, hz + r * 1.22), 0.05, hc, 7.2, root, line=0.03)
        if hstyle == "long" or str(c.get("gender", "")).lower() in ("f", "femme", "female", "fille", "girl"):
            for sx in (-1, 1):
                _p2_inked_capsule((sx * (r - 0.06), hz + 0.1), (sx * (r - 0.02), hz - 0.55), 0.12, hc, 3.8, root)
    if acc == "apron":
        ac = (0.95, 0.93, 0.88, 1.0)
        _p2_poly([(-0.27, 1.0), (0.27, 1.0), (0.24, 1.62), (-0.24, 1.62)], P2_INK, 2.4, root, "P2ink")
        _p2_poly([(-0.24, 1.03), (0.24, 1.03), (0.21, 1.59), (-0.21, 1.59)], ac, 2.6, root)
    if acc == "glasses":
        # lunettes rondes (anneaux d'encre devant les yeux)
        for sx in (-1, 1):
            cx_g = sx * (0.26 if P2_CHIBI else 0.22)
            ring = _p2_ell(cx_g, hz + (-0.02 if P2_CHIBI else 0.0), 0.25 if P2_CHIBI else 0.21, 0.23 if P2_CHIBI else 0.2, 24)
            _p2_stroke(ring + [ring[0]], 0.028, P2_INK, 6.8, root)
        _p2_stroke([(-0.05, hz + 0.03), (0.05, hz + 0.03)], 0.025, P2_INK, 6.8, root)
    FACE_INFO[root.name] = (root, (0.0, hz), r)
    _p2_billboard(root)
    return root, arms[0], arms[1], legs[0], legs[1]


def build_face_2d(rootname, emotion):
    """Visage des références : grands yeux blancs cerclés d'encre, pupille noire + reflet, joues roses, bouche fine."""
    if _p2_stick_on():
        return build_stick_face(rootname, emotion)
    root, (cx, hz), r = FACE_INFO[rootname]
    face = bpy.data.objects.new("Face_" + emotion, None)
    scene.collection.objects.link(face)
    face.parent = root
    big = emotion in ("surprised", "scared")
    er = (0.2 if P2_CHIBI else 0.17) * (1.18 if big else 1.0)
    pr = (0.115 if P2_CHIBI else 0.08) * (0.55 if big else 1.0)
    ex, ez = (0.26, hz - 0.02) if P2_CHIBI else (0.22, hz + 0.0)
    pupil = (0.24, 0.14, 0.09, 1.0) if P2_CHIBI else (0.04, 0.03, 0.06, 1.0)
    look_dz = -0.04 if emotion in ("sad", "cry") else 0.0
    for sx in (-1, 1):
        x = cx + sx * ex
        _p2_poly(_p2_ell(x, ez, er + (0.025 if P2_CHIBI else 0.035), er * 1.08 + (0.025 if P2_CHIBI else 0.035), 24), P2_INK, 5, face, "P2ink")
        _p2_poly(_p2_ell(x, ez, er, er * 1.08, 24), (1.0, 1.0, 1.0, 1.0), 5.4, face)
        px = x
        _p2_poly(_p2_ell(px, ez + look_dz, pr, pr * 1.1, 16), pupil, 5.8, face)
        _p2_poly(_p2_ell(px - 0.025, ez + look_dz + 0.03, pr * 0.32, pr * 0.32, 10), (1.0, 1.0, 1.0, 1.0), 6.1, face)
        # joues roses
        _p2_poly(_p2_ell(cx + sx * (0.46 if P2_CHIBI else 0.36), hz - (0.28 if P2_CHIBI else 0.2), 0.11, 0.065, 16), (0.98, 0.64, 0.68, 1.0), 5.2, face)
        # sourcils
        bz = ez + er * 1.08 + 0.08 + (0.04 if big else 0.0)
        inner, outer = cx + sx * 0.1, cx + sx * 0.34
        if emotion in ("sad", "cry", "scared"):
            _p2_stroke([(inner, bz + 0.05), (outer, bz - 0.03)], 0.022, P2_INK, 6.3, face)
        elif emotion == "angry":
            _p2_stroke([(inner, bz - 0.07), (outer, bz + 0.03)], 0.028, P2_INK, 6.3, face)
        elif emotion == "surprised" or P2_CHIBI:
            _p2_stroke(_p2_arc((inner + outer) / 2, bz + 0.03, abs(outer - inner) / 2, 0.04, 4), 0.022, P2_INK, 6.3, face)
        if emotion == "cry":
            _p2_poly(_p2_capsule((x + sx * 0.05, ez - er), (x + sx * 0.07, hz - 0.42), 0.035), (0.55, 0.8, 1.0, 1.0), 6.4, face)
    mz = hz - (0.4 if P2_CHIBI else 0.32)
    w = 0.02
    if P2_CHIBI:
        _p2_stroke(_p2_arc(cx, hz - 0.2, 0.05, -0.03, 3), 0.018, P2_INK, 5.7, face)  # petit nez
    if emotion == "happy":
        _p2_poly(_p2_ell(cx, mz + 0.03, 0.13, 0.1, 18, math.pi, 2 * math.pi), (0.45, 0.12, 0.18, 1.0), 5.5, face)
        _p2_stroke(_p2_arc(cx, mz + 0.03, 0.13, 0.0, 2), w, P2_INK, 5.7, face)
    elif emotion in ("sad", "cry"):
        _p2_stroke(_p2_arc(cx, mz - 0.03, 0.1, -0.05, 4), w, P2_INK, 5.7, face)
    elif emotion == "surprised":
        _p2_poly(_p2_ell(cx, mz - 0.02, 0.06, 0.08, 14), P2_INK, 5.7, face)
    elif emotion == "scared":
        _p2_stroke([(cx - 0.1, mz), (cx - 0.05, mz + 0.025), (cx, mz), (cx + 0.05, mz + 0.025), (cx + 0.1, mz)], w, P2_INK, 5.7, face)
    elif emotion == "angry":
        _p2_stroke(_p2_arc(cx, mz - 0.02, 0.09, -0.025, 3), w * 1.2, P2_INK, 5.7, face)
    elif emotion == "smirk":
        _p2_stroke([(cx - 0.09, mz), (cx + 0.04, mz), (cx + 0.11, mz + 0.05)], w, P2_INK, 5.7, face)
    else:
        _p2_stroke(_p2_arc(cx, mz, 0.08, 0.025, 4), w, P2_INK, 5.7, face)
    return face


def p2_limb_rot(a):
    """Rotation d'un membre dans le plan du dessin (axe Y) au lieu de l'axe X des persos 3D."""
    return (0.0, a, 0.0)


# ---------------------------------------------------------------- décor : textures procédurales (Workbench « TEXTURE »)
_P2_PATTERNS = {}
P2_TEX_N = 256


def _p2_noise(rng, scale):
    n = P2_TEX_N
    w = rng.standard_normal((n, n))
    fy = _np.fft.fftfreq(n)[:, None]
    fx = _np.fft.fftfreq(n)[None, :]
    filt = _np.exp(-((_np.sqrt(fx * fx + fy * fy) * scale) ** 2))
    out = _np.real(_np.fft.ifft2(_np.fft.fft2(w) * filt))
    return (out - out.mean()) / (out.std() + 1e-6)


def _p2_pattern(kind):
    if kind in _P2_PATTERNS:
        return _P2_PATTERNS[kind]
    n = P2_TEX_N
    rng = _np.random.default_rng(11 + len(kind))
    yy, xx = _np.mgrid[0:n, 0:n].astype(_np.float32)
    if kind == "cobble":
        k = 44
        pts = rng.uniform(0, n, (k, 2)).astype(_np.float32)
        dx = _np.abs(xx[..., None] - pts[:, 0])
        dy = _np.abs(yy[..., None] - pts[:, 1])
        dx = _np.minimum(dx, n - dx)
        dy = _np.minimum(dy, n - dy)
        d = _np.sqrt(dx * dx + dy * dy)
        idx = _np.argmin(d, axis=2)
        two = _np.partition(d, 1, axis=2)
        edge = two[..., 1] - two[..., 0]
        tint = rng.uniform(0.82, 1.1, k)[idx]
        bevel = _np.clip(edge / 7.0, 0, 1) ** 0.5
        p = tint * (0.72 + 0.3 * bevel) + 0.05 * _p2_noise(rng, 1.5)
        p = _np.where(edge < 2.2, 0.5, p)
    elif kind == "wood":
        row = (yy // 64).astype(int)
        tint = rng.uniform(0.86, 1.08, 8)[row % 8]
        grain = 0.08 * _np.sin(yy * 0.55 + 5.0 * _p2_noise(rng, 24)) + 0.05 * _p2_noise(rng, 2)
        p = tint * (0.95 + grain)
        p = _np.where((yy % 64) < 2.5, 0.55, p)
        p = _np.where(((xx + row * 97) % n) < 2.5, 0.6, p)
    elif kind == "grass":
        p = 1.0 + 0.1 * _p2_noise(rng, 1.2) + 0.08 * _p2_noise(rng, 10)
    elif kind == "snow":
        p = _np.minimum(1.0 + 0.025 * _p2_noise(rng, 6) + 0.02 * _p2_noise(rng, 1.2), 1.04)
    else:  # enduit / plâtre / peinture
        p = 1.0 + 0.05 * _p2_noise(rng, 14) + 0.025 * _p2_noise(rng, 1.5)
    _P2_PATTERNS[kind] = _np.clip(p, 0.0, 1.3).astype(_np.float32)
    return _P2_PATTERNS[kind]


P2_TILE = {"cobble": 1.7, "wood": 1.3, "grass": 2.2, "snow": 3.0, "plaster": 2.6}


def _p2_kind_for(rgba):
    r, g, b = rgba[:3]
    mx, mn = max(r, g, b), min(r, g, b)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = (mx - mn) / (mx + 1e-6)
    if r > 0.9 and g > 0.7 and b < 0.65:
        return None  # lumières / fenêtres allumées : unies
    if lum > 0.86 and sat < 0.1:
        return "snow"
    if r >= g >= b and (r - b) > 0.14 and lum < 0.62 and sat > 0.2:
        return "wood"
    if g > r * 1.12 and g > b * 1.12 and sat > 0.25:
        return "grass"
    if sat < 0.16 and lum < 0.62:
        return "cobble"
    return "plaster"


def p2_apply_textures(mats_by_rgba):
    """Donne une texture (pavés, bois, enduit, herbe, neige) à chaque couleur du décor + UV projetées en monde."""
    if _np is None:
        return
    tex_mats = {}
    for rgba, m in mats_by_rgba.items():
        kind = _p2_kind_for(rgba)
        if not kind:
            continue
        try:
            pat = _p2_pattern(kind)
            n = P2_TEX_N
            arr = _np.ones((n, n, 4), dtype=_np.float32)
            for ch in range(3):
                arr[..., ch] = _np.clip(rgba[ch] * pat, 0.0, 1.0)
            img = bpy.data.images.new("P2tex_%s_%d" % (kind, len(tex_mats)), n, n, alpha=False)
            img.pixels.foreach_set(arr.ravel())
            img.pack()
            try:
                m.use_nodes = True
            except Exception:
                pass
            nt = m.node_tree
            if nt is None:
                continue
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.interpolation = "Linear"
            bsdf = next((nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED"), None)
            if bsdf is not None:
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            nt.nodes.active = tex
            tex_mats[m.name] = P2_TILE.get(kind, 2.0)
        except Exception as exc:  # une texture ratée ne doit jamais casser le rendu
            print("P2 texture:", exc)
    if not tex_mats:
        return
    done = set()
    for o in list(scene.objects):
        if o.type != "MESH" or o.name in P2_CHAR_OBJS or o.data.name in done:
            continue
        me = o.data
        names = [ms.name if ms else "" for ms in me.materials]
        if not any(nm in tex_mats for nm in names):
            continue
        done.add(me.name)
        try:
            uvl = me.uv_layers.active or me.uv_layers.new(name="UVMap")
            mw = o.matrix_world
            rot = mw.to_3x3()
            for poly in me.polygons:
                nm = names[poly.material_index] if poly.material_index < len(names) else ""
                tile = tex_mats.get(nm, 2.0)
                nrm = rot @ poly.normal
                ax = max(range(3), key=lambda i: abs(nrm[i]))
                for li in poly.loop_indices:
                    v = mw @ me.vertices[me.loops[li].vertex_index].co
                    u, w = (v.x, v.y) if ax == 2 else ((v.x, v.z) if ax == 1 else (v.y, v.z))
                    uvl.data[li].uv = (u / tile, w / tile)
        except Exception as exc:
            print("P2 uv:", exc)


def p2_set_emotion(root, emotion, frame):
    """Affiche le visage de l'émotion voulue à partir de `frame` (Explainer ; le kit 3D a son propre set_emotion)."""
    rn = root.name
    if rn not in FACE_INFO:
        return
    key = (rn, emotion)
    if key not in P2_FACES:
        e = build_face_2d(rn, emotion)
        e.scale = (0, 0, 0)
        e.keyframe_insert("scale", frame=0)
        P2_FACES[key] = e
    for (r2, emo2), e in P2_FACES.items():
        if r2 != rn:
            continue
        e.scale = (1, 1, 1) if emo2 == emotion else (0, 0, 0)
        e.keyframe_insert("scale", frame=frame)
        for fc in (_p2_fcurves(e)):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def _p2_fcurves(obj):
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


# ======================================================================================================
# Style « Stickman » (id 2d_monde_3d, rendu paper2d) — d'après le pipeline 2.5D stickman (33 000 images analysées) :
#   - tête blanche ovale « haricot », yeux = points noirs, sourcils expressifs, bouche qui parle sur la voix ;
#   - petit torse coloré (pull), bras et jambes = traits d'encre fins ; visage toujours blanc pur ;
#   - visage vivant : regard qui bouge toutes les 0,3-0,8 s, clignements, bouche synchronisée sur les mots ;
#   - décor 3D cerné d'un contour encre épais (coque inversée), décor jamais mort (fumée, oiseaux, poussière),
#     figurants qui réagissent.
# La variante Explainer (P2_CHIBI) garde l'ancien dessin.
# ======================================================================================================
P2_STICK = True
P2_STICK_HEAD = (0.58, 0.70)            # demi-largeur, demi-hauteur de la tête ovale
P2_FACEPARTS = {}                        # nom du perso -> [(yeux, bouche fermée, bouche ouverte, (x, z) des yeux)]
P2_INK_SKIP = ("Flake", "P2live", "Sky")


def _p2_stick_on():
    return P2_STICK and not P2_CHIBI


def make_stick_2d(cid, loc, rot_z=0.0):
    c = CHARS.get(cid, {})
    root = bpy.data.objects.new("Char_" + cid, None)
    scene.collection.objects.link(root)
    root.location = loc
    sc = float(c.get("scale", 1.0) or 1.0)
    root.scale = (sc, sc, sc)
    shirt = hex_rgba(c.get("shirt"), (0.24, 0.38, 0.62, 1.0))
    pants = hex_rgba(c.get("pants"), None)
    hz = P2_HEAD_Z
    rx, rz = P2_STICK_HEAD
    L = P2_LINE
    acc = str(c.get("accessory") or "").lower()
    hstyle = str(c.get("hair_style") or "").lower()
    # jambes = traits d'encre, pivot à la hanche
    legs = []
    for sx in (-1, 1):
        pv = _p2_pivot("Leg", root, sx * 0.11, 1.0)
        _p2_poly(_p2_capsule((0, 0), (sx * 0.03, -0.9), 0.034), P2_INK, 1, pv, "P2ink")
        _p2_poly(_p2_ell(sx * 0.09, -0.94, 0.11, 0.05, 14), P2_INK, 1.2, pv, "P2ink")
        legs.append(pv)
    # petit torse arrondi (pull), éventuel bas de pantalon
    if pants:
        _p2_inked_capsule((0, 1.02), (0, 1.12), 0.24, pants, 1.8, root)
    _p2_inked_capsule((0, 1.18), (0, 1.62), 0.27, shirt, 2, root)
    if acc == "apron":
        _p2_inked_capsule((0, 1.12), (0, 1.48), 0.17, (0.95, 0.93, 0.88, 1.0), 2.4, root, line=0.03)
    # bras = traits d'encre, pivot à l'épaule, petite main ronde
    arms = []
    for sx in (-1, 1):
        pv = _p2_pivot("Arm", root, sx * 0.22, 1.72)
        _p2_poly(_p2_capsule((0, 0), (sx * 0.17, -0.7), 0.032), P2_INK, 3, pv, "P2ink")
        _p2_poly(_p2_ell(sx * 0.18, -0.74, 0.06, 0.06, 12), P2_INK, 3.1, pv, "P2ink")
        arms.append(pv)
    # tête ovale blanc pur, contour épais
    _p2_poly(_p2_ell(0, hz, rx + 0.06, rz + 0.06, 44), P2_INK, 3.55, root, "P2ink")
    _p2_poly(_p2_ell(0, hz, rx, rz, 44), (1.0, 1.0, 1.0, 1.0), 4, root)
    hat = c.get("hat")
    has_hat = bool(hat) and str(hat).lower() not in ("none", "", "no")
    hair = c.get("hair")
    if has_hat:
        # bonnet / chapeau posé sur le haut de la tête
        hc = hex_rgba(hat)
        hcz = hz + 0.2
        hr = rx + 0.05
        t = math.asin(0.35)
        _p2_poly(_p2_ell(0, hcz, hr + L, rz * 0.82 + L, 28, t - 0.05, math.pi - t + 0.05), P2_INK, 6.5, root, "P2ink")
        _p2_poly(_p2_ell(0, hcz, hr, rz * 0.82, 28, t, math.pi - t), hc, 7, root)
        band_z = hcz + 0.35 * rz * 0.82
        band = [(-hr - 0.04, band_z - 0.17), (hr + 0.04, band_z - 0.17), (hr + 0.04, band_z), (-hr - 0.04, band_z)]
        _p2_poly([(x + (L if x > 0 else -L), z + (L if z > band_z - 0.08 else -L)) for x, z in band], P2_INK, 7.4, root, "P2ink")
        _p2_poly(band, _p2_mix(hc, (0, 0, 0), 0.18), 7.8, root)
        if hstyle != "bald":
            _p2_inked_ell(0, hcz + rz * 0.82 + 0.1, 0.11, 0.11, _p2_mix(hc, (1, 1, 1), 0.35), 7.2, root, line=0.035, n=16)
    elif hair and str(hair).lower() not in ("none", "", "bald", "chauve") and hstyle != "bald":
        hc = hex_rgba(hair)
        t = math.asin(0.5)
        _p2_poly(_p2_ell(0, hz, rx + L + 0.02, rz + L + 0.02, 28, t - 0.05, math.pi - t + 0.05), P2_INK, 6.5, root, "P2ink")
        _p2_poly(_p2_ell(0, hz, rx + 0.02, rz + 0.02, 28, t, math.pi - t), hc, 7, root)
        if hstyle == "long" or str(c.get("gender", "")).lower() in ("f", "femme", "female", "fille", "girl"):
            for sx in (-1, 1):
                _p2_inked_capsule((sx * (rx - 0.04), hz + 0.15), (sx * (rx + 0.02), hz - 0.6), 0.11, hc, 3.8, root)
    if acc == "glasses":
        for sx in (-1, 1):
            ring = _p2_ell(sx * 0.2, hz + 0.08, 0.15, 0.14, 22)
            _p2_stroke(ring + [ring[0]], 0.026, P2_INK, 6.8, root)
        _p2_stroke([(-0.05, hz + 0.1), (0.05, hz + 0.1)], 0.024, P2_INK, 6.8, root)
    FACE_INFO[root.name] = (root, (0.0, hz), rx)
    _p2_billboard(root)
    return root, arms[0], arms[1], legs[0], legs[1]


def build_stick_face(rootname, emotion):
    """Visage stickman : yeux points (dans un groupe qu'on peut faire bouger / cligner), sourcils, bouche fermée + ouverte."""
    root, (cx, hz), r = FACE_INFO[rootname]
    face = bpy.data.objects.new("Face_" + emotion, None)
    scene.collection.objects.link(face)
    face.parent = root
    ink = P2_INK
    ez = hz + 0.1
    eyes = _p2_pivot("Eyes", face, cx, ez)
    big = emotion in ("surprised", "scared")
    erx, erz = (0.085, 0.115) if big else (0.062, 0.088)
    for sx in (-1, 1):
        if emotion == "happy":
            # yeux plissés de joie : petits arcs
            _p2_stroke(_p2_arc(sx * 0.19, 0.0, 0.07, -0.05, 4), 0.026, ink, 5.8, eyes)
        else:
            _p2_poly(_p2_ell(sx * 0.19, 0.0, erx, erz, 16), ink, 5.8, eyes, "P2ink")
            if big:
                _p2_poly(_p2_ell(sx * 0.19 - 0.025, 0.035, 0.022, 0.022, 8), (1.0, 1.0, 1.0, 1.0), 6.0, eyes)
        if emotion == "cry":
            _p2_poly(_p2_capsule((sx * 0.22, -0.1), (sx * 0.24, -0.42), 0.032), (0.55, 0.8, 1.0, 1.0), 6.2, face)
    # sourcils (sur le visage, ne clignent pas)
    bz = ez + 0.2 + (0.06 if big else 0.0)
    for sx in (-1, 1):
        inner, outer = cx + sx * 0.09, cx + sx * 0.3
        if emotion in ("sad", "cry", "scared"):
            _p2_stroke([(inner, bz + 0.05), (outer, bz - 0.04)], 0.024, ink, 6.3, face)
        elif emotion == "angry":
            _p2_stroke([(inner, bz - 0.07), (outer, bz + 0.04)], 0.03, ink, 6.3, face)
        elif emotion in ("surprised", "happy"):
            _p2_stroke(_p2_arc((inner + outer) / 2, bz + 0.03, abs(outer - inner) / 2, 0.05, 4), 0.024, ink, 6.3, face)
        elif emotion == "smirk" and sx > 0:
            _p2_stroke([(inner, bz + 0.04), (outer, bz + 0.07)], 0.024, ink, 6.3, face)
        else:
            _p2_stroke([(inner, bz), (outer, bz + 0.015)], 0.022, ink, 6.3, face)
    mz = hz - 0.27
    mouth = _p2_pivot("Mouth", face, cx, mz)
    w = 0.024
    if emotion == "happy":
        _p2_poly(_p2_ell(0, 0.03, 0.16, 0.12, 18, math.pi, 2 * math.pi), (0.25, 0.08, 0.1, 1.0), 5.5, mouth)
        _p2_poly([(-0.12, 0.03), (0.12, 0.03), (0.11, -0.015), (-0.11, -0.015)], (1.0, 1.0, 1.0, 1.0), 5.6, mouth)
        _p2_stroke(_p2_arc(0, 0.03, 0.16, 0.0, 2), w, ink, 5.7, mouth)
    elif emotion in ("sad", "cry"):
        _p2_stroke(_p2_arc(0, -0.03, 0.11, -0.06, 4), w, ink, 5.7, mouth)
    elif emotion == "surprised":
        _p2_poly(_p2_ell(0, -0.02, 0.06, 0.085, 14), ink, 5.7, mouth, "P2ink")
    elif emotion == "scared":
        # dents serrées (comme le perso au chapeau de la référence)
        _p2_poly([(-0.13, 0.04), (0.13, 0.04), (0.13, -0.05), (-0.13, -0.05)], ink, 5.5, mouth, "P2ink")
        _p2_poly([(-0.11, 0.025), (0.11, 0.025), (0.11, -0.035), (-0.11, -0.035)], (1.0, 1.0, 1.0, 1.0), 5.6, mouth)
        for k in (-0.055, 0.0, 0.055):
            _p2_stroke([(k, 0.025), (k, -0.035)], 0.01, ink, 5.7, mouth)
        _p2_stroke([(-0.11, -0.005), (0.11, -0.005)], 0.01, ink, 5.7, mouth)
    elif emotion == "angry":
        _p2_stroke(_p2_arc(0, -0.02, 0.1, -0.03, 3), w * 1.2, ink, 5.7, mouth)
    elif emotion == "smirk":
        _p2_stroke([(-0.1, 0.0), (0.04, 0.0), (0.12, 0.05)], w, ink, 5.7, mouth)
    else:
        _p2_stroke(_p2_arc(0, 0.0, 0.09, 0.03, 4), w, ink, 5.7, mouth)
    # bouche ouverte (parole) : affichée en alternance pendant les mots
    mopen = _p2_pivot("MouthOpen", face, cx, mz)
    oh = 0.1 if emotion in ("surprised", "scared") else 0.075
    _p2_poly(_p2_ell(0, -0.01, 0.1, oh, 16), ink, 5.75, mopen, "P2ink")
    _p2_poly(_p2_ell(0, -0.01 - oh * 0.45, 0.06, oh * 0.4, 12), (0.85, 0.35, 0.4, 1.0), 5.85, mopen)
    mopen.scale = (0, 0, 0)
    P2_FACEPARTS.setdefault(rootname, []).append((eyes, mouth, mopen, (cx, ez)))
    return face


def _p2_key_const(obj, path, frame):
    obj.keyframe_insert(path, frame=frame)


def p2_face_life(rootname, talk_frames, f_end, seed=1):
    """Regard qui change toutes les 0,3-0,8 s, clignements, bouche qui s'ouvre/se ferme sur les mots."""
    parts = P2_FACEPARTS.get(rootname) or []
    if not parts:
        return
    rng = random.Random(seed)
    fps = max(1, int(scene.render.fps or 12))
    # regard + micro-mouvements
    f = 1
    while f < f_end:
        dx = rng.choice((-0.06, -0.03, 0.0, 0.03, 0.06))
        dz = rng.choice((-0.02, 0.0, 0.0, 0.02))
        for eyes, _m, _o, (x0, z0) in parts:
            eyes.location = (x0 + dx, 0.0, z0 + dz)
            _p2_key_const(eyes, "location", f)
        f += rng.randint(max(2, int(0.3 * fps)), max(3, int(0.8 * fps)))
    # clignements (2 images yeux fermés) toutes les ~2-4 s
    f = rng.randint(fps, 3 * fps)
    for eyes, _m, _o, _xz in parts:
        eyes.scale = (1, 1, 1)
        _p2_key_const(eyes, "scale", 1)
    while f < f_end - 2:
        for eyes, _m, _o, _xz in parts:
            eyes.scale = (1, 1, 0.12)
            _p2_key_const(eyes, "scale", f)
            eyes.scale = (1, 1, 1)
            _p2_key_const(eyes, "scale", f + 2)
        f += rng.randint(2 * fps, 4 * fps)
    # bouche : ouverte / fermée toutes les 2 images pendant les mots
    state = None
    for fr in range(1, f_end + 1):
        talking = fr in talk_frames
        want = bool(talking and ((fr // 2) % 2 == 0))
        if want != state:
            for _e, mouth, mopen, _xz in parts:
                mouth.scale = (0, 0, 0) if want else (1, 1, 1)
                mopen.scale = (1, 1, 1) if want else (0, 0, 0)
                _p2_key_const(mouth, "scale", fr)
                _p2_key_const(mopen, "scale", fr)
            state = want
    for eyes, mouth, mopen, _xz in parts:
        for o in (eyes, mouth, mopen):
            for fc in _p2_fcurves(o):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"


def _p2_loop(o, path, index, v0, v1, f0, period, interp="LINEAR"):
    setattr_v = getattr(o, path)
    setattr_v[index] = v0
    o.keyframe_insert(path, index=index, frame=f0)
    setattr_v[index] = v1
    o.keyframe_insert(path, index=index, frame=f0 + period)
    for fc in _p2_fcurves(o):
        if fc.data_path == path and fc.array_index == index:
            for kp in fc.keyframe_points:
                kp.interpolation = interp
            if not fc.modifiers:
                try:
                    fc.modifiers.new("CYCLES")
                except Exception:
                    pass


def p2_alive(ox, indoor, slots, seed=3):
    """Le décor ne s'arrête jamais : fumée de cheminées et oiseaux dehors, poussière dorée dedans."""
    rng = random.Random(seed + int(ox))
    if indoor:
        for k in range(22):
            o = sphere((ox + rng.uniform(-5, 5), rng.uniform(0.5, 5.5), rng.uniform(0.6, 4.5)), rng.uniform(0.025, 0.05), (1.0, 0.93, 0.7, 1.0), seg=8)
            o.name = "P2live_dust"
            z = o.location.z
            _p2_loop(o, "location", 2, z, z + rng.uniform(0.6, 1.2), 1 - rng.randint(0, 60), rng.randint(60, 110), "BEZIER")
            x = o.location.x
            _p2_loop(o, "location", 0, x, x + rng.uniform(-0.5, 0.5), 1 - rng.randint(0, 60), rng.randint(70, 130), "BEZIER")
        return
    # fumée : bouffées grises qui montent et grossissent en boucle
    spots = [s for s in slots if abs(s[0] - ox) > 5.5][:3] or [(ox + rng.choice((-1, 1)) * 8.0, 9.0)]
    for (sx_, sy_) in spots[:3]:
        for k in range(5):
            o = sphere((sx_, sy_, 6.0), 0.45, (0.88, 0.88, 0.9, 1.0), seg=10)
            o.name = "P2live_smoke"
            per = 40
            ph = 1 - k * (per // 5)
            _p2_loop(o, "location", 2, 5.6, 10.0, ph, per)
            _p2_loop(o, "location", 0, sx_, sx_ + 1.2, ph, per)
            for i in range(3):
                _p2_loop(o, "scale", i, 0.4, 1.9, ph, per)
    # oiseaux : petits V d'encre qui traversent le ciel en battant des ailes
    for k in range(5):
        b = bpy.data.objects.new("P2live_bird", None)
        scene.collection.objects.link(b)
        y = rng.uniform(14, 26)
        z = rng.uniform(7.5, 12)
        b.location = (ox - 30, y, z)
        for sx in (-1, 1):
            _p2_poly(_p2_capsule((0, 0), (sx * 0.45, 0.22), 0.06, n=4), P2_INK, 0, b, "P2live_wing")
        per = rng.randint(140, 220)
        _p2_loop(b, "location", 0, ox - 30, ox + 30, 1 - rng.randint(0, per), per)
        _p2_loop(b, "scale", 2, 1.0, -0.6, 1 - rng.randint(0, 4), 3, "BEZIER")


def p2_extras(loc_ids_outdoor, shots, total_frames):
    """Figurants stickman à l'arrière-plan : ils regardent, clignent et réagissent aux moments forts."""
    rng = random.Random(11)
    shirts = ("#E8833A", "#3F7CC4", "#6BAF5B", "#C9504E", "#8A63B8", "#E0B43C", "#4A9A9A")
    hats = ("#2E3F66", "#C9504E", "none", "none", "#E0B43C")
    for lid, ox in loc_ids_outdoor:
        made = []
        for k, (x, y) in enumerate(((-4.6, 7.2), (4.9, 8.4), (-6.8, 10.5))):
            cid = "_extra_%s_%d" % (lid, k)
            CHARS[cid] = {"id": cid, "shirt": rng.choice(shirts), "hat": rng.choice(hats), "hair": "#3A2A20", "scale": 0.95}
            parts = make_char(cid, (ox + x, y, 0.0))
            animate(parts, "idle", 1, total_frames)
            set_emotion(parts, "neutral", 1)
            made.append(parts)
        for S in shots:
            if S.get("location") != lid:
                continue
            emo = S.get("emotion", "neutral")
            react = emo if emo in ("surprised", "scared", "happy", "sad") else "neutral"
            for parts in made:
                set_emotion(parts, react, int(S["f0"]))
        for k, parts in enumerate(made):
            p2_face_life(parts[0].name, set(), total_frames, seed=100 + k + int(ox))


def p2_ink_outlines():
    """Contour encre épais sur le décor 3D (coque inversée), pour coller au trait des persos."""
    from mathutils import Matrix
    try:
        scene.display.shading.show_backface_culling = True  # la coque inversée n'est visible que sur les bords
    except Exception:
        pass
    ink = bpy.data.materials.new("P2_InkHull")
    ink.diffuse_color = (0.008, 0.007, 0.012, 1.0)
    try:
        ink.use_backface_culling = True
    except Exception:
        pass
    for o in list(scene.objects):
        if o.type != "MESH" or o.name in P2_CHAR_OBJS or o.name.startswith(P2_INK_SKIP):
            continue
        if o.animation_data is not None or any(m and _is_glow(tuple(m.diffuse_color)) for m in o.data.materials):
            continue
        dims = o.dimensions
        if max(dims) > 40.0 or max(dims) < 0.05:
            continue
        if o.data.users > 1:
            continue
        if not o.children and tuple(o.scale) != (1.0, 1.0, 1.0):
            o.data.transform(Matrix.Diagonal((o.scale[0], o.scale[1], o.scale[2], 1.0)))
            o.scale = (1.0, 1.0, 1.0)
        if ink.name not in [m.name for m in o.data.materials if m]:
            o.data.materials.append(ink)
        sc = max(1e-3, (abs(o.scale[0]) + abs(o.scale[1]) + abs(o.scale[2])) / 3.0)
        thick = max(0.025, min(0.07, 0.02 + 0.012 * max(dims))) / sc
        md = o.modifiers.new("P2Ink", "SOLIDIFY")
        md.thickness = thick
        md.offset = 1.0
        md.use_flip_normals = True
        md.use_rim = False
        md.material_offset = len(o.data.materials)
