# -*- coding: utf-8 -*-
"""
Statistiques du compte actif (YouTube ou TikTok) : TOUTES les vidéos (publiées avec ou sans ClipRoll),
avec vues, likes, commentaires, un score /100 et le « pourquoi » (ce qui a marché / ce qui a freiné).

- Cache isolé par espace de travail actif (workspace.current()) : changer de compte en haut à droite
  n'affiche plus jamais les statistiques YouTube quand un compte TikTok / Instagram / Facebook est actif.
- Score /100 relatif à la chaîne (pour qu'une petite chaîne ait aussi des notes parlantes) :
  65 % = vues comparées à la médiane de la chaîne, 35 % = engagement (likes + commentaires / vues).
- L'IA (choisie toute seule : Claude, sinon Gemini) explique chaque résultat.
"""
import json
import math
import re
import shutil
import statistics
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config import BASE_DIR, STORAGE_DIR

STATS_FILE = STORAGE_DIR / "channel_stats.json"
_LOCK = threading.Lock()
_STATES: Dict[str, Dict[str, Any]] = {}
API = "https://www.googleapis.com/youtube/v3"
TIKTOK_API = "https://open.tiktokapis.com/v2"
MAX_VIDEOS = 150


def _active_workspace() -> Optional[Dict[str, Any]]:
    try:
        from core import workspace as _ws
        return _ws.current()
    except Exception:
        return None


def _ws_id(ws: Optional[Dict[str, Any]] = None) -> str:
    ws = ws if ws is not None else _active_workspace()
    return str((ws or {}).get("id") or "youtube:default")


def _state_for(ws_id: str) -> Dict[str, Any]:
    with _LOCK:
        st = _STATES.get(ws_id)
        if st is None:
            st = {"syncing": False, "progress": "", "error": ""}
            _STATES[ws_id] = st
        return st


def _stats_file(ws: Optional[Dict[str, Any]] = None) -> Path:
    ws = ws if ws is not None else _active_workspace()
    wid = _ws_id(ws)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", wid).strip("_") or "default"
    scoped = STORAGE_DIR / f"channel_stats_{safe}.json"
    # Rétrocompatibilité uniquement pour le compte YouTube si l'ancien fichier global existe déjà
    if not scoped.exists() and (ws or {}).get("platform", "youtube") == "youtube" and STATS_FILE.exists():
        return STATS_FILE
    return scoped


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


def _token(ws_key: Optional[str] = None) -> (str, Dict[str, Any]):
    from core.social_publisher import FreeSocialPublisher
    cfg = FreeSocialPublisher.get_account_config("youtube", ws_key)
    if not cfg.get("access_token"):
        raise RuntimeError("Aucune chaîne YouTube connectée. Connecte-la dans Connexions.")
    return FreeSocialPublisher._ensure_youtube_token(cfg), cfg


def fetch_youtube_videos(ws_key: Optional[str] = None) -> Dict[str, Any]:
    from core.social_publisher import FreeSocialPublisher
    token, cfg = _token(ws_key)

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
        "channel": {"id": chan["id"], "platform": "youtube",
                    "name": (chan.get("snippet") or {}).get("title", ""),
                    "subscribers": int((chan.get("statistics") or {}).get("subscriberCount") or 0),
                    "total_views": int((chan.get("statistics") or {}).get("viewCount") or 0)},
        "videos": videos,
    }


def _find_ytdlp() -> Optional[str]:
    for cand in (BASE_DIR / "venv" / "bin" / "yt-dlp", BASE_DIR / "venv" / "Scripts" / "yt-dlp.exe"):
        if cand.exists():
            return str(cand)
    return shutil.which("yt-dlp")


def _saved_tiktok_handle(ws_id: str) -> str:
    try:
        from core.settings_store import load_settings
        handles = load_settings().get("tiktok_handles") or {}
        return str(handles.get(ws_id) or "").strip().lstrip("@")
    except Exception:
        return ""


