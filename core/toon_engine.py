"""
Moteur « Dessin à compteur » : une image vectorielle par temps fort (~0,8 s), dessinée en SVG.

1. Découpe de la voix en images courtes (frontières de mots, ~0,8 s).
2. Claude DÉCRIT chaque image en JSON (persos, expression, pose, lieu, cadrage, bulle, compteur) ;
   il n'écrit aucun code : le dessin est fait par core/toon_kit.py (rien d'exécuté venant de l'IA).
3. Chrome sans fenêtre (Playwright) transforme chaque SVG en image ; FFmpeg ajoute un léger zoom
   par image et l'en-tête fixe (titre, sous-titre, pastille compteur), puis assemble la vidéo de fond.
Si l'IA ne répond pas, une mise en scène est déduite du texte (aucun échec bloquant).
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import BASE_DIR, FFMPEG_PATH
from core import toon_kit as K

FPS = 30
FONTS_DIR = BASE_DIR / "assets" / "fonts"
PANEL_TARGET_S = 0.7
PANEL_MIN_S = 0.45
PANEL_MAX_S = 1.4


# ───────────────────────────── Découpe en images ─────────────────────────────

def build_panels(words: List[Dict[str, Any]], duration: float, beat_starts: Optional[List[float]] = None,
                 target: float = PANEL_TARGET_S, min_len: float = PANEL_MIN_S, max_len: float = PANEL_MAX_S) -> List[Dict[str, Any]]:
    """Images calées sur les débuts de mots : une nouvelle image toutes les ~0,8 s, et à chaque nouveau plan."""
    duration = max(0.5, float(duration))
    ws = [w for w in (words or []) if isinstance(w, dict) and "start" in w]
    beats = sorted(float(b) for b in (beat_starts or []) if 0 < float(b) < duration)
    starts = [0.0]
    for w in ws[1:]:
        t = float(w["start"])
        if t >= duration - min_len:
            break
        since = t - starts[-1]
        at_beat = any(abs(t - b) < 0.12 for b in beats)
        if since >= min_len and (since >= target or at_beat):
            starts.append(t)
    # trous sans mots trop longs (silence, musique) : coupés régulièrement
    filled = []
    bounds = starts + [duration]
    for a, b in zip(bounds, bounds[1:]):
        filled.append(a)
        n = int((b - a) // max_len)
        for k in range(1, n + 1):
            t = a + k * (b - a) / (n + 1)
            if b - t >= min_len:
                filled.append(t)
    starts = sorted(set(round(s, 3) for s in filled))
    panels = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else duration
        txt = " ".join(str(w.get("word", "")).strip() for w in ws if s - 0.01 <= float(w["start"]) < e - 0.01)
        panels.append({"i": i, "start": round(s, 3), "end": round(e, 3), "text": txt})
    if len(panels) > 1 and panels[-1]["end"] - panels[-1]["start"] < min_len:
        last = panels.pop()
        panels[-1]["end"] = last["end"]
        panels[-1]["text"] = (panels[-1]["text"] + " " + last["text"]).strip()
    return panels


# ───────────────────────────── Mise en scène par l'IA ─────────────────────────────

def build_prompt(script: Dict[str, Any], panels: List[Dict[str, Any]], da_hint: str = "") -> str:
    lines = "\n".join(f'{p["i"]}|{p["end"] - p["start"]:.1f}s|{p["text"]}' for p in panels)
    title = script.get("title") or ""
    hook = script.get("hook_screen_text") or ""
    da = (da_hint or "")[:1800]
    sb = []
    for sh in (script.get("visual_storyboard") or [])[:14]:
        if isinstance(sh, dict):
            d = str(sh.get("visual") or sh.get("description") or sh.get("desc") or "").strip()
            if d:
                sb.append("- " + d[:160])
    board = ("Storyboard du script (respecte les tenues et les personnages décrits) :\n" + "\n".join(sb)) if sb else ""
    return f"""Tu es le dessinateur d'un short vertical en DESSIN VECTORIEL façon « brainrot » : persos chibi (grosse tête ronde,
