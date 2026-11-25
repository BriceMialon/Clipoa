"""
Analyse d'une vidéo de référence (YouTube, Shorts, Reels, TikTok, X) pour en faire un STYLE Clipoa :
l'agent télécharge la vidéo, mesure son rythme (coupes, durée des plans, débit de parole), en tire des
planches d'images, transcrit la voix, puis l'IA choisie rédige la Direction Artistique (DA), les règles
narratives et les réglages de production, et choisit le moteur de rendu Blender le plus proche.
Le style créé est ensuite utilisé comme n'importe quel style : « même style, autre histoire ».
"""
import json
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from config import FFMPEG_PATH, DOWNLOADS_DIR

RENDERERS = {
    "roblox": "personnages CUBIQUES en blocs (tête carrée ou cylindrique, corps et membres rectangulaires, visage autocollant) dans un monde 3D de jeu vidéo low-poly",
    "paper2d": "personnages 2D en traits très simples (grosse tête ronde blanche, membres bâtons fins) collés dans un décor 3D TEXTURÉ quasi réaliste (pavés, bois, rues)",
    "explainer2d": "DESSIN ANIMÉ cartoon : contours épais foncés sur tout, couleurs vives en aplats avec ombre douce, décors dessinés (ciel bleu, bâtiments, objets), "
                   "personnages cartoon expressifs (grosse tête ronde, grands yeux, chapeau, tenue de métier), cadrage de face ; c'est le moteur des dessins animés « toon » "
                   "même quand quelques objets ont l'air en volume",
    "flat_vector": "motion design en aplats très saturés SANS contours, formes géométriques, peu ou pas de personnages détaillés",
}


