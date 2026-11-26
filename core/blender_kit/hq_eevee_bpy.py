# -*- coding: utf-8 -*-
# Rendu « Haute qualité » des styles Blender (EEVEE) — ajouté APRÈS le kit par BlenderEngine.create_scene_from_spec.
# ===== Rendu HAUTE QUALITÉ (EEVEE) : vraie lumière, ombres douces, occlusion ; ajouté par ClipRoll si QUALITY == "hq" =====
def _clipoa_hq():
    import bpy as _b
    sc = _b.context.scene
    for _eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = _eng
            break
        except Exception:
            continue
    if not sc.render.engine.startswith("BLENDER_EEVEE"):
        return
    sc.render.resolution_x, sc.render.resolution_y = 720, 1280
    ee = sc.eevee
    for _a, _v in (("taa_render_samples", 24), ("use_gtao", True), ("gtao_distance", 1.2), ("use_shadows", True),
                   ("use_raytracing", False), ("shadow_ray_count", 1), ("shadow_step_count", 4),
                   ("use_soft_shadows", True), ("use_bloom", True), ("bloom_intensity", 0.04)):
        try:
            setattr(ee, _a, _v)
        except Exception:
            pass
    try:
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = 0.0
    except Exception:
        pass
    _style = str(globals().get("STYLE", ""))
    flat_chars = _style in ("paper2d", "explainer2d", "flat_vector")

    def _lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def _rgb(m):
        return tuple(m.diffuse_color[:3])

    def _emission(m, strength=1.0):
        m.use_nodes = True
        nt = m.node_tree
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
        for n in list(nt.nodes):
            if n.type not in ("TEX_IMAGE",):
                nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = _rgb(m) + (1.0,)
        em.inputs["Strength"].default_value = strength
        if tex is not None:
            nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

    def _principled(m):
        m.use_nodes = True
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if bsdf is None:
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        if out is None:
            out = nt.nodes.new("ShaderNodeOutputMaterial")
        if not out.inputs["Surface"].is_linked:
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        base = bsdf.inputs.get("Base Color")
        if base is not None and not base.is_linked:
            tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
            if tex is not None:
                nt.links.new(tex.outputs["Color"], base)
            else:
                base.default_value = _rgb(m) + (1.0,)
        for _k, _v in (("Roughness", 0.75), ("Specular IOR Level", 0.2), ("Metallic", 0.0)):
            if bsdf.inputs.get(_k) is not None and not bsdf.inputs[_k].is_linked:
                bsdf.inputs[_k].default_value = _v

    char_mats = set()
    if flat_chars:
        for _n in (globals().get("P2_CHAR_OBJS") or ()):
            _o = _b.data.objects.get(_n)
            if _o is not None:
                for _m in _o.data.materials:
                    if _m:
                        char_mats.add(_m.name)
    for m in list(_b.data.materials):
        try:
            if m.name == "P2_InkHull":
                _emission(m, 1.0)
                m.use_backface_culling = True
            elif m.name in char_mats:
                _emission(m, 1.0)  # persos 2D : aplats francs, tête blanc pur quelle que soit la lumière
            elif max(_rgb(m)) > 0.92 and min(_rgb(m)) < 0.25 and m.name.startswith("M"):
                _emission(m, 3.0)  # lampes, braises, néons : vraie lueur
            else:
                _principled(m)
        except Exception as _e:
            print("hq mat:", m.name, _e)
    # monde = ciel qui éclaire doucement la scène
    w = sc.world
    if w is not None:
        try:
            w.use_nodes = True
            bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
            if bg is not None:
                bg.inputs["Color"].default_value = tuple(w.color[:3]) + (1.0,)
                bg.inputs["Strength"].default_value = 0.6
        except Exception:
            pass
    # soleil dans la direction de la lumière Workbench
    sun = _b.data.lights.new("ClipoaSun", type="SUN")
    sun.energy = 1.2 if globals().get("NIGHT") else 3.2
    sun.color = (0.75, 0.82, 1.0) if globals().get("NIGHT") else (1.0, 0.96, 0.9)
    try:
        sun.angle = 0.12
    except Exception:
        pass
    so = _b.data.objects.new("ClipoaSun", sun)
    sc.collection.objects.link(so)
    try:
        from mathutils import Vector as _V
        d = _V(tuple(sc.display.light_direction))
        so.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    except Exception:
        so.rotation_euler = (0.8, 0.2, 0.6)
    for o in sc.objects:
        if o.type == "LIGHT" and o.data.type == "POINT":
            o.data.energy = 150  # EEVEE : la lampe d'intérieur Workbench (380 W) surexpose les murs
    # les persos plats ne projettent pas d'ombre bizarre sur eux-mêmes
    for _n in (globals().get("P2_CHAR_OBJS") or ()):
        _o = _b.data.objects.get(_n)
        if _o is not None:
            try:
                _o.visible_shadow = False
            except Exception:
                pass


if globals().get("QUALITY") == "hq":
    try:
        _clipoa_hq()
    except Exception as _hq_e:
        print("clipoa hq:", _hq_e)
