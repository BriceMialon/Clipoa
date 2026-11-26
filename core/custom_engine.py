# -*- coding: utf-8 -*-
"""
Moteur SUR MESURE pour copier le style d'une vidéo (fonction « lien d'une vidéo dont tu veux le style »).

Pas de rangement dans un style existant : l'IA (Claude, qui regarde les images de la vidéo) choisit elle-même l'outil
le plus adapté et écrit le moteur de CE style :
- « html » : une page animée (Canvas 2D, SVG, CSS, ou three.js en WebGL pour la 3D toon / cel-shading) rendue image par image
  dans Chrome sans fenêtre (Playwright) → dessin animé, motion design, infographies, 3D cartoon à contours…
- « blender » : un script Blender complet (Eevee / Workbench, Freestyle / Line Art, matériaux toon…) → vraie 3D, volumes, lumière.

1) Création du style : design_style_engine() écrit le moteur « modèle » du style, en fait une planche d'images, Claude la compare
   aux images de la vidéo d'origine et corrige (1 tour). Le moteur est rangé avec le style (storage/plugins/<id>/engine/).
2) Chaque vidéo : render_with_style_engine() fait adapter ce moteur à la NOUVELLE histoire (ce qui est dit est montré au moment
   où c'est dit), vérifie quelques images, corrige les erreurs, puis rend la vidéo. En cas d'échec, la Fabrique se rabat sur le
   style intégré le plus proche (production.fallback_style).

Les sous-titres, compteurs et cartons sont ajoutés ensuite par Clipoa (VideoComposer) : le moteur ne dessine que l'image.
"""
import base64
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import FFMPEG_PATH, STORAGE_DIR

EPISODES_DIR = STORAGE_DIR / "custom_engines"
HTML_W, HTML_H, HTML_FPS = 720, 1280, 24
BLENDER_FPS = 12

CONTRACT_HTML = """### Outil « html » : une page web COMPLÈTE (un seul fichier HTML, CSS et JS inclus)
- Image verticale {w}×{h} px. Le décor doit remplir tout l'écran.
- Avant ton code, Clipoa charge `window.CLIPOA` = {{ duration, fps, title, lines:[{{id,text,start,end,chunks:[{{text,start,end}}],words:[{{w,start,end}}]}}],
  shots:[{{start,end,text,show,emotion,camera,action}}], palette:{{sky,ground,accent}} }} (temps en secondes, calés sur la voix).
- Tu DOIS définir `window.renderFrame = function(t) {{ … }}` qui dessine EXACTEMENT l'image de l'instant t (en secondes),
  de façon déterministe (pas de Math.random() non initialisé, pas d'horloge : seul t compte ; utilise un random à graine).
  renderFrame peut renvoyer une Promise. Quand tout est prêt (images générées, polices…), mets `window.__ready = true`.
- Dessine dans un `<canvas id="stage" width="{w}" height="{h}">` (Canvas 2D ou WebGL) : c'est lui que Clipoa capture.
  (Si tu dessines en SVG/DOM, mets-les dans un conteneur plein écran de {w}×{h} : Clipoa capturera la page.)
- 3D possible avec three.js (WebGL, MeshToonMaterial, contours par coque inversée ou OutlinePass, ombres) :
  `<script type="importmap">{{"imports":{{"three":"/three/build/three.module.js","three/addons/":"/three/examples/jsm/"}}}}</script>` {three_note}
- Polices disponibles : `/fonts/LuckiestGuy-Regular.ttf`, `/fonts/Montserrat-Black.ttf`, `/fonts/Montserrat-ExtraBold.ttf` (via @font-face) ;
  sinon polices système (Arial Black, Helvetica). AUCUNE ressource Internet (pas de CDN, pas d'image distante) : tout est dessiné en code.
- NE dessine PAS les sous-titres, ni les compteurs, ni les cartons de texte : Clipoa les ajoute par-dessus."""

