"""
Style « Carte animée » (vidéo géographie) : une caméra qui survole une carte du monde, pays colorés,
étiquettes, drapeaux, flèches, dates, petits personnages chibi, calé mot à mot sur la voix.

Moteur de carte : « Geo Kit » de Caesar (@caesarscales), licence MIT
(github.com/Caesarscales/Geography-Map-Style-Animations). Il n'est PAS copié dans le dépôt ClipRoll :
au premier usage, ClipRoll télécharge les seuls fichiers utiles (~55 Mo) au commit figé dans
`core/geo_kit_manifest.json`, et vérifie l'empreinte SHA-256 de chacun. LICENSE et CREDITS.md
sont gardés avec les fichiers. Les cartes viennent de NASA Blue Marble et Natural Earth (domaine public),
les drapeaux de flag-icons (MIT), les polices sont sous licence OFL.

Rendu : Chrome sans fenêtre (Playwright Python, déjà utilisé par les styles dessinés), pas de Node.js.
Claude écrit la liste de « beats » (format du kit) ; ClipRoll la nettoie, vérifie chaque lieu et rend
la vidéo de fond (sans son). Voix, musique, bruitages et sous-titres restent ceux de ClipRoll.
"""
import functools
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import BASE_DIR, FFMPEG_PATH, STORAGE_DIR

MANIFEST_FILE = BASE_DIR / "core" / "geo_kit_manifest.json"
KIT_DIR = Path(os.environ.get("CLIPOA_GEO_RUNTIME", str(STORAGE_DIR / "geo_runtime"))) / "kit"
W, H, FPS = 1080, 1920, 30
_INSTALL_LOCK = threading.Lock()

# ───────────────────────────── Installation (au premier usage) ─────────────────────────────


def manifest() -> Dict[str, Any]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _safe_rel(rel: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_./-]+$", rel)) and ".." not in rel and not rel.startswith("/")


def missing_files() -> List[str]:
    """Fichiers absents ou de mauvaise taille (contrôle rapide ; l'empreinte est vérifiée au téléchargement)."""
    out = []
    for rel, (size, _h) in manifest()["files"].items():
        p = KIT_DIR / rel
        if not p.is_file() or p.stat().st_size != size:
            out.append(rel)
    return out


def is_installed() -> bool:
    try:
        return not missing_files()
    except Exception:
        return False


def is_available() -> bool:
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    return True


def status() -> Dict[str, Any]:
    m = manifest()
    miss = missing_files()
    return {"installed": not miss, "missing": len(miss), "files": len(m["files"]),
            "size_mb": round(sum(v[0] for v in m["files"].values()) / 1e6, 1),
            "commit": m["commit"], "credit": "Geo Kit — Caesar (@caesarscales), licence MIT"}


def install(progress: Optional[Callable[[int, str], None]] = None) -> None:
    """Télécharge les fichiers manquants au commit figé et vérifie chaque empreinte SHA-256."""
    with _INSTALL_LOCK:
        m = manifest()
        miss = missing_files()
        if not miss:
            return
        base = f"https://raw.githubusercontent.com/{m['repo']}/{m['commit']}/"
        for i, rel in enumerate(miss):
            if not _safe_rel(rel):
                raise RuntimeError(f"chemin refusé dans le manifeste : {rel}")
            size, want = m["files"][rel]
            dest = KIT_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".part")
            req = urllib.request.Request(base + rel, headers={"User-Agent": "cliproll-geo-setup/1.0"})
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                        shutil.copyfileobj(r, f, 1 << 20)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 * (attempt + 1))
            if _sha(tmp) != want:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"empreinte incorrecte pour {rel} (téléchargement refusé)")
            os.replace(tmp, dest)
            if progress and (i % 10 == 0 or i == len(miss) - 1):
                progress(i + 1, f"🗺️ Installation des cartes ({i + 1}/{len(miss)} fichiers)")


# ───────────────────────────── Lieux connus (vérifiés avant le rendu) ─────────────────────────────