grands yeux, joues roses, souvent casquette et lunettes rondes), contours épais, aplats, UNE image fixe par temps fort
(~0,8 s), une nouvelle expression ou un nouveau cadrage à CHAQUE image. Un en-tête fixe en haut résume la règle de la vidéo
et une pastille COMPTEUR évolue pendant l'histoire (ex. « TON SILENCE : 11 MIN », « TES EXCUSES : 4 »).
Tu ne dessines rien toi-même : tu DÉCRIS chaque image en JSON, un programme la dessine.

Titre : {title}
Accroche : {hook}
{('Direction artistique du style :' + chr(10) + da) if da else ''}
{board}

Voici les {len(panels)} images, une par ligne : numéro|durée|texte dit pendant l'image.
{lines}

Réponds UNIQUEMENT avec ce JSON (aucun texte autour) :
{{
 "header": {{"title": "4 à 6 mots, la règle ou le concept (ex. ICI, TON SILENCE SE VOIT)",
            "subtitle": "la règle en chiffres, court (ex. 10 MIN SANS PARLER = TRANSPARENT)",
            "counter_label": "ce qu'on compte, 1 à 3 mots (ex. TON SILENCE), ou vide si rien ne se compte",
            "counter_unit": "unité courte (MIN, J, €, …) ou vide", "accent": "#F0508C"}},
 "cast": [{{"id": "hero", "name": "Yanis", "skin": "#F6D3B3", "hair": "#3B2A20", "hair_style": "short",
           "top": "#3F8E5E", "top_style": "hoodie", "pants": "#3C4A66", "cap": "#F4B63F", "glasses": true}}],
 "locations": [{{"id": "camp", "kind": "park_day", "label": ""}}],
 "cards": {{"regles": {{"title": "Règlement de la colo", "items": [["Article 1", "Ici, tout le monde participe."]], "sign": "Les moniteurs"}}}},
 "panels": [{{"i": 0, "loc": "camp", "f": "close", "c": [{{"id": "hero", "e": "shocked", "p": "arms_up", "n": 10, "say": "", "g": 0}}],
             "crowd": 0, "k": 10, "prop": "", "pl": "", "card": "", "hi": 0}}]
}}