CONTRACT_BLENDER = """### Outil « blender » : un script Python Blender 5.x COMPLET (`import bpy`)
- Le script reçoit déjà défini : `TIMELINE` (même contenu que ci-dessus : duration, lines, shots, palette) et `FPS` = {fps}.
- Il construit la scène et l'anime pour toute la durée (frame = round(t × FPS) + 1), caméra comprise (scene.camera),
  avec les coupes de plans aux temps de `TIMELINE['shots']`. Résolution et sortie vidéo sont imposées par Clipoa (540×960).
- Moteur au choix : BLENDER_EEVEE_NEXT (lumière, matériaux toon, Line Art / Freestyle pour les contours) ou BLENDER_WORKBENCH (rapide).
  Pas de Cycles (trop lent). Garde le rendu sous ~1 s par image.
- Interdit : subprocess, os.system, réseau, lecture/écriture hors de la scène. Tout est modélisé en code (pas de fichier externe).
- Ne fabrique PAS les sous-titres ni les textes de compteurs : Clipoa les ajoute par-dessus."""


# ---------------------------------------------------------------- IA
def _ask(prompt: str, engine: str = "claude", model: Optional[str] = None, images: Optional[List[str]] = None, timeout: int = 900) -> str:
    from core.claude_bridge import ClaudeBridge
    if images:
        try:
            return ClaudeBridge.query_with_images(prompt, images, action="custom_engine", timeout=timeout)
        except Exception as e:
            print(f"⚠️ Vision indisponible ({e}) : moteur écrit sans les images.")
    return ClaudeBridge.query(prompt, action="custom_engine")


def _extract(raw: str, tool: str) -> str:
    lang = r"(?:html)?" if tool == "html" else r"(?:python|py)?"
    blocks = re.findall(r"```" + lang + r"\s*\n([\s\S]*?)```", raw or "")
    if not blocks:
        # pas de vrai bloc de code = pas de vraie réponse de l'IA (quota, réponse de secours…)
        raise ValueError("l'IA n'a pas renvoyé de code")
    code = max(blocks, key=len).strip()
    if tool == "html":
        if not re.search(r"window\.renderFrame\s*=", code) or "__ready" not in code or not re.search(r"<(canvas|svg|div|html|body)", code, re.I):
            raise ValueError("le code reçu ne respecte pas le contrat (window.renderFrame, window.__ready)")
    else:
        from core.code_guard import check_bpy_code
        if "import bpy" not in code:
            raise ValueError("script Blender refusé (pas de « import bpy »)")
        unsafe = check_bpy_code(code)
        if unsafe:
            raise ValueError("script Blender refusé (sécurité) : " + " ; ".join(unsafe[:4]))
    return code


def _parse_head(raw: str) -> Dict[str, Any]:
    m = re.search(r"\{[^{}]*\"tool\"[^{}]*\}", raw or "")
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    tool = str(d.get("tool") or "").lower()
    if tool not in ("html", "blender"):
        tool = "blender" if "import bpy" in (raw or "") and "renderFrame" not in (raw or "") else "html"
    return {"tool": tool, "why": str(d.get("why") or "")[:400]}


def _three_note() -> str:
    try:
        from core.cine_setup import THREE_DIR
        if (THREE_DIR / "build" / "three.module.js").exists():
            return "(three.js est installé)"
    except Exception:
        pass
    return "(three.js n'est pas installé sur cette machine : préfère Canvas 2D/SVG, ou l'outil blender pour la 3D)"


def contracts() -> str:
    return CONTRACT_HTML.format(w=HTML_W, h=HTML_H, three_note=_three_note()) + "\n\n" + CONTRACT_BLENDER.format(fps=BLENDER_FPS)