@functools.lru_cache(maxsize=1)
def _gazetteer() -> Dict[str, Any]:
    d = KIT_DIR / "engine" / "data" / "world"
    C = json.loads((d / "countries.json").read_text(encoding="utf-8"))
    S = json.loads((d / "states.json").read_text(encoding="utf-8"))
    names = set()
    for k, v in C.items():
        names.add(k.lower())
        names.update(str(x).lower() for x in (v.get("names") or []))
    for k, v in S.items():
        names.add(k.lower())
        names.add(str(v.get("name") or "").lower())
    for p in json.loads((d / "places.json").read_text(encoding="utf-8")):
        names.add(str(p[0]).lower())
    for s in json.loads((d / "seas.json").read_text(encoding="utf-8")):
        names.add(str(s[0] or "").lower())
    names.update(["korea", "korean peninsula", "latin america", "europe", "middle east", "usa", "us", "uk", "britain",
                  "united states", "soviet union", "ussr"])
    names.discard("")
    return {"names": names, "iso3": sorted(C)}


def _known_place(name: str, gaz: Dict[str, Any]) -> bool:
    parts = [p.strip().lower() for p in str(name).split("+")]
    return all(p in gaz["names"] for p in parts) and bool(parts)


# ───────────────────────────── Ce que Claude écrit ─────────────────────────────

BEAT_TYPES = {
    "skin", "clouds", "fill", "front", "cutout", "focus", "label", "maplabel", "flag", "pin", "ring", "arrow", "line",
    "sprite", "chibi", "tag", "bubble", "emblem", "badge", "explosions", "fire", "lens", "scribble", "reticle", "googly",
    "question", "date", "title", "firetitle", "neon", "document", "calendar", "stamp", "vignette", "flash", "whip",
    "scene", "endcard",
}
SKINS = {"sat", "atlas", "old", "blueprint", "teal", "war", "grey", "minimal", "paperwhite"}
BADGE_ICONS = {"skull", "medic", "missing", "people", "money"}
SCENE_CODES = {"mountains"}
PLACE_KEYS = ("at", "from", "to", "target", "origin")
_TIME_RE = re.compile(r"^w\d{1,4}e?([+-]\d{1,3}(\.\d+)?)?$")


def library_sprites() -> List[str]:
    try:
        return sorted(p.stem for p in (KIT_DIR / "chibi" / "library").glob("*.png"))
    except Exception:
        return []


