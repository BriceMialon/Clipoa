import html as htmllib
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote_plus, unquote
import requests

from config import STORAGE_DIR, YT_DLP_PATH
from core.claude_bridge import ClaudeBridge
from core.gemini_studio import GeminiStudio
from core.social_publisher import FreeSocialPublisher
from agents.team import _clean_json_response

INTERNAL_FILE = STORAGE_DIR / "analytics_internal.json"
EXTERNAL_FILE = STORAGE_DIR / "analytics_external.json"
_LOCK = threading.Lock()

PRESET_NICHES = [
    {"id": "finance", "label": "Finance & Argent", "query_fr": "finance argent investissement #shorts", "query_en": "personal finance money tips #shorts"},
    {"id": "ia_tech", "label": "IA & Tech", "query_fr": "intelligence artificielle outil ia #shorts", "query_en": "ai tools tech tips #shorts"},
    {"id": "storytelling", "label": "Storytelling & Frisson", "query_fr": "histoire vraie mystere frisson #shorts", "query_en": "scary true story mystery #shorts"},
    {"id": "business", "label": "Business & Side Hustle", "query_fr": "business en ligne entreprendre #shorts", "query_en": "side hustle online business #shorts"},
    {"id": "psychologie", "label": "Psychologie", "query_fr": "psychologie humaine astuce mentale #shorts", "query_en": "dark psychology facts #shorts"},
    {"id": "fitness", "label": "Fitness & Santé", "query_fr": "musculation sante routine #shorts", "query_en": "fitness workout tips #shorts"},
    {"id": "actu", "label": "Actu & Culture", "query_fr": "saviez vous fait insolite #shorts", "query_en": "did you know crazy facts #shorts"},
]