# ---------------------------------------------------------------- chronologie (voix → plans)
def build_timeline(words: List[Dict[str, Any]], duration: float, plan: Optional[Dict[str, Any]] = None,
                   spec_shots: Optional[List[Dict[str, Any]]] = None, title: str = "", palette: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from core.cine_director import build_timeline as _lines
    tl = _lines(words or [], duration)
    shots = []
    for i, s in enumerate((plan or {}).get("shots") or []):
        st, en = float(s.get("start", 0.0)), float(s.get("end", duration))
        txt = " ".join(str(w.get("word") or "") for w in (words or []) if st - 0.05 <= float(w.get("start", 0)) < en - 0.05)
        sp = (spec_shots or [])[i] if spec_shots and i < len(spec_shots) else {}
        shots.append({"start": round(st, 3), "end": round(en, 3), "text": txt[:200] or str(s.get("desc") or "")[:200],
                      "show": sp.get("show"), "emotion": sp.get("emotion"), "camera": sp.get("camera"), "action": sp.get("action")})
    if not shots:
        shots = [{"start": L["start"], "end": L["end"], "text": L["text"]} for L in tl["lines"]] or [{"start": 0.0, "end": duration, "text": title}]
    return {"duration": round(duration, 3), "title": title, "lines": tl["lines"], "shots": shots, "palette": palette or {}}


# ---------------------------------------------------------------- rendu « html » (Chrome sans fenêtre)
def _routes(ep_dir: Path) -> List[tuple]:
    r = [("/ep/", ep_dir)]
    try:
        from core.cine_setup import FONTS_DIR, THREE_DIR
        r += [("/three/", THREE_DIR), ("/fonts/", FONTS_DIR)]
    except Exception:
        pass
    return r


def _serve(ep_dir: Path):
    routes = _routes(ep_dir)

    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def translate_path(self, path):
            p = path.split("?", 1)[0]
            for prefix, base in routes:
                if p.startswith(prefix):
                    t = (Path(base) / p[len(prefix):]).resolve()
                    if str(t).startswith(str(Path(base).resolve())):
                        return str(t)
            return "/nonexistent"

    H.extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{".js": "text/javascript", ".mjs": "text/javascript", ".ttf": "font/ttf"})
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


class HtmlPage:
    def __init__(self, ep_dir: Path, w: int = HTML_W, h: int = HTML_H):
        self.ep_dir, self.w, self.h = Path(ep_dir), w, h
        self.logs: List[str] = []

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        from core.cine_setup import find_chrome
        self.httpd, port = _serve(self.ep_dir)
        self.pw = sync_playwright().start()
        kw = {"headless": True, "args": ["--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--no-sandbox"]}
        if find_chrome():
            kw["executable_path"] = find_chrome()
        self.browser = self.pw.chromium.launch(**kw)
        self.page = self.browser.new_page(viewport={"width": self.w, "height": self.h}, device_scale_factor=1)
        # aucune sortie vers Internet : seulement le serveur local de Clipoa
        self.page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(f"http://127.0.0.1:{port}/") or route.request.url.startswith("data:") else route.abort())
        self.page.on("console", lambda m: self.logs.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None)
        self.page.on("pageerror", lambda e: self.logs.append(f"[pageerror] {e}"))
        self.page.goto(f"http://127.0.0.1:{port}/ep/index.html")
        try:
            self.page.wait_for_function("window.__ready === true && typeof window.renderFrame === 'function'", timeout=120000)
        except Exception:
            raise RuntimeError("la page ne démarre pas : " + (" | ".join(self.logs[-6:]) or "window.__ready jamais vrai"))
        self.has_canvas = bool(self.page.evaluate("!!document.getElementById('stage') && !!document.getElementById('stage').toDataURL"))
        return self

    def __exit__(self, *exc):
        for fn in (lambda: self.browser.close(), lambda: self.pw.stop(), lambda: self.httpd.shutdown()):
            try:
                fn()
            except Exception:
                pass

    def frame_jpeg(self, t: float) -> bytes:
        self.page.evaluate("async t => { await window.renderFrame(t); }", float(t))
        if self.has_canvas:
            u = self.page.evaluate("() => document.getElementById('stage').toDataURL('image/jpeg', 0.9)")
            return base64.b64decode(u.split(",", 1)[1])
        return self.page.screenshot(type="jpeg", quality=90)