def _run(cmd: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def measure_video(video_path: str) -> Dict[str, Any]:
    """Durée, coupes (changements de plan) et durée moyenne des plans."""
    res = _run([FFMPEG_PATH, "-hide_banner", "-i", video_path, "-vf", "select='gt(scene,0.32)',showinfo", "-f", "null", "-"], 300)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    cuts: List[float] = []
    for t in re.findall(r"pts_time:([0-9.]+)", res.stderr):
        t = float(t)
        if not cuts or t - cuts[-1] > 0.4:
            cuts.append(round(t, 2))
    shots = len(cuts) + 1
    return {"duration_s": round(dur, 1), "cuts_s": cuts[:80], "shots": shots, "avg_shot_s": round(dur / max(1, shots), 2)}


def make_sheets(video_path: str, out_dir: Path, duration: float) -> List[str]:
    """Deux planches : vue d'ensemble (30 images) + 6 images clés en plus grand."""
    out_dir.mkdir(parents=True, exist_ok=True)
    every = max(0.5, duration / 30.0)
    a = out_dir / "planche_ensemble.jpg"
    _run([FFMPEG_PATH, "-y", "-i", video_path, "-vf", f"fps=1/{every:.3f},scale=216:384,tile=6x5", "-frames:v", "1", "-q:v", "4", str(a)])
    b = out_dir / "planche_details.jpg"
    step = max(0.5, duration / 6.0)
    _run([FFMPEG_PATH, "-y", "-i", video_path, "-vf", f"fps=1/{step:.3f},scale=360:640,tile=3x2", "-frames:v", "1", "-q:v", "3", str(b)])
    cover = out_dir / "cover.jpg"
    _run([FFMPEG_PATH, "-y", "-ss", f"{max(0.5, duration * 0.35):.2f}", "-i", video_path, "-frames:v", "1", "-vf", "scale=540:960", "-q:v", "3", str(cover)])
    return [str(p) for p in (a, b) if p.exists()]


def build_prompt(meta: Dict[str, Any], stats: Dict[str, Any], transcript_txt: str, words_per_s: float, with_images: bool) -> str:
    renderers = "\n".join(f"- {k} : {v}" for k, v in RENDERERS.items())
    look = ("Regarde les deux planches : planche_ensemble = 30 images réparties sur toute la vidéo ; planche_details = 6 images clés en grand.\n"
            if with_images else "Tu n'as pas les images : déduis le style du titre, de la description et du texte parlé, et dis-le dans « confidence ».\n")
    return f"""Tu es directeur artistique et monteur de vidéos courtes. Analyse cette vidéo de référence pour que n'importe qui puisse
refaire une vidéo EXACTEMENT dans ce style (rendu, couleurs, cadrage, rythme, texte à l'écran, son, narration), avec une autre histoire.
{look}
Titre : {meta.get('title', '')}
Auteur : {meta.get('uploader', '')}
Description : {str(meta.get('description', ''))[:400]}
Mesures : durée {stats.get('duration_s')} s ; {stats.get('shots')} plans ; plan moyen {stats.get('avg_shot_s')} s ; débit de parole {words_per_s:.1f} mots/s.
Texte parlé (horodaté) :
{transcript_txt[:2500]}

Clipoa rend les vidéos avec Blender. Moteurs disponibles :
{renderers}
Pour CHAQUE moteur, donne une note de ressemblance de 0 à 10 avec les images (« renderer_scores ») en regardant d'abord les PERSONNAGES
(cubiques ? traits bâtons ? dessin animé à contours ?) puis le décor ; « renderer » = le mieux noté.
« palette » = les vraies couleurs dominantes des images (ciel, sol / murs, couleur d'accent). « hud » = des compteurs ou infos fixes affichés
en permanence (souvent en haut, ex. « JOURS SANS … : 3 », « ALTITUDE : 5 M ») qui changent pendant la vidéo : enabled true seulement s'il y en a.

Réponds UNIQUEMENT avec un JSON valide :
{{
  "name": "nom court du style (2-4 mots, sans nom de marque ni de créateur)",
  "icon": "un emoji",
  "tagline": "une phrase qui décrit le rendu",
  "tool_guess": "outil probable utilisé par le créateur (ex. After Effects, Blender, IA vidéo, Canva, CapCut, Roblox Studio…) et pourquoi, en une phrase",
  "renderer_scores": {{"roblox": 0, "paper2d": 0, "explainer2d": 0, "flat_vector": 0}},
  "renderer": "roblox|paper2d|flat_vector|explainer2d",
  "time_of_day": "day|sunset|night (lumière dominante de la vidéo)",
  "hud": {{"enabled": false, "examples": ["COMPTEUR : 0"], "color": "#RRGGBB"}},
  "confidence": "élevée|moyenne|faible + ce qui manque",
  "da_prompt": "STYLE BIBLE en Markdown, 500 à 900 mots, sections : 1. L'ADN ; 2. Format (durée, rythme, zones sûres) ; 3. Direction artistique (rendu, palette avec codes hex, contours, lumière, personnages, décors) ; 4. Texte à l'écran / sous-titres (format exact) ; 5. Caméra et montage (types de plans, transitions) ; 6. Son (voix, musique, bruitages) ; 7. Phrases-ancres de prompt en anglais. Ne copie ni personnages, ni noms, ni textes de la référence : décris le STYLE.",
  "narrative_rules": "structure narrative en 5 à 8 étapes avec les timings, ton et personne grammaticale (tu/vous/je), types de phrases",
  "production": {{
    "mood": "dark|tension|upbeat|calm",
    "shot_min_s": 1.0, "shot_max_s": 4.0,
    "caption_mode": "chunk|one_word|two_words|none",
    "keyword_colors": true,
    "music_db": -18,
    "note_color": "#RRGGBB"
  }},
  "palette": {{"sky": "#RRGGBB", "ground": "#RRGGBB", "accent": "#RRGGBB"}},
  "subtitle_style": "submagic_yellow|shortcrew_red|neon_green|cyber_cyan|clean_white"
}}"""


def pick_renderer(a: Dict[str, Any]) -> str:
    """Moteur le mieux noté par l'IA (notes 0-10 par moteur) ; sinon son choix direct ; sinon le dessin animé."""
    scores = a.get("renderer_scores") if isinstance(a.get("renderer_scores"), dict) else {}
    best, best_v = "", -1.0
    for k in RENDERERS:
        try:
            v = float(scores.get(k))
        except (TypeError, ValueError):
            continue
        if v > best_v:
            best, best_v = k, v
    if best and best_v > 0:
        return best
    return a.get("renderer") if a.get("renderer") in RENDERERS else "explainer2d"


def _parse(raw: str) -> Optional[Dict[str, Any]]:
    txt = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1)
    try:
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception:
        return None


