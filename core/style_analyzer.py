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
    "roblox": "3D en blocs façon Roblox / jeu vidéo low-poly (personnages R6, décors 3D)",
    "paper2d": "personnages 2D plats (papier découpé) dans un décor 3D low-poly",
    "flat_vector": "illustration vectorielle plate très saturée, sans contours, perspective 3D légère",
    "explainer2d": "dessin animé vectoriel de face (motion design 2D, explainer), contours fins, couleurs pastel ou franches",
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

Clipoa rend les vidéos avec Blender. Moteurs disponibles (choisis le plus proche) :
{renderers}

Réponds UNIQUEMENT avec un JSON valide :
{{
  "name": "nom court du style (2-4 mots, sans nom de marque ni de créateur)",
  "icon": "un emoji",
  "tagline": "une phrase qui décrit le rendu",
  "tool_guess": "outil probable utilisé par le créateur (ex. After Effects, Blender, IA vidéo, Canva, CapCut, Roblox Studio…) et pourquoi, en une phrase",
  "renderer": "roblox|paper2d|flat_vector|explainer2d",
  "confidence": "élevée|moyenne|faible + ce qui manque",
  "da_prompt": "STYLE BIBLE en Markdown, 500 à 900 mots, sections : 1. L'ADN ; 2. Format (durée, rythme, zones sûres) ; 3. Direction artistique (rendu, palette avec codes hex, contours, lumière, personnages, décors) ; 4. Texte à l'écran / sous-titres (format exact) ; 5. Caméra et montage (types de plans, transitions) ; 6. Son (voix, musique, bruitages) ; 7. Phrases-ancres de prompt en anglais. Ne copie ni personnages, ni noms, ni textes de la référence : décris le STYLE.",
  "narrative_rules": "structure narrative en 5 à 8 étapes avec les timings, ton et personne grammaticale (tu/vous/je), types de phrases",
  "production": {{
    "mood": "dark|tension|upbeat|calm",
    "shot_min_s": 1.0, "shot_max_s": 4.0,
    "caption_mode": "chunk|one_word|none",
    "keyword_colors": true,
    "music_db": -18,
    "note_color": "#RRGGBB"
  }},
  "palette": {{"sky": "#RRGGBB", "ground": "#RRGGBB", "accent": "#RRGGBB"}},
  "subtitle_style": "submagic_yellow|shortcrew_red|neon_green|cyber_cyan"
}}"""


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
    try:
        tr = AudioTranscriber.transcribe(dl["audio_path"])
        for seg in tr.get("segments", []):
            transcript_txt += f'{float(seg.get("start", 0)):.1f}-{float(seg.get("end", 0)):.1f} {str(seg.get("text", "")).strip()}\n'
            n_words += len(str(seg.get("text", "")).split())
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
    }


def create_style_from_reference(
    url: str,
    engine: str = "claude",
    model: Optional[str] = None,
    progress: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, Any]:
    """Analyse la vidéo et enregistre un nouveau style (plugin) prêt à l'emploi dans Clipoa."""
    from core.style_plugins import StylePluginStore, sanitize_production
    res = analyze_reference(url, engine=engine, model=model, progress=progress)
    a = res["analysis"]
    renderer = a.get("renderer") if a.get("renderer") in RENDERERS else "flat_vector"
    prod = dict(a.get("production") or {})
    prod["visual_style"] = renderer
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
        "subtitle_style": a.get("subtitle_style") if a.get("subtitle_style") in ("submagic_yellow", "shortcrew_red", "neon_green", "cyber_cyan") else "submagic_yellow",
        "production": production,
    })
    if res.get("cover"):
        try:
            StylePluginStore.attach_local_sheet(plugin["id"], res["cover"], "reference")
        except Exception as e:
            print(f"⚠️ Vignette non ajoutée ({e})")
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