Règles :
- cast : 1 à 6 persos récurrents, chacun reconnaissable (couleurs de peau, cheveux, haut, casquette différentes).
  skin parmi {", ".join(K.SKINS)} ; hair_style parmi {", ".join(K.HAIR_STYLES)} ; top_style parmi {", ".join(K.TOP_STYLES)} ;
  "cap" = couleur de casquette ou null (le compteur s'affiche SUR la casquette), "glasses" true/false.
- locations : 1 à 5 lieux ; kind parmi {", ".join(K.LOCATIONS)} ; "label" = panneau court sur le décor (ex. DORTOIR) ou vide.
- panels : EXACTEMENT {len(panels)} entrées, "i" de 0 à {len(panels) - 1}, dans l'ordre.
  "f" (cadrage) parmi close (gros plan d'UN perso, le plus fréquent), medium (2-3 persos), wide (groupe + "crowd" figurants 0-8),
  card (carton texte plein écran : "card" = clé de "cards", "hi" = numéro de l'article mis en avant), object (gros objet : "prop" parmi
  {", ".join(K.PROPS)}, "pl" = petit texte sur l'objet).
  "c" = persos à l'image : "e" expression parmi {", ".join(K.EXPRESSIONS)} ; "p" pose parmi {", ".join(K.POSES)} ;
  "n" = valeur du compteur sur SA casquette (nombre) ; "say" = bulle de 1 à 3 mots (rare, max 1 image sur 5) ;
  "g" = transparence 0 à 0.8 (ex. un perso qui « disparaît »).
  "k" = valeur de la pastille compteur de l'en-tête à cette image (nombre, elle évolue avec l'histoire).
- Cohérence : le héros (premier perso de "cast") est celui dont parle la voix ; quand la phrase parle de lui, IL est à l'image.
  Son apparence ne change jamais. "n" sur une casquette = l'état de CE perso (le héros porte la valeur de "k") ; un perso
  secondaire a sa propre valeur, jamais celle du héros. Quand "k" change, montre le héros au même moment.
  Quand le compteur change beaucoup, passe par des valeurs intermédiaires sur plusieurs images.
- Rythme « brainrot » : alterne gros plans et plans larges, change d'expression à chaque image, réactions exagérées,
  l'image montre ce que dit la voix (un nom = un objet ou un perso visible). 1 carton tous les ~15 s maximum.
- Textes en français, sans emoji."""


def _num(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    s = str(v).strip()[:6]
    return s if re.match(r"^-?[0-9]+([.,][0-9]+)?$", s) else None


def _short(v: Any, n: int) -> str:
    return re.sub(r"[\x00-\x1f<>]", "", str(v or "")).strip()[:n]


def sanitize(raw: Dict[str, Any], n: int) -> Optional[Dict[str, Any]]:
    """Ne garde que des valeurs connues et bornées ; None si inutilisable."""
    if not isinstance(raw, dict) or not isinstance(raw.get("panels"), list) or not raw["panels"]:
        return None
    h = raw.get("header") if isinstance(raw.get("header"), dict) else {}
    header = {"title": _short(h.get("title"), 34), "subtitle": _short(h.get("subtitle"), 46),
              "counter_label": _short(h.get("counter_label"), 22), "counter_unit": _short(h.get("counter_unit"), 8),
              "accent": K.hexcol(h.get("accent"), K.PINK)}
    cast: Dict[str, Dict[str, Any]] = {}
    for i, c in enumerate((raw.get("cast") or [])[:6]):
        if not isinstance(c, dict):
            continue
        cid = _short(c.get("id") or f"p{i}", 20)
        cast[cid] = {
            "name": _short(c.get("name"), 20),
            "skin": K.hexcol(c.get("skin"), K.SKINS[i % len(K.SKINS)]),
            "hair": K.hexcol(c.get("hair"), K.HAIRS[i % len(K.HAIRS)]),
            "hair_style": c.get("hair_style") if c.get("hair_style") in K.HAIR_STYLES else "short",
            "top": K.hexcol(c.get("top"), K.TOPS[i % len(K.TOPS)]),
            "top_style": c.get("top_style") if c.get("top_style") in K.TOP_STYLES else "hoodie",
            "pants": K.hexcol(c.get("pants"), "#3C4A66"),
            "cap": K.hexcol(c.get("cap"), K.CAPS[i % len(K.CAPS)]) if c.get("cap") else None,
            "glasses": bool(c.get("glasses")),
        }
    if not cast:
        cast = dict(_default_cast())
    locs: Dict[str, Dict[str, Any]] = {}
    for i, l in enumerate((raw.get("locations") or [])[:5]):
        if isinstance(l, dict):
            lid = _short(l.get("id") or f"l{i}", 20)
            locs[lid] = {"kind": l.get("kind") if l.get("kind") in K.LOCATIONS else "park_day", "label": _short(l.get("label"), 18),
                         "wall": K.hexcol(l.get("wall"), "") or None, "night": bool(l.get("night"))}
    if not locs:
        locs = {"main": {"kind": "park_day", "label": ""}}
    cards: Dict[str, Dict[str, Any]] = {}
    for key, cd in list((raw.get("cards") or {}).items())[:4] if isinstance(raw.get("cards"), dict) else []:
        if isinstance(cd, dict):
            items = []
            for it in (cd.get("items") or [])[:4]:
                if isinstance(it, (list, tuple)) and it:
                    items.append([_short(it[0], 30), _short(it[1] if len(it) > 1 else "", 90)])
                elif isinstance(it, dict):
                    items.append([_short(it.get("head"), 30), _short(it.get("text"), 90)])
            cards[_short(key, 20)] = {"title": _short(cd.get("title"), 40), "items": items, "sign": _short(cd.get("sign"), 30)}
    first_loc = next(iter(locs))
    first_cast = next(iter(cast))
    panels: List[Dict[str, Any]] = []
    by_i = {}
    for p in raw["panels"]:
        if isinstance(p, dict):
            try:
                by_i.setdefault(int(p.get("i", len(by_i))), p)
            except (TypeError, ValueError):
                continue
    prev = None
    for i in range(n):
        p = by_i.get(i)
        if p is None:
            p = dict(prev or {}, i=i)
        f = p.get("f") or p.get("frame")
        f = f if f in K.FRAMES else "medium"
        chars = []
        for c in (p.get("c") or p.get("chars") or [])[:5]:
            if not isinstance(c, dict):
                continue
            cid = _short(c.get("id"), 20)
            if cid not in cast:
                continue
            e, po = c.get("e") or c.get("expr"), c.get("p") or c.get("pose")
            try:
                g = max(0.0, min(0.8, float(c.get("g") or c.get("ghost") or 0)))
            except (TypeError, ValueError):
                g = 0.0
            chars.append({"id": cid, "expr": e if e in K.EXPRESSIONS else "neutral", "pose": po if po in K.POSES else "idle",
                          "counter": _num(c.get("n") if "n" in c else c.get("counter")), "say": _short(c.get("say"), 24), "ghost": g})
        if f in ("close", "medium", "wide") and not chars:
            chars = [{"id": first_cast, "expr": "neutral", "pose": "idle", "counter": None, "say": "", "ghost": 0.0}]
        card = None
        if f == "card":
            card = dict(cards.get(_short(p.get("card"), 20)) or next(iter(cards.values()), None) or {})
            if not card:
                f = "close"
                chars = chars or [{"id": first_cast, "expr": "neutral", "pose": "idle", "counter": None, "say": "", "ghost": 0.0}]
            else:
                hi = p.get("hi")
                card["hi"] = int(hi) if isinstance(hi, (int, float)) or (isinstance(hi, str) and hi.isdigit()) else None
        try:
            crowd = max(0, min(8, int(p.get("crowd") or 0)))
        except (TypeError, ValueError):
            crowd = 0
        loc = _short(p.get("loc"), 20)
        out = {"i": i, "frame": f, "loc": loc if loc in locs else first_loc, "chars": chars, "crowd": crowd,
               "counter": _num(p.get("k") if "k" in p else p.get("counter")), "prop": p.get("prop") if p.get("prop") in K.PROPS else "",
               "prop_label": _short(p.get("pl") or p.get("prop_label"), 14), "card": card}
        panels.append(out)
        prev = p
    return {"header": header, "cast": cast, "locations": locs, "cards": cards, "panels": panels}


def _default_cast() -> Dict[str, Dict[str, Any]]:
    return {
        "hero": {"skin": K.SKINS[0], "hair": K.HAIRS[2], "hair_style": "short", "top": "#3F8E5E", "top_style": "hoodie", "cap": "#F4B63F", "glasses": True},
        "ami": {"skin": K.SKINS[4], "hair": K.HAIRS[1], "hair_style": "short", "top": "#E8823A", "top_style": "vest", "cap": "#3D6FCB", "glasses": False},
        "amie": {"skin": K.SKINS[2], "hair": K.HAIRS[0], "hair_style": "long", "top": "#E86FA6", "top_style": "tshirt", "cap": None, "glasses": False},
    }


def heuristic_spec(script: Dict[str, Any], panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mise en scène sans IA : héros + amis, cadrages alternés, expression déduite de la ponctuation."""
    cast = _default_cast()
    ids = list(cast)
    cycle = ("close", "medium", "close", "wide", "close", "medium")
    out = []
    for p in panels:
        t = p.get("text") or ""
        e = "shocked" if "?" in t else ("laugh" if "!" in t else ("talk", "happy", "worried", "smug")[p["i"] % 4])
        f = cycle[p["i"] % len(cycle)]
        chars = [{"id": ids[0], "expr": e, "pose": ("idle", "arms_up", "point", "shrug")[p["i"] % 4], "counter": None, "say": "", "ghost": 0.0}]
        if f in ("medium", "wide"):
            chars.append({"id": ids[1 + p["i"] % 2], "expr": "laugh" if e != "laugh" else "shocked", "pose": "idle", "counter": None, "say": "", "ghost": 0.0})
        out.append({"i": p["i"], "frame": f, "loc": "main", "chars": chars, "crowd": 4 if f == "wide" else 0, "counter": None,
                    "prop": "", "prop_label": "", "card": None})
    title = _short(script.get("hook_screen_text") or script.get("title") or "", 34)
    return {"header": {"title": title, "subtitle": "", "counter_label": "", "counter_unit": "", "accent": K.PINK},
            "cast": cast, "locations": {"main": {"kind": "park_day", "label": ""}}, "cards": {}, "panels": out}


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    txt = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1)
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None


def design(script: Dict[str, Any], panels: List[Dict[str, Any]], model: Optional[str] = None, da_hint: str = "") -> Dict[str, Any]:
    raw = ""
    try:
        from core.claude_bridge import ClaudeBridge
        raw = ClaudeBridge.query(build_prompt(script, panels, da_hint), action="toon_design", model=model)
    except Exception as e:
        print(f"⚠️ Mise en scène IA indisponible ({e}) : mise en scène déduite du texte.")
    spec = sanitize(_parse_json(raw) or {}, len(panels)) if raw else None
    if spec:
        spec["_source"] = "ia"
        return spec
    spec = heuristic_spec(script, panels)
    spec["_source"] = "texte"
    return spec


# ───────────────────────────── Rendu ─────────────────────────────

def is_available() -> bool:
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return (FONTS_DIR / "Fredoka-Bold.ttf").exists()


def _font_css() -> str:
    css = []
    for fname, weights in (("Fredoka-Bold.ttf", (600, 700, 800)), ("Fredoka-Medium.ttf", (400, 500))):
        p = FONTS_DIR / fname
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        for w in weights:
            css.append(f"@font-face{{font-family:'{K.FONT}';font-weight:{w};src:url(data:font/ttf;base64,{b64}) format('truetype');}}")
    return "".join(css)


class Rasterizer:
    """Chrome sans fenêtre : SVG -> PNG 1080x1920 (fond transparent possible)."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = None
        try:
            from core.cine_setup import find_chrome
            exe = find_chrome()
        except Exception:
            exe = os.environ.get("CLIPOA_CHROME") or None
        args = ["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"]
        self._browser = self._pw.chromium.launch(executable_path=exe, args=args) if exe else self._pw.chromium.launch(args=args)
        self._page = self._browser.new_page(viewport={"width": K.W, "height": K.H}, device_scale_factor=1)
        self._page.set_content(f"<html><head><style>{_font_css()} html,body{{margin:0;background:transparent;overflow:hidden}}</style></head>"
                               f"<body><div id='s'></div></body></html>")
        return self

    def png(self, svg: str, path: str, transparent: bool = False) -> str:
        self._page.evaluate("s => { document.getElementById('s').innerHTML = s; }", svg)
        self._page.evaluate("() => document.fonts.ready.then(() => true)")
        self._page.screenshot(path=path, omit_background=transparent, clip={"x": 0, "y": 0, "width": K.W, "height": K.H})
        return path

    def __exit__(self, *a):
        try:
            self._browser.close()
        finally:
            self._pw.stop()


ZOOMS = {"close": (1.0, 1.07), "medium": (1.02, 1.08), "wide": (1.09, 1.02), "card": (1.0, 1.03), "object": (1.0, 1.1)}


def _segment(scene_png: str, header_png: Optional[str], frames: int, frame: str, idx: int, out: str) -> None:
    z0, z1 = ZOOMS.get(frame, (1.0, 1.06))
    if idx % 3 == 2 and frame == "close":
        z0, z1 = z1, z0
    n = max(1, frames)
    up_w, up_h = 1620, 2880
    zexpr = f"{z0}+({z1}-{z0})*on/{max(1, n - 1)}"
    vf = (f"[0:v]scale={up_w}:{up_h}:flags=lanczos,zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih*0.46-(ih/zoom*0.46)':d={n}:s={K.W}x{K.H}:fps={FPS}[bg]")
    inputs = ["-i", scene_png]
    if header_png:
        inputs += ["-i", header_png]
        vf += ";[bg][1:v]overlay=0:0:format=auto[v]"
    else:
        vf += ";[bg]null[v]"
    cmd = [FFMPEG_PATH, "-y", "-loglevel", "error", *inputs, "-filter_complex", vf, "-map", "[v]", "-frames:v", str(n),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), out]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg (image {idx}) : {res.stderr[-400:]}")


def render_video(spec: Dict[str, Any], panels: List[Dict[str, Any]], duration: float, out_mp4: str,
                 progress: Optional[Callable[[int, str], None]] = None, work_dir: Optional[str] = None) -> str:
    """Dessine chaque image, ajoute zoom + en-tête, assemble la vidéo de fond (sans son)."""
    tmp = Path(work_dir or tempfile.mkdtemp(prefix="toon_"))
    tmp.mkdir(parents=True, exist_ok=True)
    header = spec.get("header") or {}
    unit = header.get("counter_unit") or ""
    cast, locs = spec.get("cast") or {}, spec.get("locations") or {}
    pspec = spec.get("panels") or []
    n = len(panels)
    headers: Dict[str, str] = {}
    scenes: List[str] = []
    counter = None
    with Rasterizer() as R:
        for k, p in enumerate(panels):
            sp = dict(pspec[k] if k < len(pspec) else pspec[-1])
            sp["_unit"] = unit
            if sp.get("counter") is not None:
                counter = sp["counter"]
            loc = locs.get(sp.get("loc")) or next(iter(locs.values()), {"kind": "park_day"})
            svg = K.wrap_svg(K.panel_svg(sp, cast, loc, seed=7 + list(locs).index(sp.get("loc")) if sp.get("loc") in locs else 7))
            scenes.append(R.png(svg, str(tmp / f"s{k:03d}.png")))
            key = str(counter)
            if key not in headers and (header.get("title") or header.get("counter_label")):
                headers[key] = R.png(K.wrap_svg(K.header_svg(header, counter)), str(tmp / f"h{len(headers):03d}.png"), transparent=True)
            p["_header"] = headers.get(key)
            if progress and (k % 10 == 0 or k == n - 1):
                progress(58 + int(8 * (k + 1) / max(1, n)), f"🖍️ [3/4] Dessin des images… {k + 1}/{n}")
    segs = []
    f_prev = 0
    for k, p in enumerate(panels):
        f_end = int(round((p["end"] if k < n - 1 else duration) * FPS))
        frames = max(1, f_end - f_prev)
        f_prev = f_end
        seg = str(tmp / f"v{k:03d}.mp4")
        sp = pspec[k] if k < len(pspec) else pspec[-1]
        _segment(scenes[k], p.get("_header"), frames, sp.get("frame", "medium"), k, seg)
        segs.append(seg)
        if progress and (k % 10 == 0 or k == n - 1):
            progress(66 + int(8 * (k + 1) / max(1, n)), f"🎞️ [3/4] Montage des images… {k + 1}/{n}")
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{Path(s).name}'\n" for s in segs), encoding="utf-8")
    res = subprocess.run([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", out_mp4],
                         capture_output=True, text=True, timeout=300, cwd=str(tmp))
    if res.returncode != 0 or not os.path.exists(out_mp4):
        raise RuntimeError(f"Assemblage impossible : {res.stderr[-400:]}")
    if not work_dir:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_mp4


def render_story(session_id: str, script: Dict[str, Any], plan: Dict[str, Any], words: List[Dict[str, Any]],
                 duration: float, out_dir: Path, model: Optional[str] = None, da_hint: str = "",
                 progress: Optional[Callable[[int, str], None]] = None) -> str:
    """Point d'entrée du pipeline : renvoie la vidéo de fond (mp4 sans son)."""
    beats = [float(s.get("start", 0)) for s in (plan.get("shots") or [])[1:]]
    panels = build_panels(words, duration, beats)
    if progress:
        progress(55, f"🖍️ [3/4] Claude met en scène {len(panels)} images dessinées…")
    spec = design(script, panels, model=model, da_hint=da_hint)
    try:
        with open(Path(out_dir) / f"{session_id}_toon_spec.json", "w", encoding="utf-8") as f:
            json.dump({"panels_timing": panels, **spec}, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    out = str(Path(out_dir) / f"{session_id}_toon_bg.mp4")
    return render_video(spec, panels, duration, out, progress)