def analyze_reference(
    url: str,
    engine: str = "claude",
    model: Optional[str] = None,
    progress: Optional[Callable[[int, str], None]] = None,
    cookies_from_browser: Optional[str] = None,
) -> Dict[str, Any]:
    """Télécharge et analyse la vidéo ; renvoie {analysis, stats, sheets, cover, meta, vision}."""
    from core.scraper import CompetitorScraper
    from core.transcriber import AudioTranscriber

    def _p(pct: int, msg: str):
        print(msg)
        if progress:
            progress(pct, msg)

    work_id = f"styleref_{int(time.time())}_{uuid.uuid4().hex[:5]}"
    _p(5, "📥 Téléchargement de la vidéo d'exemple...")
    dl = CompetitorScraper.download_video(url, output_id=work_id, cookies_from_browser=cookies_from_browser, extract_frames=False)
    video_path = dl["video_path"]
    meta = dl.get("metadata") or {}
    _p(15, "📏 Mesure du rythme (coupes, durée des plans)...")
    stats = measure_video(video_path)
    sheets_dir = DOWNLOADS_DIR / work_id / "analyse"
    sheets = make_sheets(video_path, sheets_dir, stats["duration_s"] or 30.0)
    _p(22, "🎙️ Écoute de la voix (transcription)...")
    transcript_txt, n_words = "", 0
    ref_words: List[Dict[str, Any]] = []
    try:
        tr = AudioTranscriber.transcribe(dl["audio_path"])
        for seg in tr.get("segments", []):
            transcript_txt += f'{float(seg.get("start", 0)):.1f}-{float(seg.get("end", 0)):.1f} {str(seg.get("text", "")).strip()}\n'
            n_words += len(str(seg.get("text", "")).split())
            # mots horodatés (pour la planche de contrôle du moteur sur mesure)
            toks = str(seg.get("text", "")).split()
            s0, s1 = float(seg.get("start", 0)), float(seg.get("end", 0))
            for k, tok in enumerate(toks):
                ref_words.append({"word": tok, "start": s0 + (s1 - s0) * k / max(1, len(toks)),
                                  "end": s0 + (s1 - s0) * (k + 1) / max(1, len(toks))})
    except Exception as e:
        transcript_txt = f"(transcription impossible : {e})"
    wps = n_words / max(1.0, stats["duration_s"])

    vision = False
    raw = ""
    if (engine or "claude") != "antigravity":
        from core.claude_bridge import ClaudeBridge
        _p(35, "👀 Claude regarde la vidéo image par image et décrit le style...")
        try:
            raw = ClaudeBridge.query_with_images(build_prompt(meta, stats, transcript_txt, wps, True), sheets, action="style_analysis")
            vision = True
        except Exception as e:
            print(f"⚠️ Analyse d'images Claude impossible ({e}) : analyse sans images.")
            raw = ClaudeBridge.query(build_prompt(meta, stats, transcript_txt, wps, False), action="style_analysis")
    else:
        from core.antigravity_bridge import AntigravityBridge
        _p(35, "🧠 Antigravity analyse la vidéo (mesures + voix + description)...")
        raw = AntigravityBridge.query(build_prompt(meta, stats, transcript_txt, wps, False), model=model, timeout=300)
    analysis = _parse(raw)
    if not analysis or not analysis.get("da_prompt"):
        raise RuntimeError("L'IA n'a pas pu décrire le style de cette vidéo. Réessaie ou choisis une autre vidéo.")
    return {
        "analysis": analysis,
        "stats": stats,
        "sheets": sheets,
        "cover": str(sheets_dir / "cover.jpg") if (sheets_dir / "cover.jpg").exists() else "",
        "meta": meta,
        "vision": vision,
        "words_per_s": round(wps, 2),
        "source_url": url,
        "video_path": video_path,
        "words": ref_words,
    }