def set_tiktok_handle(handle: str, ws: Optional[Dict[str, Any]] = None) -> str:
    """Enregistre le @handle TikTok public pour le compte actif (fallback yt-dlp)."""
    from core.settings_store import load_settings, save_settings
    clean = re.sub(r"[^A-Za-z0-9._]", "", str(handle or "").strip().lstrip("@"))
    if not clean or len(clean) < 2:
        raise ValueError("Entre un @handle TikTok valide (ex: docteurshark).")
    wid = _ws_id(ws)
    handles = dict(load_settings().get("tiktok_handles") or {})
    handles[wid] = clean
    save_settings({"tiktok_handles": handles})
    return clean


def _tiktok_handle(cfg: Dict[str, Any], fallback_name: str = "", ws_id: str = "") -> str:
    saved = _saved_tiktok_handle(ws_id) if ws_id else ""
    for raw in (saved, cfg.get("username"), cfg.get("handle"), cfg.get("account_name"), cfg.get("display_name"), fallback_name):
        s = str(raw or "").strip().lstrip("@")
        if s and re.fullmatch(r"[A-Za-z0-9._]{2,40}", s):
            return s
    return ""


def fetch_tiktok_videos(ws_key: Optional[str] = None, fallback_name: str = "", ws_id: str = "") -> Dict[str, Any]:
    """
    Lit les vidéos & stats du compte TikTok actif :
    1) API officielle TikTok v2 (video/list + user/info) si le token dispose du scope `video.list`.
    2) Fallback automatique via yt-dlp sur le profil public `https://www.tiktok.com/@<username>`.
    """
    from core.social_publisher import FreeSocialPublisher
    cfg = FreeSocialPublisher.get_account_config("tiktok", ws_key)
    tok = str(cfg.get("access_token") or "")
    channel_name = str(cfg.get("display_name") or cfg.get("username") or fallback_name or "TikTok")
    followers = 0
    videos: List[Dict[str, Any]] = []

    # 1. Tentative API officielle TikTok v2
    if tok and not tok.startswith(("same_browser:", "browser_session:")):
        try:
            tok = FreeSocialPublisher._ensure_tiktok_token(cfg)
            u_res = requests.get(
                f"{TIKTOK_API}/user/info/",
                params={"fields": "open_id,display_name,username,follower_count,likes_count,video_count"},
                headers={"Authorization": f"Bearer {tok}"},
                timeout=12,
            )
            if u_res.status_code != 200:
                u_res = requests.get(
                    f"{TIKTOK_API}/user/info/",
                    params={"fields": "open_id,display_name"},
                    headers={"Authorization": f"Bearer {tok}"},
                    timeout=12,
                )
            if u_res.status_code == 200:
                u = ((u_res.json().get("data") or {}).get("user") or {})
                channel_name = u.get("display_name") or u.get("username") or channel_name
                if u.get("username") and not cfg.get("username"):
                    cfg = {**cfg, "username": u["username"]}
                followers = int(u.get("follower_count") or 0)
            v_res = requests.post(
                f"{TIKTOK_API}/video/list/",
                params={"fields": "id,title,video_description,duration,cover_image_url,share_url,create_time,like_count,comment_count,view_count"},
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                json={"max_count": 20},
                timeout=15,
            )
            if v_res.status_code == 200:
                v_items = ((v_res.json().get("data") or {}).get("videos") or [])
                for v in v_items:
                    ct = int(v.get("create_time") or 0)
                    pub = datetime.fromtimestamp(ct, tz=timezone.utc).strftime("%Y-%m-%d") if ct else ""
                    age = round((time.time() - ct) / 86400.0, 1) if ct else None
                    vid_id = str(v.get("id") or "")
                    title = (v.get("title") or v.get("video_description") or "Vidéo TikTok").strip()[:120]
                    videos.append({
                        "id": vid_id, "platform": "tiktok",
                        "url": v.get("share_url") or "",
                        "title": title, "description": (v.get("video_description") or "")[:300],
                        "published_at": pub, "age_days": age,
                        "duration": int(v.get("duration") or 0), "is_short": True,
                        "views": int(v.get("view_count") or 0),
                        "likes": int(v.get("like_count") or 0),
                        "comments": int(v.get("comment_count") or 0),
                        "thumbnail": v.get("cover_image_url") or "",
                    })
        except Exception:
            pass

    # 2. Fallback profil public via yt-dlp si l'API TikTok n'a pas le scope video.list.
    #    Coupé en version publique : lecture automatisée d'un profil, contraire aux CGU TikTok.
    from core import edition as _edition
    if not videos and not _edition.is_public():
        handle = _tiktok_handle(cfg, fallback_name, ws_id=ws_id)
        ytdlp = _find_ytdlp()
        if handle and ytdlp:
            try:
                proc = subprocess.run(
                    [ytdlp, "--flat-playlist", "-J", "--playlist-end", "40", f"https://www.tiktok.com/@{handle}"],
                    capture_output=True, text=True, timeout=45,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout)
                    for e in (data.get("entries") or []):
                        if not isinstance(e, dict):
                            continue
                        ts = int(e.get("timestamp") or 0)
                        pub = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts else ""
                        if not pub and e.get("upload_date") and len(str(e["upload_date"])) == 8:
                            ud = str(e["upload_date"])
                            pub = f"{ud[:4]}-{ud[4:6]}-{ud[6:8]}"
                        age = round((time.time() - ts) / 86400.0, 1) if ts else None
                        vid_id = str(e.get("id") or "")
                        url = e.get("webpage_url") or e.get("url") or (f"https://www.tiktok.com/@{handle}/video/{vid_id}" if vid_id else "")
                        thumbs = e.get("thumbnails") or []
                        thumb = e.get("thumbnail") or (thumbs[-1].get("url") if thumbs and isinstance(thumbs[-1], dict) else "")
                        videos.append({
                            "id": vid_id, "platform": "tiktok", "url": url,
                            "title": (e.get("title") or e.get("description") or "Vidéo TikTok").strip()[:120],
                            "description": (e.get("description") or "")[:300],
                            "published_at": pub, "age_days": age,
                            "duration": int(e.get("duration") or 0), "is_short": True,
                            "views": int(e.get("view_count") or 0),
                            "likes": int(e.get("like_count") or 0),
                            "comments": int(e.get("comment_count") or 0),
                            "thumbnail": thumb or "",
                        })
            except Exception:
                pass

    if not videos:
        raise RuntimeError(
            f"Impossible de lire les vidéos TikTok de « {channel_name} » : le scope OAuth `video.list` n'est pas activé"
            + (" (reconnecte TikTok dans Connexions)." if _edition.is_public()
               else " et le profil public n'a pas pu être lu (compte privé ou @handle manquant).")
        )

    total_views = sum(v["views"] for v in videos)
    return {
        "channel": {"id": str(cfg.get("open_id") or ws_key or channel_name), "platform": "tiktok",
                    "name": channel_name, "subscribers": followers, "total_views": total_views},
        "videos": videos,
    }