def _write_episode(ep_dir: Path, code: str, timeline: Dict[str, Any]) -> None:
    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / "clipoa_timeline.js").write_text("window.CLIPOA = " + json.dumps(dict(timeline, fps=HTML_FPS), ensure_ascii=False) + ";\n", encoding="utf-8")
    tag = '<script src="clipoa_timeline.js"></script>'
    if tag not in code:
        code = re.sub(r"(<head[^>]*>)", r"\1\n" + tag, code, count=1, flags=re.I) if re.search(r"<head[^>]*>", code, re.I) else tag + "\n" + code
    (ep_dir / "index.html").write_text(code, encoding="utf-8")


def _luma(path: str) -> float:
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((36, 64))
        return sum(im.getdata()) / (36 * 64)
    except Exception:
        return 128.0


def preview_html(ep_dir: Path, times: List[float]) -> Dict[str, Any]:
    out = ep_dir / "preview"
    out.mkdir(parents=True, exist_ok=True)
    images, problems = [], []
    try:
        with HtmlPage(ep_dir, HTML_W // 2, HTML_H // 2) as hp:
            for i, t in enumerate(times):
                try:
                    p = out / f"{i:02d}.jpg"
                    p.write_bytes(hp.frame_jpeg(t))
                    images.append(str(p))
                    if _luma(str(p)) < 8:
                        problems.append(f"image à {t:.1f} s presque noire")
                except Exception as e:
                    problems.append(f"erreur JavaScript à {t:.1f} s : {str(e)[:220]}")
            problems += [l[:220] for l in hp.logs if "pageerror" in l or "[error]" in l][-6:]
    except Exception as e:
        problems.append(str(e)[:300])
    return {"images": images, "problems": problems}


def render_html(ep_dir: Path, out_mp4: str, duration: float, progress: Optional[Callable[[int, int], None]] = None) -> str:
    n = max(1, int(round(duration * HTML_FPS)))
    with HtmlPage(ep_dir) as hp:
        ff = subprocess.Popen([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(HTML_FPS),
                               "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out_mp4], stdin=subprocess.PIPE)
        for f in range(n):
            ff.stdin.write(hp.frame_jpeg(f / HTML_FPS))
            if progress and f % 24 == 0:
                progress(f, n)
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("encodage de la vidéo impossible")
    return out_mp4


# ---------------------------------------------------------------- rendu « blender »
def _blender_script(code: str, timeline: Dict[str, Any], path: Path) -> None:
    head = ("import json\nTIMELINE = json.loads(" + json.dumps(json.dumps(timeline, ensure_ascii=False)) + ")\nFPS = " + str(BLENDER_FPS) + "\n")
    path.write_text(head + code, encoding="utf-8")


def render_blender(ep_dir: Path, code: str, timeline: Dict[str, Any], out_mp4: str, progress=None) -> str:
    from core.blender_engine import BlenderEngine
    from core.code_guard import ensure_safe_bpy_code
    ensure_safe_bpy_code(code)  # le code de l'IA ne sort jamais de la scène 3D
    py = ep_dir / "scene.py"
    _blender_script(code, timeline, py)
    frames = max(12, int(round(timeline["duration"] * BLENDER_FPS)))
    BlenderEngine.enforce_render_settings(str(py), frames, fps=BLENDER_FPS)
    if not BlenderEngine.render_script(str(py), out_mp4, frames=frames, progress_cb=progress):
        raise RuntimeError("le rendu Blender du moteur sur mesure a échoué")
    return out_mp4


def preview_blender(ep_dir: Path, code: str, timeline: Dict[str, Any], times: List[float]) -> Dict[str, Any]:
    """Quelques images fixes du script Blender (vérifie qu'il tourne et à quoi il ressemble)."""
    from config import BLENDER_PATH
    from core.code_guard import check_bpy_code
    unsafe = check_bpy_code(code)
    if unsafe:
        # refusé avant toute exécution ; l'IA reçoit la liste et corrige au tour suivant
        return {"images": [], "problems": ["code refusé pour sécurité (interdit : fichiers, réseau, imports hors bpy/math) : " + " ; ".join(unsafe[:6])]}
    out = ep_dir / "preview"
    out.mkdir(parents=True, exist_ok=True)
    py = ep_dir / "preview_scene.py"
    frames = [max(1, int(round(t * BLENDER_FPS)) + 1) for t in times]
    _blender_script(code, timeline, py)
    tail = ("\nimport bpy as _b\n_s = _b.context.scene\n_s.render.resolution_x, _s.render.resolution_y = 540, 960\n"
            "_s.render.engine = 'BLENDER_WORKBENCH' if _s.render.engine == 'CYCLES' else _s.render.engine\n"
            "if hasattr(_s.render.image_settings, 'media_type'):\n    _s.render.image_settings.media_type = 'IMAGE'\n"
            "_s.render.image_settings.file_format = 'JPEG'\n"
            f"for _i, _f in enumerate({frames}):\n    _s.frame_set(_f)\n    _s.render.filepath = {json.dumps(str(out))} + '/%02d.jpg' % _i\n"
            "    _b.ops.render.render(write_still=True)\n")
    py.write_text(py.read_text(encoding="utf-8") + tail, encoding="utf-8")
    from core.blender_engine import BlenderEngine
    BlenderEngine._patch_blender5_compat(str(py))
    r = subprocess.run([BLENDER_PATH, "-b", "--python", str(py)], capture_output=True, text=True, timeout=900)
    images = sorted(str(p) for p in out.glob("*.jpg"))
    problems = []
    if r.returncode != 0 or not images:
        err = [l for l in (r.stdout + r.stderr).splitlines() if "Error" in l or "Traceback" in l or "line " in l][-8:]
        problems.append("le script Blender plante : " + " | ".join(err)[:600])
    return {"images": images, "problems": problems}


def _preview(tool: str, ep_dir: Path, code: str, timeline: Dict[str, Any], n: int = 6) -> Dict[str, Any]:
    d = max(1.0, float(timeline["duration"]))
    times = [round(d * (i + 0.5) / n, 2) for i in range(n)]
    if tool == "html":
        _write_episode(ep_dir, code, timeline)
        return preview_html(ep_dir, times)
    return preview_blender(ep_dir, code, timeline, times)


# ---------------------------------------------------------------- 1) création du moteur du style
def engine_dir(plugin_id: str) -> Path:
    from core.style_plugins import PLUGINS_DIR
    return PLUGINS_DIR / plugin_id / "engine"


def load_engine(plugin_id: str) -> Optional[Dict[str, Any]]:
    d = engine_dir(plugin_id)
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        code = (d / ("template.html" if meta["tool"] == "html" else "template.py")).read_text(encoding="utf-8")
        return dict(meta, code=code)
    except Exception:
        return None


def design_style_engine(plugin_id: str, analysis: Dict[str, Any], sheets: List[str], words: List[Dict[str, Any]], duration: float,
                        engine: str = "claude", model: Optional[str] = None, progress: Optional[Callable[[int, str], None]] = None) -> Dict[str, Any]:
    def _p(pct, msg):
        if progress:
            progress(pct, msg)

    a = analysis or {}
    timeline = build_timeline(words, min(duration or 20.0, 40.0), title=str(a.get("name") or ""), palette=a.get("palette") or {})
    prompt = f"""Tu es directeur technique d'un studio de vidéos courtes. Clipoa doit pouvoir REFAIRE des vidéos EXACTEMENT dans le style
de la vidéo de référence (les images jointes : planche de 30 images sur toute la vidéo + 6 images clés), avec d'autres histoires.
Il n'y a PAS de style tout fait : tu choisis l'outil le plus adapté et tu écris le moteur de CE style, fidèle au rendu de la référence
(proportions et dessin des personnages, contours, couleurs, lumière, textures, profondeur, cadrages, mouvements de caméra, effets).

Analyse déjà faite de la vidéo :
{json.dumps({k: a.get(k) for k in ("name", "tagline", "tool_guess", "palette", "time_of_day", "hud")}, ensure_ascii=False)[:1500]}
Direction artistique :
{str(a.get('da_prompt') or '')[:5000]}

Outils disponibles sur la machine (choisis-en UN) :
{contracts()}

Pour ce premier jet, illustre la narration de la référence ci-dessous (Clipoa l'utilise pour vérifier le rendu) :
{json.dumps({"duration": timeline["duration"], "shots": timeline["shots"][:14]}, ensure_ascii=False)[:3500]}

Écris un moteur RÉUTILISABLE : des fonctions pour dessiner les personnages (avec expressions), les décors, les objets, et la caméra,
pilotées par `CLIPOA.shots` (chaque plan montre ce que dit sa phrase, au moment où elle est dite).
Réponds avec d'abord une ligne JSON {{"tool": "html|blender", "why": "pourquoi cet outil, en une phrase"}}, puis le code COMPLET
dans un seul bloc ```html … ``` (outil html) ou ```python … ``` (outil blender)."""
    _p(42, "🧠 L'IA choisit l'outil et écrit le moteur de ce style (2-5 min)…")
    raw = _ask(prompt, engine, model, images=sheets)
    head = _parse_head(raw)
    tool = head["tool"]
    code = _extract(raw, tool)
    work = EPISODES_DIR / f"_style_{plugin_id}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    for attempt in range(2):
        _p(46 + attempt * 3, f"🔍 Planche de contrôle du moteur ({tool}, essai {attempt + 1})…")
        rep = _preview(tool, work, code, timeline)
        if attempt == 1:
            break
        compare = bool(rep["images"])
        if not rep["problems"] and not compare:
            break
        fix = (f"Voici ton moteur ({tool}) :\n```{'html' if tool == 'html' else 'python'}\n{code}\n```\n\n"
               + (("Défauts techniques relevés :\n- " + "\n- ".join(rep["problems"][:12]) + "\n\n") if rep["problems"] else "")
               + ("Compare les images de ton rendu (rendu_*.jpg) aux images de la vidéo de référence (reference_*.jpg) : corrige tout ce qui "
                  "s'en écarte (dessin et proportions des personnages, contours, couleurs, lumière, décor, cadrage). " if compare else "")
               + f"\nRappel des règles :\n{contracts()}\n\nRéponds UNIQUEMENT avec le code COMPLET corrigé dans un seul bloc de code.")
        imgs = None
        if compare:
            tmp = work / "compare"
            tmp.mkdir(parents=True, exist_ok=True)
            imgs = []
            for i, pth in enumerate(rep["images"][:6]):
                dst = tmp / f"rendu_{i + 1}.jpg"
                shutil.copyfile(pth, dst)
                imgs.append(str(dst))
            for i, pth in enumerate(sheets[:2]):
                dst = tmp / f"reference_{i + 1}.jpg"
                shutil.copyfile(pth, dst)
                imgs.append(str(dst))
        _p(48, "🛠️ L'IA compare son rendu à la vidéo d'origine et corrige…")
        try:
            code = _extract(_ask(fix, engine, model, images=imgs), tool)
        except Exception as e:
            print(f"⚠️ Correction du moteur impossible ({e}) : on garde la version actuelle.")
            break
    if any("ne démarre pas" in p or "plante" in p for p in rep["problems"]) or not rep["images"]:
        raise RuntimeError("le moteur sur mesure ne produit pas d'image : " + "; ".join(rep["problems"][:3]))
    d = engine_dir(plugin_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / ("template.html" if tool == "html" else "template.py")).write_text(code, encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({"tool": tool, "why": head["why"], "created_at": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False, indent=2), encoding="utf-8")
    for i, pth in enumerate(rep["images"][:6]):
        shutil.copyfile(pth, d / f"apercu_{i + 1}.jpg")
    return {"tool": tool, "why": head["why"]}


# ---------------------------------------------------------------- 2) chaque vidéo
def render_with_style_engine(plugin: Dict[str, Any], session_id: str, script: Dict[str, Any], words: List[Dict[str, Any]],
                             plan: Dict[str, Any], duration: float, out_mp4: str, spec_shots: Optional[List[Dict[str, Any]]] = None,
                             engine: str = "claude", model: Optional[str] = None, da_hint: str = "",
                             progress: Optional[Callable[[int, str], None]] = None) -> str:
    def _p(pct, msg):
        if progress:
            progress(pct, msg)

    eng = load_engine(plugin["id"])
    if not eng:
        raise RuntimeError("ce style n'a pas de moteur sur mesure")
    tool = eng["tool"]
    prod = plugin.get("production") or {}
    timeline = build_timeline(words, duration, plan, spec_shots, title=str(script.get("title") or ""), palette=prod.get("palette") or {})
    ep_dir = EPISODES_DIR / re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:60]
    ep_dir.mkdir(parents=True, exist_ok=True)
    code_file = ep_dir / ("episode.html" if tool == "html" else "episode.py")
    if code_file.exists():  # reprise après coupure : on garde le code déjà écrit
        code = code_file.read_text(encoding="utf-8")
    else:
        lng = "html" if tool == "html" else "python"
        prompt = f"""Voici le moteur ({tool}) d'un style de vidéo courte. Adapte-le à la NOUVELLE histoire ci-dessous en gardant EXACTEMENT
le même style (dessin des personnages, contours, couleurs, lumière, caméra, effets). Invente les personnages, décors et objets
de CETTE histoire. Tout ce qui est dit doit se VOIR au moment exact où c'est dit (objet qui apparaît, action du personnage, décor
qui change, chiffre qui monte) : suis `CLIPOA.shots` / `TIMELINE['shots']` (start, end, text, show, emotion, action) plan par plan.
Mouvements vivants : personnages qui bougent, caméra qui avance ou glisse, objets qui surgissent avec un rebond.

Titre : {script.get('title', '')}
{('Direction artistique : ' + da_hint[:2500]) if da_hint else ''}
Narration calée sur la voix (durée {timeline['duration']:.2f} s) :
{json.dumps(timeline['shots'], ensure_ascii=False)[:6000]}

Règles techniques :
{CONTRACT_HTML.format(w=HTML_W, h=HTML_H, three_note=_three_note()) if tool == 'html' else CONTRACT_BLENDER.format(fps=BLENDER_FPS)}

Moteur du style :
```{lng}
{eng['code'][:60000]}
```

Réponds UNIQUEMENT avec le code COMPLET de la vidéo dans un seul bloc ```{lng} … ```."""
        _p(56, f"🎬 [3/4] Claude anime ton histoire avec le moteur de ce style (2-5 min)…")
        code = _extract(_ask(prompt, engine, model), tool)
        code_file.write_text(code, encoding="utf-8")
    for attempt in range(2):
        _p(60, f"🔍 [3/4] Vérification des images (essai {attempt + 1})…")
        rep = _preview(tool, ep_dir, code, timeline, n=4)
        if not rep["problems"] or attempt == 1:
            break
        _p(61, "🛠️ [3/4] Correction des erreurs…")
        try:
            code = _extract(_ask(f"Voici le code ({tool}) :\n```\n{code}\n```\nErreurs :\n- " + "\n- ".join(rep["problems"][:12])
                                 + "\nCorrige. Réponds UNIQUEMENT avec le code COMPLET corrigé dans un seul bloc de code.", engine, model), tool)
            code_file.write_text(code, encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Correction impossible ({e})")
            break
    if not rep["images"]:
        raise RuntimeError("le moteur sur mesure ne produit pas d'image : " + "; ".join(rep["problems"][:3]))
    t0 = time.time()

    def _prog(done, total):
        eta = int((time.time() - t0) / max(1, done) * (total - done) / 60)
        _p(62 + int(12 * done / max(1, total)), f"🎥 [3/4] Rendu sur mesure image {done}/{total} · encore ≈ {eta} min")

    if tool == "html":
        _write_episode(ep_dir, code, timeline)
        return render_html(ep_dir, out_mp4, duration, progress=_prog)
    return render_blender(ep_dir, code, timeline, out_mp4, progress=_prog)