def build_prompt(script: Dict[str, Any], words: List[List[Any]], duration: float, da_hint: str = "") -> str:
    lines = " ".join(f"w{i}:{w[2]}@{w[0]:.2f}" for i, w in enumerate(words))
    sprites = ", ".join(library_sprites()) or "aucun"
    title = str(script.get("title") or script.get("hook_screen_text") or "")[:120]
    return f"""Tu es monteur de Shorts « géographie sur carte animée » (9:16, 1080×1920, 30 i/s).
Tu écris la liste de beats d'une vidéo pour un moteur de carte. Réponds UNIQUEMENT avec un objet JSON :
{{"camera": [...], "beats": [...]}}

SUJET : {title}
DURÉE DE LA VOIX : {duration:.1f} s
MOTS DE LA VOIX (index:mot@début en s) : {lines}
{('DIRECTION ARTISTIQUE : ' + da_hint[:1500]) if da_hint else ''}

TEMPS (`t`, `until`) : nombre de secondes, ou "w12" (début du mot 12), "w12e" (fin du mot 12), "w12+0.3".
Accroche CHAQUE beat à un mot de la voix : c'est ce qui donne l'impression d'un vrai montage.

LIEUX (`at`, `from`, `to`, `target`) : code pays ISO3 ("FRA", "RUS", "USA"), nom ANGLAIS de pays ("Russia"),
État "USA:Alaska", ville en anglais ("Moscow"), mer ("Bering Sea"), union "PRK+KOR", ou coordonnées [lon, lat].
Jamais de nom français (« Russie » ne marche pas). Décalages : {{"place": "FRA", "dx": 90, "dy": -120}}. Écran fixe : {{"screen": [540, 900]}}.

CAMÉRA : liste de clés {{"t", "at", "zoom"}} ; zoom = pixels par degré (≈10 monde, 40 un pays, 100 une région,
250 gros plan). Sans zoom, elle cadre le lieu. La caméra ne s'arrête jamais ; prévois une clé tous les 2 à 5 s,
autant de zooms avant que de zooms arrière, aucun « cut ». Première clé à t=0.

TYPES DE BEATS (paramètres principaux) :
- skin : look de la carte, kind = sat | atlas | old | blueprint | teal | war | grey | minimal | paperwhite ; transition = fade | wipe | blob | iris
- clouds : plongée dans les nuages au début (dur)
- fill : colorie un pays/État/liste : target, color (#hex), style = flash | fade | spread | wipe | pulse
- front : couleur qui avance sur un pays (ligne de front) : target, color, from, to
- focus : tout en gris sauf target
- label : nom de pays blanc tapé lettre par lettre + drapeau : text, at, flag (ISO3)
- maplabel : nom de mer/région en italique : text, at
- flag : drapeau qui flotte : flag (ISO3, ou USSR, UN, UK_OLD, AUSTRIA_HUNGARY), at, size
- pin : épingle rouge + anneaux + étiquette : at, label
- ring : anneaux qui s'étendent : at, color
- arrow : flèche blanche courbe : from, to, bend
- line : route lumineuse : points [[lon,lat],...], color
- sprite / chibi : objet ou personnage de la bibliothèque : sprite ou chibi = un de [{sprites}], at ou path, size, count
- tag : petite boîte nom/année : text, at, bg, fg
- bubble : bulle de dialogue : text, at
- badge : pastille chiffrée : icon = skull | medic | missing | people | money, number, label, at
- explosions / fire : at, count
- lens, scribble, reticle, googly, question : at
- date : grosse date qui claque : text ("1867"), style = neon | gold | white | cream | fire
- title : titre de chapitre deux couleurs : lines [["Le", "#ffffff"], ["Twist", "#E42D2D"]]
- neon : phrase lumineuse : text
- document : vieux document : title, lines, highlight ; calendar : text ["1860","1867"] ; stamp : text
- vignette / flash / whip : effets
- endcard : globe de fin : text
Paramètres communs : id, until, dur.

RÈGLES DU STYLE :
- Une seule carte, un seul plan continu : on voyage d'un lieu à l'autre, jamais de coupe.
- Il se passe toujours quelque chose : un nouveau beat toutes les 1 à 2 s (au moins {max(8, int(duration / 1.6))} beats).
- Commence par clouds + skin "sat", passe en skin "atlas" pour l'histoire, finis par un endcard.
- Couleurs de pays franches (#F2F21C jaune, #2D7DD2 bleu, #D8111C rouge, #2BB673 vert), drapeaux sur les pays cités,
  une date qui claque à chaque année importante, des flèches pour les déplacements.
- Les textes à l'écran (label, tag, title, date…) sont en FRANÇAIS, courts (1 à 4 mots). Ne remets pas les sous-titres :
  ils sont ajoutés au montage.
- Personnages et objets : seulement ceux de la bibliothèque ci-dessus, petits sur la carte.
"""


def _clean_value(v: Any, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return max(-1e6, min(1e6, float(v))) if isinstance(v, float) else max(-10 ** 6, min(10 ** 6, v))
    if isinstance(v, str):
        return v[:80]
    if isinstance(v, list):
        return [x for x in (_clean_value(x, depth + 1) for x in v[:60]) if x is not None]
    if isinstance(v, dict):
        out = {}
        for k, x in list(v.items())[:30]:
            if isinstance(k, str) and re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,24}$", k):
                cx = _clean_value(x, depth + 1)
                if cx is not None:
                    out[k] = cx
        return out
    return None


def _ok_time(t: Any, nwords: int) -> bool:
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return 0 <= t <= 600
    if isinstance(t, str) and _TIME_RE.match(t):
        return int(re.match(r"^w(\d+)", t).group(1)) < max(1, nwords)
    return False


def _ok_place(at: Any, gaz: Dict[str, Any]) -> bool:
    if isinstance(at, list):
        return len(at) == 2 and all(isinstance(x, (int, float)) for x in at) and -180 <= at[0] <= 360 and -85 <= at[1] <= 85
    if isinstance(at, str):
        return _known_place(at, gaz)
    if isinstance(at, dict):
        if "screen" in at:
            s = at["screen"]
            return isinstance(s, list) and len(s) == 2 and all(isinstance(x, (int, float)) for x in s)
        if "follow" in at:
            return isinstance(at["follow"], str)
        return _ok_place(at.get("place"), gaz)
    return False


def _ok_target(t: Any, gaz: Dict[str, Any]) -> bool:
    if isinstance(t, list):
        return bool(t) and all(isinstance(x, str) and _known_place(x, gaz) for x in t)
    return isinstance(t, str) and _known_place(t, gaz)


