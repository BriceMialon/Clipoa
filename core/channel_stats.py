# -*- coding: utf-8 -*-
"""
Statistiques de la chaîne YouTube connectée : TOUTES les vidéos (publiées avec ou sans Clipoa),
avec vues, likes, commentaires, un score /100 et le « pourquoi » (ce qui a marché / ce qui a freiné).

Score /100 relatif à la chaîne (pour qu'une petite chaîne ait aussi des notes parlantes) :
65 % = vues comparées à la médiane de la chaîne, 35 % = engagement (likes + commentaires / vues).
L'IA (choisie toute seule : Claude, sinon Antigravity, sinon Gemini) explique chaque résultat.
"""
import json
import math
import re
import statistics
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from config import STORAGE_DIR

STATS_FILE = STORAGE_DIR / "channel_stats.json"
_LOCK = threading.Lock()
_STATE = {"syncing": False, "progress": "", "error": ""}
API = "https://www.googleapis.com/youtube/v3"
MAX_VIDEOS = 150


def _iso_duration(s: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def channel_score(views: int, likes: int, comments: int, median_views: float) -> int:
    views = max(0, int(views or 0))
    if views <= 0:
        return 0
    rel = views / max(1.0, median_views or 1.0)
    rel_score = max(0.0, min(100.0, 50.0 + 25.0 * math.log2(max(rel, 1e-3))))   # médiane = 50, ×4 = 100
    eng = (int(likes or 0) + int(comments or 0)) / views
    eng_score = min(100.0, eng / 0.08 * 100.0)                                 # 8 % d'engagement = 100
    return int(round(0.65 * rel_score + 0.35 * eng_score))


def _get(path: str, token: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.get(f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=20)
    if r.status_code == 401:
        raise PermissionError("expired")
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except Exception:
            msg = r.text[:160]
        raise RuntimeError(f"YouTube a refusé la lecture des statistiques ({r.status_code}) : {msg}")
    return r.json()


def _token() -> (str, Dict[str, Any]):
    from core.social_publisher import FreeSocialPublisher
    cfg = FreeSocialPublisher.get_account_config("youtube")
    if not cfg.get("access_token"):
        raise RuntimeError("Aucune chaîne YouTube connectée. Connecte-la dans Connexions.")
    return FreeSocialPublisher._ensure_youtube_token(cfg), cfg


def fetch_youtube_videos() -> Dict[str, Any]:
    from core.social_publisher import FreeSocialPublisher
    token, cfg = _token()

    def call(path, params):
        nonlocal token
        try:
            return _get(path, token, params)
        except PermissionError:
            token = FreeSocialPublisher._ensure_youtube_token(cfg, force=True)
            return _get(path, token, params)

    ch = call("channels", {"part": "snippet,contentDetails,statistics", "mine": "true"})
    items = ch.get("items") or []
    if not items:
        raise RuntimeError("Chaîne YouTube introuvable pour ce compte.")
    chan = items[0]
    uploads = chan["contentDetails"]["relatedPlaylists"]["uploads"]
    ids: List[str] = []
    page = None
    while len(ids) < MAX_VIDEOS:
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            params["pageToken"] = page
        pl = call("playlistItems", params)
        ids += [it["contentDetails"]["videoId"] for it in pl.get("items") or []]
        page = pl.get("nextPageToken")
        if not page:
            break
    videos: List[Dict[str, Any]] = []
    for k in range(0, len(ids), 50):
        vs = call("videos", {"part": "snippet,statistics,contentDetails,status", "id": ",".join(ids[k:k + 50])})
        for v in vs.get("items") or []:
            sn, st, cd = v.get("snippet") or {}, v.get("statistics") or {}, v.get("contentDetails") or {}
            if (v.get("status") or {}).get("privacyStatus") not in (None, "public", "unlisted"):
                continue
            dur = _iso_duration(cd.get("duration", ""))
            thumbs = sn.get("thumbnails") or {}
            thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
            pub = sn.get("publishedAt") or ""
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(pub.replace("Z", "+00:00"))).total_seconds() / 86400.0
            except Exception:
                age = None
            videos.append({
                "id": v["id"], "platform": "youtube",
                "url": f"https://www.youtube.com/shorts/{v['id']}" if dur and dur <= 180 else f"https://www.youtube.com/watch?v={v['id']}",
                "title": sn.get("title", "")[:120], "description": (sn.get("description") or "")[:300],
                "published_at": pub[:10], "age_days": round(age, 1) if age is not None else None,
                "duration": dur, "is_short": bool(dur and dur <= 180),
                "views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0),
                "comments": int(st.get("commentCount") or 0),
                "thumbnail": thumb,
            })
    return {
        "channel": {"id": chan["id"], "name": (chan.get("snippet") or {}).get("title", ""),
                    "subscribers": int((chan.get("statistics") or {}).get("subscriberCount") or 0),
                    "total_views": int((chan.get("statistics") or {}).get("viewCount") or 0)},
        "videos": videos,
    }


def render_for_video(video_id: str) -> str:
    """Identifiant de la fabrication Clipoa d'une vidéo YouTube publiée (vide si faite sans Clipoa)."""
    try:
        from core.social_publisher import FreeSocialPublisher
        for post in FreeSocialPublisher.load_queue():
            yt = (post.get("results") or {}).get("youtube") or {}
            if str(yt.get("video_id") or "") == video_id or video_id in str(yt.get("url") or ""):
                return str(post.get("render_id") or "")
    except Exception:
        pass
    return ""


def remake_request(video_id: str) -> Dict[str, Any]:
    """
    Ce qu'il faut envoyer à la Fabrique pour refaire la vidéo EN MIEUX :
    - faite avec Clipoa → même style, script d'origine réécrit en corrigeant les points faibles ;
    - faite sans Clipoa → on copie son style (lien de la vidéo) et on raconte la même idée en corrigeant les points faibles.
    """
    data = load()
    v = next((x for x in (data.get("videos") or []) if x.get("id") == video_id), None)
    if not v:
        raise ValueError("Vidéo introuvable : clique d'abord sur « Mettre à jour ».")
    fixes = " ".join(t for t in (v.get("why"), v.get("next")) if t) or "accroche plus forte, rythme plus serré, fin plus marquante"
    dur = max(30, min(90, int(v.get("duration") or 60)))
    brief = (f"Refais en MIEUX la vidéo « {v.get('title', '')} » ({v.get('views', 0)} vues, score {v.get('score', 0)}/100). "
             f"Ce qu'il faut corriger : {fixes} Garde l'idée et le ton, change ce qui n'a pas marché.")
    rid = render_for_video(video_id)
    meta: Dict[str, Any] = {}
    if rid:
        try:
            from config import RENDERS_DIR
            meta = json.loads((RENDERS_DIR / rid / "metadata.json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    if meta:
        spoken = str((meta.get("script") or {}).get("full_spoken_script") or "")[:1800]
        return {"route": "/api/make", "payload": {
            "topic": brief + (f" Script d'origine : {spoken}" if spoken else ""),
            "plugin_id": meta.get("plugin_id") or None, "target_duration_sec": dur,
            "enable_music": bool(meta.get("enable_music", True)), "enable_sfx": bool(meta.get("enable_sfx", True)),
        }}
    return {"route": "/api/make-like", "payload": {"url": v.get("url"), "topic": brief, "target_duration_sec": dur}}


def _published_with_clipoa() -> set:
    try:
        from core.social_publisher import FreeSocialPublisher
        out = set()
        for post in FreeSocialPublisher.load_queue():
            yt = (post.get("results") or {}).get("youtube") or {}
            if yt.get("video_id"):
                out.add(str(yt["video_id"]))
            m = re.search(r"(?:shorts/|v=)([A-Za-z0-9_-]{11})", str(yt.get("url") or ""))
            if m:
                out.add(m.group(1))
        return out
    except Exception:
        return set()


def _explain(videos: List[Dict[str, Any]], median_views: float, channel_name: str) -> None:
    """Pourquoi chaque vidéo a marché ou non (modifie la liste sur place). Une seule question à l'IA par lot."""
    from core.inspiration_radar import _default_ai_query, _parse_json
    if not videos:
        return
    for k in range(0, len(videos), 25):
        batch = videos[k:k + 25]
        lines = "\n".join(
            f'{i}. « {v["title"]} » — {v["views"]} vues ({round(v["views"] / max(1.0, median_views), 2)}× la médiane), '
            f'{v["engagement"]} % engagement, {v["duration"]} s, publiée il y a {v.get("age_days")} j — desc: {v["description"][:120]}'
            for i, v in enumerate(batch)
        )
        sys_p = (
            "Tu es un stratège YouTube Shorts / TikTok. Pour chaque vidéo de la chaîne, dis pourquoi elle a bien marché ou non, "
            "en comparant à la médiane de la chaîne. Réponds UNIQUEMENT par un tableau JSON dans l'ordre : "
            '[{"i": 0, "verdict": "a bien marché | moyenne | n\'a pas marché", "why": "la raison principale, 1 phrase concrète '
            '(accroche, titre, sujet, durée, miniature, rythme, timing)", "next": "1 action concrète pour la prochaine vidéo"}]'
        )
        out = _parse_json(_default_ai_query(f"Chaîne : {channel_name} — médiane {int(median_views)} vues\n\n{lines}", sys_p))
        if not isinstance(out, list):
            continue
        for item in out:
            try:
                v = batch[int(item.get("i"))]
            except Exception:
                continue
            v["verdict"] = str(item.get("verdict") or "")[:30]
            v["why"] = str(item.get("why") or "")[:240]
            v["next"] = str(item.get("next") or "")[:200]
            v["explained_at"] = time.time()
            v["explained_views"] = v["views"]


def load() -> Dict[str, Any]:
    try:
        data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.update(syncing=_STATE["syncing"], progress=_STATE["progress"], error=_STATE["error"])
    return data


def sync() -> Dict[str, Any]:
    _STATE.update(progress="Lecture de ta chaîne YouTube…", error="")
    fresh = fetch_youtube_videos()
    old = {v["id"]: v for v in (load().get("videos") or [])}
    vids = fresh["videos"]
    med = statistics.median([v["views"] for v in vids]) if vids else 0
    clipoa_ids = _published_with_clipoa()
    for v in vids:
        v["engagement"] = round(100.0 * (v["likes"] + v["comments"]) / v["views"], 1) if v["views"] else 0.0
        v["score"] = channel_score(v["views"], v["likes"], v["comments"], med)
        v["made_with_clipoa"] = v["id"] in clipoa_ids
        prev = old.get(v["id"]) or {}
        # on garde l'explication tant que les chiffres n'ont pas beaucoup bougé (économise l'IA)
        if prev.get("why") and prev.get("explained_views", 0) * 1.3 >= v["views"]:
            for key in ("verdict", "why", "next", "explained_at", "explained_views"):
                v[key] = prev.get(key)
    todo = [v for v in vids if not v.get("why")]
    if todo:
        _STATE["progress"] = f"L'IA explique {len(todo)} vidéo{'s' if len(todo) > 1 else ''}…"
        _explain(todo, med, fresh["channel"]["name"])
    vids.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    report = {"updated_at": time.strftime("%Y-%m-%d %H:%M"), "channel": fresh["channel"], "median_views": med, "videos": vids}
    with _LOCK:
        STATS_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def start_sync() -> bool:
    with _LOCK:
        if _STATE["syncing"]:
            return False
        _STATE["syncing"] = True

    def _run():
        try:
            sync()
        except Exception as e:
            _STATE["error"] = str(e)[:240]
        finally:
            _STATE["syncing"] = False
            _STATE["progress"] = ""

    threading.Thread(target=_run, daemon=True).start()
    return True
