# -*- coding: utf-8 -*-
"""
Radar « S'inspirer » : les vidéos courtes FAITES À L'IA qui cartonnent EN CE MOMENT sur TikTok et Instagram Reels.

Pour chaque vidéo : vues, likes, commentaires, date de sortie, score viral /100 (vues, vitesse, engagement),
le style IA détecté et pourquoi elle marche. L'utilisateur copie le lien ou l'envoie directement dans
« Nouvelle vidéo » (champ « vidéo dont tu veux le style »).

L'IA utilisée est choisie toute seule (Claude si branché, sinon Gemini) ; sans IA,
le radar garde seulement le tri par mots-clés et par chiffres.
"""
import json
import math
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import STORAGE_DIR, YT_DLP_PATH

RADAR_FILE = STORAGE_DIR / "inspiration_radar.json"
_LOCK = threading.Lock()
_STATE = {"scanning": False, "progress": "", "error": ""}

# Recherches orientées contenu IA (le style des vidéos que ClipRoll sait refaire)
AI_QUERIES = {
    "fr": [
        "histoire ia animation", "dans ma ville roblox histoire", "vidéo ia dessin animé", "conte ia 3d",
        "animation ia histoire triste", "ia pixar histoire", "roblox story fr", "histoire inventée ia",
    ],
    "en": [
        "ai animation story", "in this town roblox story", "ai generated cartoon story", "ai 3d animation short",
        "roblox story sad", "ai pixar style story", "ai video viral story", "ai cartoon explainer",
    ],
}

# Indices qu'une vidéo est faite à l'IA / en animation générée (titre, description, hashtags, compte)
AI_HINTS = re.compile(
    r"(\b(ia|ai|a\.i\.)\b|#ia\b|#ai\b|aiart|aivideo|aianimation|animationia|vid[ée]oia|g[ée]n[ée]r[ée]e? par|generated|"
    r"\bveo\b|\bsora\b|\bkling\b|runway|midjourney|hailuo|pika|luma|chatgpt|gemini|"
    r"roblox|blender|\b3d\b|pixar|animation|anim[ée]e?|cartoon|dessin anim[ée]|brainrot|story ?time)",
    re.I,
)

MIN_VIEWS = 50_000
MAX_DURATION = 180


def _days_since(upload_date: str, ts: Optional[float]) -> Optional[float]:
    try:
        if ts:
            return max(0.0, (time.time() - float(ts)) / 86400.0)
        if upload_date and len(upload_date) == 8:
            d = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        pass
    return None


def viral_score(views: int, likes: int, comments: int, days: Optional[float]) -> int:
    """Score /100 : volume de vues (log), vitesse (vues par jour depuis la sortie) et engagement."""
    views = max(0, int(views or 0))
    if views <= 0:
        return 0
    vol = min(1.0, math.log10(views) / 7.0)                       # 10 M vues = plein
    per_day = views / max(1.0, days if days is not None else 30.0)
    speed = min(1.0, math.log10(max(1.0, per_day)) / 6.0)          # 1 M vues/jour = plein
    eng = (int(likes or 0) + int(comments or 0)) / views
    engs = min(1.0, eng / 0.12)                                    # 12 % d'engagement = plein
    return int(round(100 * (0.4 * vol + 0.35 * speed + 0.25 * engs)))


def _search_links(query: str, platform: str, lang: str) -> List[str]:
    """Liens récents TikTok (/video/) ou Reels (/reel/) trouvés par le moteur de recherche (semaine puis mois)."""
    import requests
    from urllib.parse import quote_plus, unquote

    host = "fr.search.yahoo.com" if lang == "fr" else "search.yahoo.com"
    q = f"site:tiktok.com {query}" if platform == "tiktok" else f"site:instagram.com/reel {query}"
    links: List[str] = []
    for btf in ("w", "m"):
        try:
            r = requests.get(
                f"https://{host}/search?p={quote_plus(q)}&btf={btf}",
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"},
                timeout=12,
            )
        except Exception:
            continue
        for m in re.finditer(r'RU=(https?%3a%2f%2f[^/&"]+)', r.text, flags=re.I):
            url = unquote(m.group(1)).split("?")[0]
            ok = ("/video/" in url) if platform == "tiktok" else ("instagram.com/reel/" in url)
            if ok and url not in links:
                links.append(url)
        if len(links) >= 6:
            break
    return links[:10]