def sanitize(raw: Dict[str, Any], nwords: int, gaz: Dict[str, Any], sprites: List[str]) -> Optional[Dict[str, Any]]:
    """Garde seulement des beats connus, à des moments et des lieux valides. None si rien d'utilisable."""
    if not isinstance(raw, dict):
        return None
    cam = []
    for k in (raw.get("camera") or [])[:80]:
        k = _clean_value(k)
        if not isinstance(k, dict) or not _ok_time(k.get("t"), nwords):
            continue
        if "follow" in k:
            if isinstance(k["follow"], str) and _ok_time(k.get("until"), nwords):
                cam.append({x: k[x] for x in ("t", "follow", "until", "zoom") if x in k})
            continue
        if not _ok_place(k.get("at"), gaz):
            continue
        cam.append({x: k[x] for x in ("t", "at", "zoom", "fit", "rot", "dlon", "dlat") if x in k})
    beats = []
    sp = set(sprites)
    for b in (raw.get("beats") or [])[:160]:
        b = _clean_value(b)
        if not isinstance(b, dict) or b.get("type") not in BEAT_TYPES or not _ok_time(b.get("t", 0), nwords):
            continue
        if "until" in b and not _ok_time(b["until"], nwords):
            b.pop("until")
        if not all(_ok_target(b[k], gaz) if k == "target" else _ok_place(b[k], gaz) for k in PLACE_KEYS if k in b):
            continue
        # aucun fichier du projet : pas d'image importée, icônes et décors prédéfinis seulement
        b.pop("image", None)
        b.pop("sfx", None)
        if b["type"] == "scene" and b.get("code") not in SCENE_CODES:
            b["code"] = "mountains"
        if b["type"] == "badge" and b.get("icon") not in BADGE_ICONS:
            b["icon"] = "people"
        if b["type"] == "emblem" and b.get("icon") != "un":
            continue
        if b["type"] == "skin" and b.get("kind") not in SKINS:
            b["kind"] = "atlas"
        if b["type"] in ("sprite", "chibi"):
            name = b.get(b["type"])
            if name not in sp:
                continue
        if b.get("sprite") and b["sprite"] not in sp:
            continue
        beats.append(b)
    if len(cam) < 2 or len(beats) < 4:
        return None
    return {"camera": cam, "beats": beats}