def render_for_video(video_id: str, platform: str = "youtube") -> str:
    """Identifiant de la fabrication ClipRoll d'une vidéo publiée (vide si faite sans ClipRoll)."""
    try:
        from core.social_publisher import FreeSocialPublisher
        for post in FreeSocialPublisher.load_queue():
            res = (post.get("results") or {}).get(platform) or {}
            if str(res.get("video_id") or "") == video_id or (video_id and video_id in str(res.get("url") or "")):
                return str(post.get("render_id") or "")
    except Exception:
        pass
    return ""


def remake_request(video_id: str) -> Dict[str, Any]:
    """
    Ce qu'il faut envoyer à la Fabrique pour refaire la vidéo EN MIEUX :
    - faite avec ClipRoll → même style, script d'origine réécrit en corrigeant les points faibles ;
    - faite sans ClipRoll → on copie son style (lien de la vidéo) et on raconte la même idée en corrigeant les points faibles.
    """
    data = load()
    v = next((x for x in (data.get("videos") or []) if x.get("id") == video_id), None)
    if not v:
        raise ValueError("Vidéo introuvable : clique d'abord sur « Mettre à jour ».")
    fixes = " ".join(t for t in (v.get("why"), v.get("next")) if t) or "accroche plus forte, rythme plus serré, fin plus marquante"
    dur = max(30, min(90, int(v.get("duration") or 60)))
    brief = (
        f"Refais en MIEUX la vidéo « {v.get('title', '')} » ({v.get('views', 0)} vues, score {v.get('score', 0)}/100). "
        f"Ce qu'il faut corriger : {fixes} "
        "Applique strictement : hook visuel + parlé en moins de 1,5s (Evidence + Betrayal, <7 mots), "
        "phrases courtes (<8 mots), payoff avant 65% de la durée, relance visuelle/SFX toutes les 6s, "
        "et fin avec question binaire polarisante + boucle grammaticale sans pause vers le début."
    )
    rid = render_for_video(video_id, platform=str(v.get("platform") or "youtube"))
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
    from core import edition as _edition
    if _edition.is_public():
        return {"route": "/api/make", "payload": {"topic": brief, "target_duration_sec": dur}}
    return {"route": "/api/make-like", "payload": {"url": v.get("url"), "topic": brief, "target_duration_sec": dur}}