def create_style_from_reference(
    url: str,
    engine: str = "claude",
    model: Optional[str] = None,
    progress: Optional[Callable[[int, str], None]] = None,
    hidden: bool = False,
) -> Dict[str, Any]:
    """Analyse la vidéo et enregistre un nouveau style (plugin) prêt à l'emploi dans Clipoa.
    hidden=True (lien collé dans la Fabrique) : style interne à cette vidéo, absent de la liste des styles."""
    from core.style_plugins import StylePluginStore, sanitize_production
    res = analyze_reference(url, engine=engine, model=model, progress=progress)
    a = res["analysis"]
    renderer = pick_renderer(a)
    prod = dict(a.get("production") or {})
    prod["visual_style"] = renderer
    # la vidéo copiée garde SES couleurs, SA lumière et ses compteurs à l'écran
    if isinstance(a.get("palette"), dict):
        prod["palette"] = a["palette"]
    if a.get("time_of_day") in ("day", "sunset", "night"):
        prod["time_of_day"] = a["time_of_day"]
    hud = a.get("hud") if isinstance(a.get("hud"), dict) else {}
    if hud.get("enabled"):
        prod["hud"] = True
        if hud.get("color"):
            prod["hud_color"] = hud["color"]
    if renderer in ("paper2d",):
        prod["character_style"] = "flat2d"
    stats = res["stats"]
    if stats.get("avg_shot_s") and "shot_max_s" not in (a.get("production") or {}):
        prod["shot_max_s"] = max(2.0, min(8.0, stats["avg_shot_s"] * 1.5))
    production = sanitize_production(prod)
    if progress:
        progress(55, f"🎨 Création du style « {a.get('name', 'Mon style')} »...")
    tool = str(a.get("tool_guess") or "")
    da = str(a.get("da_prompt") or "")
    da += (
        f"\n\n## Origine de ce style\nAnalysé automatiquement par Clipoa depuis une vidéo d'exemple ({res['meta'].get('uploader') or 'source externe'}). "
        f"Mesures : {stats.get('duration_s')} s, {stats.get('shots')} plans, plan moyen {stats.get('avg_shot_s')} s, {res['words_per_s']} mots/s."
        + (f"\nOutil probable du créateur : {tool}" if tool else "")
    )
    if hud.get("enabled"):
        ex = ", ".join(f"« {e} »" for e in (hud.get("examples") or [])[:3] if e)
        da += (
            "\n\n## Compteurs à l'écran (signature de ce style)\n"
            "En haut à gauche, 1 à 2 lignes fixes en MAJUSCULES qui évoluent avec l'histoire (chiffre qui monte ou qui retombe), "
            f"dans l'esprit de {ex or '« COMPTEUR : 0 »'} mais avec le sujet de la nouvelle histoire. Le script les donne dans « hud »."
        )
    plugin = StylePluginStore.create_plugin({
        "name": str(a.get("name") or "Style importé")[:50],
        "icon": str(a.get("icon") or "🎬")[:8],
        "category": "Importé",
        "gradient": "custom",
        "tagline": str(a.get("tagline") or "")[:200],
        "da_prompt": da,
        "narrative_rules": str(a.get("narrative_rules") or ""),
        "render_mode": "blender3d",
        "theme": "pop_flat" if renderer in ("explainer2d", "flat_vector") else "dark_luxury",
        "subtitle_style": a.get("subtitle_style") if a.get("subtitle_style") in ("submagic_yellow", "shortcrew_red", "neon_green", "cyber_cyan", "clean_white") else "submagic_yellow",
        "production": production,
    })
    if res.get("cover"):
        try:
            StylePluginStore.attach_local_sheet(plugin["id"], res["cover"], "reference")
        except Exception as e:
            print(f"⚠️ Vignette non ajoutée ({e})")
    if hidden:
        StylePluginStore.set_hidden(plugin["id"], True)
    # Moteur SUR MESURE : l'IA choisit l'outil (page animée / three.js, ou Blender) et écrit le moteur de CE style.
    # Les moteurs intégrés ne servent plus qu'en secours (production.fallback_style).
    try:
        from core import custom_engine
        made = custom_engine.design_style_engine(
            plugin["id"], dict(a, palette=a.get("palette") or {}), res.get("sheets") or [], res.get("words") or [],
            float(stats.get("duration_s") or 20.0), engine=engine, model=model, progress=progress,
        )
        StylePluginStore.update_plugin(plugin["id"], {"production": dict(production, visual_style="custom", fallback_style=renderer)})
        tool = f"{made['tool']} (sur mesure) — {made.get('why') or tool}"
        renderer = "custom"
    except Exception as e:
        print(f"⚠️ Moteur sur mesure impossible ({e}) : style intégré le plus proche ({renderer}).")
    # la vidéo d'exemple devient la vidéo de référence du style (montrée quand on clique dessus)
    try:
        if res.get("video_path"):
            StylePluginStore.set_reference_video(plugin["id"], src_path=res["video_path"], source_url=url)
        else:
            StylePluginStore.update_plugin(plugin["id"], {"reference_url": url})
    except Exception as e:
        print(f"⚠️ Vidéo de référence non gardée ({e})")
    plugin = StylePluginStore.get_plugin(plugin["id"], include_script_body=False) or plugin
    return {
        "plugin": plugin,
        "renderer": renderer,
        "tool_guess": tool,
        "confidence": a.get("confidence", ""),
        "vision": res["vision"],
        "stats": stats,
        "palette": a.get("palette") or {},
    }