def heuristic_spec(words: List[List[Any]], duration: float) -> Dict[str, Any]:
    """Repli sans IA : tour du monde lent, nuages, changement de carte, fin."""
    tour = ["FRA", "EGY", "IND", "CHN", "JPN", "AUS", "BRA", "USA"]
    cam = [{"t": 0, "at": [10, 30], "zoom": 8}]
    n = max(1, int(duration // 4))
    for i in range(n):
        cam.append({"t": round(min(duration, 2 + i * 4), 2), "at": tour[i % len(tour)], "zoom": 26 if i % 2 else 18})
    beats = [{"t": 0, "type": "clouds", "dur": 1.2}, {"t": 0, "type": "skin", "kind": "sat"},
             {"t": 3, "type": "skin", "kind": "atlas", "transition": "blob"}]
    for i in range(n):
        beats.append({"t": round(2.4 + i * 4, 2), "type": "fill", "target": tour[i % len(tour)], "color": "#F2F21C", "style": "flash",
                      "until": round(2.4 + i * 4 + 3.6, 2)})
    beats.append({"t": max(0.0, round(duration - 2.2, 2)), "type": "endcard", "text": ""})
    return {"camera": cam, "beats": beats}


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    txt = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1)
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None


def to_kit_words(words: List[Dict[str, Any]]) -> List[List[Any]]:
    out = []
    for w in words or []:
        if not isinstance(w, dict) or "start" not in w:
            continue
        s = float(w["start"])
        e = float(w.get("end", s + 0.25))
        out.append([round(s, 3), round(max(e, s + 0.05), 3), str(w.get("word") or w.get("text") or "").strip()[:40]])
    return out


def design(script: Dict[str, Any], words: List[List[Any]], duration: float, model: Optional[str] = None,
           da_hint: str = "") -> Dict[str, Any]:
    gaz = _gazetteer()
    raw = ""
    try:
        from core.claude_bridge import ClaudeBridge
        raw = ClaudeBridge.query(build_prompt(script, words, duration, da_hint), action="geo_design", model=model)
    except Exception as e:
        print(f"⚠️ Mise en scène IA indisponible ({e}) : tour du monde par défaut.")
    spec = sanitize(_parse_json(raw) or {}, len(words), gaz, library_sprites()) if raw else None
    if spec:
        spec["_source"] = "ia"
        return spec
    spec = heuristic_spec(words, duration)
    spec["_source"] = "repli"
    return spec


# ───────────────────────────── Rendu ─────────────────────────────

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(root: Path):
    handler = functools.partial(_QuietHandler, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def render_video(spec: Dict[str, Any], words: List[List[Any]], duration: float, out_mp4: str, project: str,
                 progress: Optional[Callable[[int, str], None]] = None, fps: int = FPS) -> str:
    """Rend la vidéo de fond (sans son) : une image du moteur de carte par image vidéo."""
    from playwright.sync_api import sync_playwright
    pdir = KIT_DIR / "projects" / project
    pdir.mkdir(parents=True, exist_ok=True)
    meta = {"title": project, "words": "words.json", "watermark": "", "regions": [], "region_defs": {},
            "duration": round(float(duration), 3)}
    (pdir / "beats.json").write_text(json.dumps({"meta": meta, "camera": spec["camera"], "beats": spec["beats"]}), encoding="utf-8")
    (pdir / "words.json").write_text(json.dumps(words), encoding="utf-8")
    (pdir / "captions.json").write_text("[]", encoding="utf-8")  # sous-titres ajoutés au montage ClipRoll
    srv = _serve(KIT_DIR)
    step = max(1, round(FPS / max(1, fps)))
    ff = None
    try:
        with sync_playwright() as pw:
            exe = None
            try:
                from core.cine_setup import find_chrome
                exe = find_chrome()
            except Exception:
                exe = os.environ.get("CLIPOA_CHROME") or None
            args = ["--no-sandbox", "--font-render-hinting=none"]
            browser = pw.chromium.launch(executable_path=exe, args=args) if exe else pw.chromium.launch(args=args)
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            errors: List[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{srv.server_address[1]}/engine/page.html?p={project}")
            page.wait_for_function("window.ready", timeout=300000)
            if errors:
                raise RuntimeError("moteur de carte : " + errors[0][:200])
            total = int(page.evaluate("window.total"))
            ff = subprocess.Popen([FFMPEG_PATH, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS / step),
                                   "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                                   "-r", str(FPS / step), out_mp4], stdin=subprocess.PIPE)
            import base64
            t0 = time.time()
            frames = list(range(0, total, step))
            for i, f in enumerate(frames):
                d = page.evaluate("f => window.grab(f, 0.9)", f)
                ff.stdin.write(base64.b64decode(d.split(",", 1)[1]))
                if progress and i % 60 == 0:
                    eta = (time.time() - t0) / max(1, i) * (len(frames) - i)
                    progress(60 + int(26 * i / max(1, len(frames))),
                             f"🗺️ [3/4] Rendu de la carte… image {i}/{len(frames)} (~{int(eta)} s restantes)")
            browser.close()
        ff.stdin.close()
        if ff.wait(timeout=300) != 0:
            raise RuntimeError("FFmpeg n'a pas pu assembler la vidéo de la carte")
    finally:
        srv.shutdown()
        if ff and ff.poll() is None:
            ff.kill()
        shutil.rmtree(pdir, ignore_errors=True)
    return out_mp4


def render_story(session_id: str, script: Dict[str, Any], words: List[Dict[str, Any]], duration: float, out_dir: Path,
                 model: Optional[str] = None, da_hint: str = "", progress: Optional[Callable[[int, str], None]] = None,
                 quality: str = "hq") -> str:
    """Point d'entrée du pipeline : renvoie la vidéo de fond (mp4 sans son)."""
    if not is_installed():
        if progress:
            progress(55, "🗺️ Premier usage : téléchargement des cartes (~55 Mo, une seule fois)…")
        install(lambda i, msg: progress(55, msg) if progress else None)
        _gazetteer.cache_clear()
    kw = to_kit_words(words)
    if progress:
        progress(56, "🗺️ [3/4] Claude prépare le trajet de la caméra sur la carte…")
    spec = design(script, kw, duration, model=model, da_hint=da_hint)
    try:
        with open(Path(out_dir) / f"{session_id}_geo_beats.json", "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=1, ensure_ascii=False)
    except Exception:
        pass
    out = str(Path(out_dir) / f"{session_id}_geo_bg.mp4")
    project = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64] or "geo"
    return render_video(spec, kw, duration, out, project, progress, fps=15 if quality == "fast" else FPS)