def _published_with_clipoa(platform: str = "youtube") -> set:
    try:
        from core.social_publisher import FreeSocialPublisher
        out = set()
        for post in FreeSocialPublisher.load_queue():
            res = (post.get("results") or {}).get(platform) or {}
            if res.get("video_id"):
                out.add(str(res["video_id"]))
            url = str(res.get("url") or "")
            if platform == "youtube":
                m = re.search(r"(?:shorts/|v=)([A-Za-z0-9_-]{11})", url)
                if m:
                    out.add(m.group(1))
            elif platform == "tiktok":
                m = re.search(r"/video/(\d+)", url)
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
    ws = _active_workspace()
    wid = _ws_id(ws)
    st = _state_for(wid)
    f = _stats_file(ws)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if ws:
        data.setdefault("workspace", {"id": ws.get("id"), "platform": ws.get("platform"), "name": ws.get("name")})
        if ws.get("platform") == "tiktok":
            data["tiktok_handle"] = _saved_tiktok_handle(wid)
    data.update(syncing=st["syncing"], progress=st["progress"], error=st["error"])
    return data


def sync(ws: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ws = ws if ws is not None else _active_workspace()
    wid = _ws_id(ws)
    st = _state_for(wid)
    plat = (ws or {}).get("platform") or "youtube"
    ws_key = (ws or {}).get("key")
    ws_name = (ws or {}).get("name") or plat.title()

    if plat == "youtube":
        st.update(progress=f"Lecture de ta chaîne YouTube ({ws_name})…", error="")
        fresh = fetch_youtube_videos(ws_key)
    elif plat == "tiktok":
        st.update(progress=f"Lecture de ton compte TikTok ({ws_name})…", error="")
        fresh = fetch_tiktok_videos(ws_key, fallback_name=ws_name, ws_id=wid)
    else:
        raise RuntimeError(
            f"Les statistiques automatiques du compte sont disponibles pour YouTube et TikTok (pas encore pour {plat.title()}). "
            "Tu peux toutefois coller le lien d'une vidéo ci-dessous pour l'auditer."
        )

    old_file = _stats_file(ws)
    try:
        old_data = json.loads(old_file.read_text(encoding="utf-8"))
    except Exception:
        old_data = {}
    old = {v["id"]: v for v in (old_data.get("videos") or [])}
    vids = fresh["videos"]
    med = statistics.median([v["views"] for v in vids]) if vids else 0
    clipoa_ids = _published_with_clipoa(platform=plat)
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
        st["progress"] = f"L'IA explique {len(todo)} vidéo{'s' if len(todo) > 1 else ''}…"
        _explain(todo, med, fresh["channel"]["name"])
    vids.sort(key=lambda v: v.get("published_at") or "", reverse=True)
    report = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        "workspace": {"id": wid, "platform": plat, "name": ws_name},
        "channel": fresh["channel"],
        "median_views": med,
        "videos": vids,
    }
    target_file = STORAGE_DIR / f"channel_stats_{re.sub(r'[^A-Za-z0-9._-]+', '_', wid).strip('_') or 'default'}.json"
    with _LOCK:
        target_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def start_sync() -> bool:
    ws = _active_workspace()
    wid = _ws_id(ws)
    st = _state_for(wid)
    with _LOCK:
        if st["syncing"]:
            return False
        st["syncing"] = True
        st["error"] = ""

    def _run():
        try:
            sync(ws)
        except Exception as e:
            st["error"] = str(e)[:240]
        finally:
            st["syncing"] = False
            st["progress"] = ""

    threading.Thread(target=_run, daemon=True).start()
    return True