def _probe(url: str) -> Optional[Dict[str, Any]]:
    """Chiffres réels d'une vidéo via yt-dlp (vues, likes, commentaires, date, durée, description)."""
    try:
        from core.security import validate_public_http_url
        safe_url = validate_public_http_url(url, resolve_dns=True)
        p = subprocess.run([YT_DLP_PATH, "--dump-json", "--skip-download", "--no-warnings", "--", safe_url],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
        if p.returncode != 0 or not p.stdout.strip():
            return None
        info = json.loads(p.stdout.splitlines()[0])
    except Exception:
        return None
    dur = int(info.get("duration") or 0)
    if dur and dur > MAX_DURATION:
        return None
    platform = "tiktok" if "tiktok.com" in url else "instagram"
    views = int(info.get("view_count") or 0)
    likes = int(info.get("like_count") or 0)
    comments = int(info.get("comment_count") or 0)
    days = _days_since(str(info.get("upload_date") or ""), info.get("timestamp"))
    tags = info.get("tags") or []
    desc = str(info.get("description") or "")
    thumb = str(info.get("thumbnail") or "")
    from urllib.parse import quote_plus
    return {
        "url": info.get("webpage_url") or url,
        "platform": platform,
        "title": (str(info.get("title") or desc or "Vidéo").strip().splitlines()[0])[:110],
        "description": desc[:400],
        "tags": [str(t) for t in tags][:15],
        "channel": str(info.get("uploader") or info.get("channel") or info.get("creator") or ""),
        "views": views, "likes": likes, "comments": comments,
        "engagement": round(100.0 * (likes + comments) / views, 1) if views else 0.0,
        "duration": dur,
        "upload_date": str(info.get("upload_date") or ""),
        "age_days": round(days, 1) if days is not None else None,
        "thumbnail": f"/api/thumb?url={quote_plus(thumb)}" if thumb.startswith("https://") else "",
        "score": viral_score(views, likes, comments, days),
    }


def _looks_ai(v: Dict[str, Any]) -> bool:
    blob = " ".join([v.get("title", ""), v.get("description", ""), " ".join(v.get("tags") or []), v.get("channel", "")])
    return bool(AI_HINTS.search(blob))


def _default_ai_query(prompt: str, system_prompt: str) -> str:
    """IA choisie toute seule : Claude si branché, sinon Gemini (hors édition publique). Vide si aucune ne répond."""
    from core import edition as _edition
    try:
        from core.claude_bridge import ClaudeBridge
        if (ClaudeBridge.check_status(live_probe=False) or {}).get("connected"):
            out = ClaudeBridge.query(prompt, system_prompt=system_prompt, action="analytics")
            if out and out.strip():
                return out
    except Exception:
        pass
    if _edition.is_public():
        return ""
    try:
        from core.gemini_studio import GeminiStudio
        return GeminiStudio.query(prompt, system_prompt=system_prompt, model=GeminiStudio.get_best_available_model()) or ""
    except Exception:
        return ""


def _parse_json(raw: str) -> Any:
    if not raw:
        return None
    m = re.search(r"\[[\s\S]*\]", raw)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


def _ai_review(videos: List[Dict[str, Any]], lang: str) -> None:
    """Pour chaque vidéo : est-ce bien du contenu IA ? quel style ? pourquoi ça marche ? (modifie la liste sur place)."""
    if not videos:
        return
    lines = "\n".join(
        f'{i}. [{v["platform"]}] « {v["title"]} » — {v["channel"]} — {v["views"]} vues, {v["engagement"]} % engagement, '
        f'{v.get("age_days")} jours — tags: {", ".join(v.get("tags") or [])[:120]} — desc: {v.get("description", "")[:160]}'
        for i, v in enumerate(videos)
    )
    sys_p = (
        "Tu analyses des vidéos courtes virales pour des créateurs de contenu IA. Réponds UNIQUEMENT par un tableau JSON, "
        "un objet par vidéo, dans l'ordre : "
        '[{"i": 0, "ai": true, "style": "3D Roblox | 2D dessin animé | 2D dans décor 3D | 3D style Pixar | réaliste IA | autre", '
        '"why": "pourquoi elle marche, 1 phrase concrète (accroche, twist, émotion, format)", "hook": "l\'accroche en 6 mots max"}]. '
        '"ai" = true seulement si la vidéo est clairement faite avec de l\'IA ou de l\'animation générée (pas un humain filmé, pas un jeu filmé brut).'
    )
    out = _parse_json(_default_ai_query(f"Langue des créateurs : {lang}\n\n{lines}", sys_p))
    if not isinstance(out, list):
        return
    for item in out:
        try:
            v = videos[int(item.get("i"))]
        except Exception:
            continue
        v["ai_checked"] = True
        v["is_ai"] = bool(item.get("ai"))
        v["style"] = str(item.get("style") or "")[:40]
        v["why"] = str(item.get("why") or "")[:220]
        v["hook"] = str(item.get("hook") or "")[:60]


def scan(lang: str = "fr", platforms: Optional[List[str]] = None, max_age_days: int = 30) -> Dict[str, Any]:
    lang = lang if lang in ("fr", "en", "all") else "fr"
    platforms = [p for p in (platforms or ["tiktok", "instagram"]) if p in ("tiktok", "instagram")] or ["tiktok", "instagram"]
    langs = ["fr", "en"] if lang == "all" else [lang]
    _STATE.update(progress="Recherche des vidéos IA récentes…", error="")
    links: List[str] = []
    jobs = [(q, p, lg) for lg in langs for q in AI_QUERIES[lg] for p in platforms]
    with ThreadPoolExecutor(max_workers=6) as ex:
        for found in ex.map(lambda a: _search_links(*a), jobs):
            for u in found:
                if u not in links:
                    links.append(u)
    links = links[:70]
    _STATE["progress"] = f"Lecture des chiffres de {len(links)} vidéos…"
    with ThreadPoolExecutor(max_workers=6) as ex:
        vids = [v for v in ex.map(_probe, links) if v]
    # récentes + qui ont vraiment marché + style IA
    fresh = [v for v in vids if v.get("age_days") is None or v["age_days"] <= max_age_days]
    strong = [v for v in fresh if v["views"] >= MIN_VIEWS or (v["platform"] == "instagram" and v["likes"] >= 3000)]
    candidates = [v for v in strong if _looks_ai(v)] or strong
    candidates.sort(key=lambda v: v["score"], reverse=True)
    candidates = candidates[:30]
    _STATE["progress"] = "L'IA regarde pourquoi elles marchent…"
    _ai_review(candidates, lang)
    final = [v for v in candidates if v.get("is_ai", True)]
    final.sort(key=lambda v: v["score"], reverse=True)
    report = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "lang": lang,
        "platforms": platforms,
        "max_age_days": max_age_days,
        "checked": len(vids),
        "videos": final[:24],
    }
    with _LOCK:
        RADAR_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def load() -> Dict[str, Any]:
    try:
        data = json.loads(RADAR_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["scanning"] = _STATE["scanning"]
    data["progress"] = _STATE["progress"]
    data["error"] = _STATE["error"]
    return data


def start_scan(lang: str = "fr", platforms: Optional[List[str]] = None, max_age_days: int = 30) -> bool:
    """Lance le scan en arrière-plan (1 à 3 min). False si un scan tourne déjà."""
    with _LOCK:
        if _STATE["scanning"]:
            return False
        _STATE["scanning"] = True

    def _run():
        try:
            scan(lang, platforms, max_age_days)
        except Exception as e:  # le radar ne doit jamais faire tomber l'app
            _STATE["error"] = str(e)[:200]
        finally:
            _STATE["scanning"] = False
            _STATE["progress"] = ""

    threading.Thread(target=_run, daemon=True).start()
    return True