class AnalyticsEngine:
    """
    Moteur d'analyse interne (perf de tes vidéos postées + note /10 + plan d'action)
    et externe (tendances live par niche + pépites concurrentes).
    """

    @classmethod
    def load_internal_reports(cls) -> List[Dict[str, Any]]:
        with _LOCK:
            if not INTERNAL_FILE.exists():
                return []
            try:
                return json.loads(INTERNAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def _save_internal_reports(cls, items: List[Dict[str, Any]]):
        with _LOCK:
            INTERNAL_FILE.write_text(json.dumps(items[:40], indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def delete_internal_report(cls, report_id: str) -> bool:
        items = cls.load_internal_reports()
        new_items = [r for r in items if r.get("id") != report_id]
        if len(new_items) == len(items):
            return False
        cls._save_internal_reports(new_items)
        return True

    @classmethod
    def load_external_report(cls) -> Dict[str, Any]:
        with _LOCK:
            if not EXTERNAL_FILE.exists():
                return {}
            try:
                return json.loads(EXTERNAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}

    @classmethod
    def _save_external_report(cls, report: Dict[str, Any]):
        with _LOCK:
            EXTERNAL_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def _run_ai(cls, prompt: str, system_prompt: str, engine: str = "gemini") -> Dict[str, Any]:
        if engine == "claude":
            raw = ClaudeBridge.query(prompt, system_prompt=system_prompt, action="analytics")
        else:
            raw = GeminiStudio.query(prompt, system_prompt=system_prompt, model=GeminiStudio.get_best_available_model())
        return _clean_json_response(raw)

    @classmethod
    def fetch_video_metrics(cls, url: str) -> Dict[str, Any]:
        """Récupère les vraies stats publiques d'une vidéo YouTube/TikTok/IG via yt-dlp."""
        cmd = [
            YT_DLP_PATH,
            "--dump-json",
            "--skip-download",
            "--no-warnings",
            "--ignore-errors",
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
                views = int(info.get("view_count") or 0)
                likes = int(info.get("like_count") or 0)
                comments = int(info.get("comment_count") or 0)
                eng = round(((likes + comments) / views) * 100, 2) if views > 0 else 0.0
                low_url = url.lower()
                platform = (
                    "tiktok" if "tiktok.com" in low_url else
                    "instagram" if "instagram.com" in low_url else
                    "facebook" if "facebook.com" in low_url else
                    "youtube"
                )
                return {
                    "url": info.get("webpage_url") or url,
                    "platform": platform,
                    "title": (info.get("title") or info.get("fulltitle") or "Vidéo").strip()[:120],
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": eng,
                    "duration": int(info.get("duration") or 0),
                    "description": (info.get("description") or "")[:500],
                    "upload_date": info.get("upload_date") or "",
                }
            except Exception:
                continue
        raise RuntimeError("Impossible de récupérer les statistiques de cette vidéo (vérifie que le lien est public).")

    @classmethod
    def analyze_internal_video(
        cls,
        url: str,
        manual_views: Optional[int] = None,
        manual_likes: Optional[int] = None,
        manual_title: str = "",
        engine: str = "gemini",
        source: str = "manual",
    ) -> Dict[str, Any]:
        metrics = None
        if url.strip():
            metrics = cls.fetch_video_metrics(url.strip())
        else:
            views = int(manual_views or 0)
            likes = int(manual_likes or 0)
            metrics = {
                "url": "",
                "platform": "multi",
                "title": manual_title or "Mon clip",
                "uploader": "",
                "views": views,
                "likes": likes,
                "comments": 0,
                "engagement_rate": round((likes / views) * 100, 2) if views > 0 else 0.0,
                "duration": 0,
                "description": "",
            }

        sys_prompt = (
            "Tu es un stratège growth expert en YouTube Shorts, TikTok et Instagram Reels. "
            "Analyse objectivement les performances de la vidéo du créateur. "
            "Rends UNIQUEMENT un JSON strict avec ces clés :\n"
            '{"score": 7.8, "verdict": "Résumé en 1 phrase claire", '
            '"worked": ["Point fort 1", "Point fort 2"], '
            '"didnt_work": ["Point faible ou frein 1", "Point faible 2"], '
            '"improvements": ["Action concrète 1 pour la prochaine vidéo", "Action concrète 2", "Action concrète 3"]}'
        )
        user_prompt = (
            f"Plateforme : {metrics['platform']}\n"
            f"Titre : {metrics['title']}\n"
            f"Vues : {metrics['views']:,}\n"
            f"Likes : {metrics['likes']:,}\n"
            f"Commentaires : {metrics['comments']:,}\n"
            f"Taux d'engagement : {metrics['engagement_rate']}%\n"
            f"Durée : {metrics['duration']}s\n"
            f"Description : {metrics.get('description', '')}\n\n"
            "Note cette vidéo sur 10, explique pourquoi elle a bien ou mal marché, et donne 3 améliorations concrètes."
        )
        ai = cls._run_ai(user_prompt, sys_prompt, engine=engine)

        report = {
            "id": f"rep_{uuid.uuid4().hex[:8]}",
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "engine": engine,
            "source": source,
            "metrics": metrics,
            "score": ai.get("score", 7.0),
            "verdict": ai.get("verdict") or "Analyse terminée.",
            "worked": ai.get("worked") if isinstance(ai.get("worked"), list) else [],
            "didnt_work": ai.get("didnt_work") if isinstance(ai.get("didnt_work"), list) else [],
            "improvements": ai.get("improvements") if isinstance(ai.get("improvements"), list) else [],
        }

        items = cls.load_internal_reports()
        # Replace existing report for same URL if present
        if metrics.get("url"):
            items = [r for r in items if (r.get("metrics") or {}).get("url") != metrics["url"]]
        items.insert(0, report)
        cls._save_internal_reports(items)
        return report

    @classmethod
    def analyze_published_post(cls, post: Dict[str, Any], engine: str = "gemini") -> Optional[Dict[str, Any]]:
        """Analyse automatiquement un clip tout juste publié via Pulse (sans lien manuel)."""
        results = post.get("results") or {}
        for plat, rinfo in results.items():
            if not isinstance(rinfo, dict) or not rinfo.get("ok"):
                continue
            vid_url = rinfo.get("url") or ""
            if not vid_url and plat == "youtube" and rinfo.get("video_id"):
                vid_url = f"https://www.youtube.com/shorts/{rinfo['video_id']}"
            if vid_url:
                try:
                    return cls.analyze_internal_video(vid_url, engine=engine, source="clipoa_auto")
                except Exception:
                    pass
        # Fallback if platform didn't return a public URL yet (e.g. TikTok inbox)
        return cls.analyze_internal_video(
            url="",
            manual_views=0,
            manual_likes=0,
            manual_title=post.get("title") or "Clip publié via Pulse",
            engine=engine,
            source="clipoa_auto",
        )

    @classmethod
    def sync_published_posts(cls, engine: str = "gemini") -> Dict[str, Any]:
        """Détecte les vidéos déjà publiées via Pulse et analyse automatiquement celles qui ont une URL publique."""
        queue = FreeSocialPublisher.load_queue()
        existing_urls = {(r.get("metrics") or {}).get("url") for r in cls.load_internal_reports()}
        analyzed = []
        for post in queue:
            if post.get("status") not in ("published", "partial"):
                continue
            results = post.get("results") or {}
            for plat, rinfo in results.items():
                if not isinstance(rinfo, dict) or not rinfo.get("ok"):
                    continue
                vid_url = rinfo.get("url") or ""
                if not vid_url and plat == "youtube" and rinfo.get("video_id"):
                    vid_url = f"https://www.youtube.com/shorts/{rinfo['video_id']}"
                if vid_url and vid_url not in existing_urls:
                    try:
                        rep = cls.analyze_internal_video(vid_url, engine=engine)
                        analyzed.append(rep)
                        existing_urls.add(vid_url)
                    except Exception:
                        pass
        return {"analyzed_count": len(analyzed), "reports": cls.load_internal_reports()}

    @classmethod
    def _search_niche_videos(cls, query: str, limit: int = 30, max_duration: int = 95) -> List[Dict[str, Any]]:
        """Recherche strictement des Shorts récents et viraux (<= 95s) triés par vues."""
        cur_year = time.strftime("%Y")
        search_targets = [
            f"ytsearch{limit}:{query} {cur_year}",
            f"ytsearchdate{min(25, limit)}:{query}",
        ]
        out: List[Dict[str, Any]] = []
        seen = set()
        for target in search_targets:
            cmd = [
                YT_DLP_PATH,
                "--flat-playlist",
                "--dump-json",
                "--no-warnings",
                "--ignore-errors",
                target,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
            except Exception:
                continue
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    v = json.loads(line)
                    vid_id = v.get("id") or ""
                    if not vid_id or vid_id in seen:
                        continue
                    dur = int(v.get("duration") or 0)
                    if dur <= 0 or dur > max_duration:
                        continue
                    seen.add(vid_id)
                    views = int(v.get("view_count") or 0)
                    thumb = f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
                    out.append({
                        "id": vid_id,
                        "platform": "youtube",
                        "title": (v.get("title") or "Sans titre").strip()[:95],
                        "channel": v.get("channel") or v.get("uploader") or "",
                        "views": views,
                        "duration": dur,
                        "thumbnail": thumb,
                        "url": f"https://www.youtube.com/shorts/{vid_id}",
                    })
                except Exception:
                    continue
        out.sort(key=lambda x: x["views"], reverse=True)
        # Keep only genuinely viral / high-performing short clips (>= 10k views)
        viral = [x for x in out if x["views"] >= 10000 and x.get("thumbnail")]
        if len(viral) >= 3:
            return viral
        return [x for x in out if x["views"] >= 1000 and x.get("thumbnail")] or out[:4]

    @classmethod
    def _enrich_tiktok_video(cls, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Récupère les vraies vues, la durée (<= 95s) et la miniature HD d'une vidéo TikTok via yt-dlp."""
        try:
            p = subprocess.run(
                [YT_DLP_PATH, "--dump-json", "--skip-download", "--no-warnings", item["url"]],
                capture_output=True, text=True, timeout=14,
            )
            if p.returncode != 0 or not p.stdout.strip():
                return None
            info = json.loads(p.stdout.splitlines()[0])
            dur = int(info.get("duration") or 0)
            if dur > 95:
                return None
            views = int(info.get("view_count") or 0)
            raw_thumb = info.get("thumbnail") or ""
            thumb = f"/api/thumb?url={quote_plus(raw_thumb)}" if raw_thumb.startswith("https://") else ""
            item["views"] = views
            item["duration"] = dur
            item["thumbnail"] = thumb
            item["channel"] = info.get("uploader") or info.get("creator") or item.get("channel") or "TikTok"
            if info.get("title"):
                item["title"] = str(info["title"]).strip()[:90]
            return item
        except Exception:
            return None

    @staticmethod
    def _parse_compact_count(raw: str) -> int:
        s = (raw or "").strip().lower().replace("\u00a0", "").replace(" ", "").replace(",", ".")
        if not s:
            return 0
        mult = 1
        if s.endswith("k"):
            mult, s = 1000, s[:-1]
        elif s.endswith("m"):
            mult, s = 1_000_000, s[:-1]
        try:
            # Handle French/US thousand separator like "1.234" when no k/m suffix
            if mult == 1 and s.count(".") >= 1 and len(s.split(".")[-1]) == 3:
                return int(s.replace(".", ""))
            return int(float(s) * mult)
        except Exception:
            return 0

    @classmethod
    def _enrich_instagram_reel(cls, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Récupère la vraie miniature HD, le créateur et les likes d'un Reel Instagram via son embed public."""
        m_code = re.search(r"/reel/([A-Za-z0-9_-]+)", item.get("url") or "")
        if not m_code:
            return None
        code = m_code.group(1)
        try:
            r = requests.get(
                f"https://www.instagram.com/reel/{code}/embed/captioned/",
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                timeout=10,
            )
            if r.status_code != 200 or not r.text:
                return None
            page = r.text
            m_img = (
                re.search(r'<img[^>]+class="[^"]*EmbeddedMediaImage[^"]*"[^>]+src="([^"]+)"', page)
                or re.search(r'<img[^>]+src="([^"]+)"[^>]+class="[^"]*EmbeddedMediaImage[^"]*"', page)
            )
            if not m_img:
                return None
            raw_thumb = htmllib.unescape(m_img.group(1))
            if not raw_thumb.startswith("https://"):
                return None
            item["thumbnail"] = f"/api/thumb?url={quote_plus(raw_thumb)}"

            m_user = re.search(r'class="UsernameText"[^>]*>([^<]+)<', page)
            if m_user:
                uname = htmllib.unescape(m_user.group(1)).strip().lstrip("@")
                if uname:
                    item["channel"] = f"@{uname}"

            m_likes = re.search(r'([\d\s.,]+[kKmM]?)\s*(?:likes|J&#039;aime|J\'aime)', page, flags=re.I)
            if m_likes:
                item["likes"] = cls._parse_compact_count(m_likes.group(1))

            m_views = re.search(r'"video_view_count":(\d+)', page) or re.search(r'"video_play_count":(\d+)', page)
            if m_views:
                item["views"] = int(m_views.group(1))

            m_cap = re.search(r'<div class="Caption"[^>]*>([\s\S]*?)</div>', page)
            if m_cap:
                cap_txt = re.sub(r"<[^>]+>", " ", htmllib.unescape(m_cap.group(1)))
                cap_txt = re.sub(r"\s+", " ", cap_txt).strip()
                cap_txt = re.sub(r"View all [\d,.\s]+ comments.*$", "", cap_txt, flags=re.I).strip()
                if item.get("channel"):
                    u_raw = item["channel"].lstrip("@")
                    if cap_txt.lower().startswith(u_raw.lower()):
                        cap_txt = cap_txt[len(u_raw):].strip()
                if len(cap_txt) >= 8 and (len(item.get("title", "")) < 12 or "instagram" in item.get("title", "").lower()):
                    item["title"] = cap_txt[:90]

            return item
        except Exception:
            return None

    @classmethod
    def _search_social_clips(cls, topic_query: str, platform: str, lang: str = "fr", limit: int = 5) -> List[Dict[str, Any]]:
        """Découvre de vrais clips courts TikTok (/video/) et Instagram Reels (/reel/) avec miniatures nettes & vues."""
        from concurrent.futures import ThreadPoolExecutor
        words = [w for w in topic_query.replace("#shorts", "").split() if w][: (2 if platform == "instagram" else 3)]
        clean_q = " ".join(words)
        host = "fr.search.yahoo.com" if lang == "fr" else "search.yahoo.com"
        q = f"site:tiktok.com video {clean_q}" if platform == "tiktok" else f"site:instagram.com/reel {clean_q}"
        anchors = []
        # Prefer recent clips (past month `btf=m`), fall back to past year (`btf=y`) then unfiltered if needed
        for btf in ("m", "y", ""):
            try:
                btf_param = f"&btf={btf}" if btf else ""
                r = requests.get(
                    f"https://{host}/search?p={quote_plus(q)}{btf_param}",
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"},
                    timeout=12,
                )
                found = re.findall(r'<a[^>]+href="([^"]*RU=https?%3a%2f%2f[^"]+)"[^>]*>([\s\S]*?)</a>', r.text, flags=re.I)
                matched = [
                    a for a in found
                    if (platform == "tiktok" and "%2fvideo%2f" in a[0].lower())
                    or (platform == "instagram" and "instagram.com%2freel%2f" in a[0].lower())
                ]
                if len(matched) >= 2:
                    anchors = found
                    break
                if not anchors:
                    anchors = found
            except Exception:
                continue

        candidates: List[Dict[str, Any]] = []
        seen = set()
        for href, raw_title in anchors:
            m = re.search(r'RU=(https?%3a%2f%2f[^/&"]+)', href, flags=re.I)
            if not m:
                continue
            url = unquote(m.group(1))
            if url in seen:
                continue
            if platform == "tiktok" and "/video/" not in url.lower():
                continue
            if platform == "instagram" and "instagram.com/reel/" not in url.lower():
                continue
            title = re.sub(r'<[^>]+>', ' ', htmllib.unescape(raw_title))
            title = re.sub(r'\s+', ' ', title).strip()
            title = re.sub(r'\s*[\|\-]\s*(TikTok|Instagram).*$', '', title, flags=re.I).strip()
            if len(title) < 4:
                continue
            seen.add(url)
            cm = re.search(r'tiktok\.com/(@[^/?]+)', url)
            channel = cm.group(1) if cm else ("Instagram Reels" if platform == "instagram" else "TikTok")
            candidates.append({
                "id": f"{platform}_{uuid.uuid4().hex[:6]}",
                "platform": platform,
                "title": title[:90],
                "channel": channel,
                "views": 0,
                "duration": 0,
                "thumbnail": "",
                "url": url,
            })
            if len(candidates) >= limit:
                break

        if platform == "tiktok" and candidates:
            with ThreadPoolExecutor(max_workers=4) as ex:
                enriched = [x for x in ex.map(cls._enrich_tiktok_video, candidates) if x and x.get("thumbnail") and x.get("views", 0) >= 1000]
            enriched.sort(key=lambda x: x.get("views", 0), reverse=True)
            return enriched
        if platform == "instagram" and candidates:
            with ThreadPoolExecutor(max_workers=4) as ex:
                enriched = [x for x in ex.map(cls._enrich_instagram_reel, candidates) if x and x.get("thumbnail")]
            enriched.sort(key=lambda x: (x.get("views", 0), x.get("likes", 0)), reverse=True)
            return enriched
        return []

    @classmethod
    def analyze_external_niches(
        cls,
        niche_ids: List[str],
        custom_niche: str = "",
        lang: str = "fr",
        engine: str = "gemini",
    ) -> Dict[str, Any]:
        lang = (lang or "fr").strip().lower()
        if lang not in ("fr", "en", "intl"):
            lang = "fr"
        lang_labels = {"fr": "Français", "en": "Anglais", "intl": "International"}

        preset_map = {n["id"]: n for n in PRESET_NICHES}
        queries: List[Dict[str, str]] = []
        for nid in niche_ids:
            if nid in preset_map:
                p = preset_map[nid]
                if lang == "fr":
                    queries.append({"label": p["label"], "query": p["query_fr"]})
                elif lang == "en":
                    queries.append({"label": p["label"], "query": p["query_en"]})
                else:
                    queries.append({"label": p["label"], "query": p["query_fr"]})
                    queries.append({"label": p["label"], "query": p["query_en"]})
        if custom_niche.strip():
            cn = custom_niche.strip()
            queries.append({"label": cn, "query": f"{cn} #shorts"})
        if not queries:
            p = preset_map["finance"]
            queries.append({"label": p["label"], "query": p["query_fr"] if lang != "en" else p["query_en"]})

        yt_videos: List[Dict[str, Any]] = []
        tt_videos: List[Dict[str, Any]] = []
        ig_videos: List[Dict[str, Any]] = []
        seen_urls = set()

        for q in queries[:2]:
            for sq in (q["query"], q["query"].replace("#shorts", "shorts")):
                for v in cls._search_niche_videos(sq, limit=25, max_duration=95):
                    if v["url"] not in seen_urls:
                        seen_urls.add(v["url"])
                        v["niche"] = q["label"]
                        yt_videos.append(v)

        primary_q = queries[0]["query"]
        primary_label = queries[0]["label"]
        for v in cls._search_social_clips(primary_q, "tiktok", lang=lang, limit=8):
            if v["url"] not in seen_urls:
                seen_urls.add(v["url"])
                v["niche"] = primary_label
                tt_videos.append(v)

        for v in cls._search_social_clips(primary_q, "instagram", lang=lang, limit=8):
            if v["url"] not in seen_urls:
                seen_urls.add(v["url"])
                v["niche"] = primary_label
                ig_videos.append(v)

        yt_videos.sort(key=lambda x: x["views"], reverse=True)
        # Interleave YouTube Shorts, TikTok & Instagram Reels cleanly on the wall
        top_videos: List[Dict[str, Any]] = []
        buckets = [yt_videos[:8], tt_videos[:4], ig_videos[:4]]
        for idx in range(8):
            for b in buckets:
                if idx < len(b):
                    top_videos.append(b[idx])
        top_videos = top_videos[:15]

        niche_names = ", ".join(dict.fromkeys(q["label"] for q in queries))
        vid_lines = "\n".join(
            f"- [{v['platform'].upper()} · {v['niche']}] {v['title']}" + (f" ({v['views']:,} vues)" if v.get("views") else "")
            for v in top_videos
        ) or "(Aucune donnée vidéo récupérée)"

        sys_prompt = (
            "Tu es un analyste minimaliste de tendances courtes (YouTube Shorts, TikTok, Instagram Reels). "
            "Sois ULTRA CONCIS et percutant (style éditorial épuré, zéro blabla). "
            "Rends UNIQUEMENT un JSON strict :\n"
            '{"summary": "1 seule phrase courte et claire", '
            '"hot_sectors": ["Tag court 1 (2-4 mots)", "Tag court 2", "Tag court 3", "Tag court 4"], '
            '"winning_formats": ["Format court 1 (max 8 mots)", "Format 2", "Format 3"], '
            '"recommended_angles": ["Titre de clip court 1", "Titre de clip court 2", "Titre de clip court 3"]}'
        )
        user_prompt = (
            f"Langue : {lang_labels[lang]} | Niches : {niche_names}\n\n"
            f"Clips courts performants (YouTube Shorts, TikTok, Reels) :\n{vid_lines}"
        )
        ai = cls._run_ai(user_prompt, sys_prompt, engine=engine)

        report = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M"),
            "lang": lang,
            "lang_label": lang_labels[lang],
            "niches": list(dict.fromkeys(q["label"] for q in queries)),
            "engine": engine,
            "summary": ai.get("summary") or "Tendances analysées.",
            "hot_sectors": ai.get("hot_sectors") if isinstance(ai.get("hot_sectors"), list) else [],
            "winning_formats": ai.get("winning_formats") if isinstance(ai.get("winning_formats"), list) else [],
            "recommended_angles": ai.get("recommended_angles") if isinstance(ai.get("recommended_angles"), list) else [],
            "top_videos": top_videos,
        }
        cls._save_external_report(report)
        return report
