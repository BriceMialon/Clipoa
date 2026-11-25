import subprocess
import json
import os
import re
import statistics
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import (
    YT_DLP_PATH,
    FFMPEG_PATH,
    DOWNLOADS_DIR,
    OUTLIER_THRESHOLD,
    YT_DLP_COOKIES_BROWSER,
    CLIPOA_MAX_DOWNLOAD_SIZE,
)
from core.security import validate_public_http_url, validate_cookie_browser


class CompetitorScraper:
    """
    Scrapes competitor accounts (YouTube Shorts and TikTok),
    identifies outlier viral videos using median baseline (>= 2x account median),
    and downloads target shorts with full metadata + audio + keyframes.
    """

    @staticmethod
    def detect_platform(url: str) -> str:
        u = url.lower()
        if "tiktok.com" in u:
            return "tiktok"
        if "youtube.com" in u or "youtu.be" in u:
            return "youtube"
        if "instagram.com" in u:
            return "instagram"
        return "other"

    @classmethod
    def normalize_channel_url(cls, channel_url: str) -> str:
        url = channel_url.strip()
        # Allow shorthand like "@MrBeast" -> YouTube Shorts
        if url.startswith("@"):
            return f"https://www.youtube.com/{url}/shorts"

        if "youtube.com" in url and not any(k in url for k in ["/shorts", "/videos", "/streams", "/watch", "/playlist"]):
            url = url.rstrip("/") + "/shorts"

        return url

    @staticmethod
    def _base_yt_dlp_cmd(cookies_from_browser: Optional[str] = None) -> List[str]:
        cmd = [YT_DLP_PATH, "--ignore-errors", "--no-warnings"]
        # yt-dlp doit trouver le ffmpeg de Clipoa pour assembler image + son (X, YouTube, TikTok en flux séparés)
        if FFMPEG_PATH and os.path.exists(str(FFMPEG_PATH)):
            cmd.extend(["--ffmpeg-location", str(FFMPEG_PATH)])
        browser = validate_cookie_browser(cookies_from_browser or YT_DLP_COOKIES_BROWSER)
        if browser:
            cmd.extend(["--cookies-from-browser", browser])
        return cmd

    @staticmethod
    def _parse_json_lines(stdout: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    items.append(data)
            except json.JSONDecodeError:
                continue
        return items

    @classmethod
    def get_channel_shorts(
        cls,
        channel_url: str,
        limit: int = 30,
        cookies_from_browser: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the latest shorts from a channel/profile URL without downloading video files.
        Automatically falls back to full metadata extraction if flat-playlist omits view counts (common on TikTok).
        """
        url = validate_public_http_url(cls.normalize_channel_url(channel_url), resolve_dns=True)
        cmd = cls._base_yt_dlp_cmd(cookies_from_browser) + [
            "--dump-json",
            "--flat-playlist",
            "--playlist-end", str(limit),
            "--",
            url,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        items = cls._parse_json_lines(result.stdout)

        if not items and result.returncode != 0:
            err = result.stderr.strip() or "Impossible de lire le compte (vérifie l'URL ou essaie --cookies chrome)"
            raise RuntimeError(f"Erreur yt-dlp: {err}")

        # Check if view_count is populated on at least 40% of items
        with_views = sum(1 for v in items if (v.get("view_count") or 0) > 0)
        if items and with_views < max(1, int(len(items) * 0.4)):
            # Enrich top items with full metadata (without --flat-playlist)
            enrich_limit = min(limit, 15)
            cmd_full = cls._base_yt_dlp_cmd(cookies_from_browser) + [
                "--dump-json",
                "--skip-download",
                "--playlist-end", str(enrich_limit),
                "--",
                url,
            ]
            res_full = subprocess.run(cmd_full, capture_output=True, text=True, timeout=120)
            enriched = cls._parse_json_lines(res_full.stdout)
            if enriched:
                return enriched

        return items

    @classmethod
    def find_outliers(
        cls,
        channel_url: str,
        limit: int = 30,
        threshold: float = OUTLIER_THRESHOLD,
        max_duration: int = 95,
        cookies_from_browser: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Finds outlier shorts performing >= `threshold` times the channel's median views.
        Uses median as primary baseline so a single viral video doesn't distort detection.
        """
        normalized_url = cls.normalize_channel_url(channel_url)
        platform = cls.detect_platform(normalized_url)
        videos = cls.get_channel_shorts(normalized_url, limit=limit, cookies_from_browser=cookies_from_browser)

        valid_videos: List[Dict[str, Any]] = []
        for v in videos:
            views = v.get("view_count")
            duration = v.get("duration")
            # Keep shorts/reels (<= max_duration) when duration is available
            if duration is not None and duration > max_duration:
                continue
            if views is not None and views > 0:
                valid_videos.append(v)

        if not valid_videos:
            # Return raw top items gracefully if platform hid view counts completely
            fallback_items = []
            for v in videos[:8]:
                vid_id = v.get("id", "")
                fallback_items.append({
                    "id": vid_id,
                    "title": v.get("title") or v.get("description", "Sans titre")[:80],
                    "url": v.get("webpage_url") or v.get("url") or (f"https://www.youtube.com/shorts/{vid_id}" if platform == "youtube" else ""),
                    "views": int(v.get("view_count") or 0),
                    "likes": int(v.get("like_count") or 0),
                    "comments": int(v.get("comment_count") or 0),
                    "duration": int(v.get("duration") or 0),
                    "engagement_rate": 0.0,
                    "median_views": 0,
                    "avg_views": 0,
                    "ratio": 1.0,
                    "upload_date": v.get("upload_date", ""),
                    "thumbnail": v.get("thumbnail") or (v.get("thumbnails", [{}])[-1].get("url") if v.get("thumbnails") else ""),
                })
            return {
                "channel_url": normalized_url,
                "platform": platform,
                "median_views": 0,
                "average_views": 0,
                "total_scanned": len(videos),
                "outliers": fallback_items,
                "note": "Compteur de vues masqué par la plateforme — affichage des vidéos récentes (essaie avec cookies navigateur)."
            }

        view_counts = [int(v["view_count"]) for v in valid_videos]
        median_views = statistics.median(view_counts)
        avg_views = sum(view_counts) / len(view_counts)
        baseline = max(1.0, float(median_views))

        outliers: List[Dict[str, Any]] = []
        for v in valid_videos:
            views = int(v["view_count"])
            ratio = views / baseline
            if ratio >= threshold:
                vid_id = v.get("id", "")
                likes = int(v.get("like_count") or 0)
                comments = int(v.get("comment_count") or 0)
                engagement = round(((likes + comments) / views) * 100, 2) if (likes or comments) and views > 0 else 0.0
                video_url = v.get("webpage_url") or v.get("url") or ""
                if video_url and not video_url.startswith("http") and platform == "youtube":
                    video_url = f"https://www.youtube.com/shorts/{vid_id}"
                elif not video_url and platform == "youtube" and vid_id:
                    video_url = f"https://www.youtube.com/shorts/{vid_id}"

                thumb = v.get("thumbnail") or ""
                if not thumb and v.get("thumbnails"):
                    thumb = v["thumbnails"][-1].get("url", "")

                outliers.append({
                    "id": vid_id,
                    "title": (v.get("title") or v.get("description") or "Sans titre").strip()[:100],
                    "url": video_url,
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "duration": int(v.get("duration") or 0),
                    "engagement_rate": engagement,
                    "median_views": int(median_views),
                    "avg_views": int(avg_views),
                    "ratio": round(ratio, 1),
                    "upload_date": v.get("upload_date", ""),
                    "thumbnail": thumb,
                })

        outliers.sort(key=lambda x: (x["ratio"], x["views"]), reverse=True)

        return {
            "channel_url": normalized_url,
            "platform": platform,
            "median_views": int(median_views),
            "average_views": int(avg_views),
            "total_scanned": len(valid_videos),
            "outliers": outliers,
        }

    @classmethod
    def download_video(
        cls,
        video_url: str,
        output_id: str,
        cookies_from_browser: Optional[str] = None,
        extract_frames: bool = True
    ) -> Dict[str, Any]:
        """
        Downloads a target video (short or long), captures its JSON metadata,
        extracts 16kHz mono WAV audio for Whisper, and optionally extracts keyframes.
        """
        video_url = validate_public_http_url(video_url, resolve_dns=True)
        target_dir = DOWNLOADS_DIR / output_id
        target_dir.mkdir(parents=True, exist_ok=True)
        video_path = target_dir / "original.mp4"
        audio_path = target_dir / "audio.wav"
        frames_dir = target_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # 1. Download video + metadata JSON (always prefer formats that contain an audio stream)
        cmd_dl = cls._base_yt_dlp_cmd(cookies_from_browser) + [
            "-f", "best[acodec!=none][vcodec!=none][ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
            "--max-filesize", str(CLIPOA_MAX_DOWNLOAD_SIZE),
            "--write-info-json",
            "--output", str(video_path),
            "--force-overwrites",
            "--",
            video_url,
        ]
        res_dl = subprocess.run(cmd_dl, capture_output=True, text=True, timeout=300)
        if res_dl.returncode != 0 or not video_path.exists():
            raise RuntimeError(f"Erreur téléchargement yt-dlp: {res_dl.stderr.strip()[-500:]}")

        # Parse saved metadata if present
        metadata: Dict[str, Any] = {"title": Path(video_url).name, "views": 0, "uploader": "", "duration": 0}
        info_files = list(target_dir.glob("*.info.json"))
        if info_files:
            try:
                with open(info_files[0], "r", encoding="utf-8") as f:
                    info = json.load(f)
                metadata = {
                    "id": info.get("id", ""),
                    "title": info.get("title") or info.get("fulltitle") or Path(video_url).name,
                    "views": int(info.get("view_count") or 0),
                    "likes": int(info.get("like_count") or 0),
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "duration": float(info.get("duration") or 0),
                    "description": (info.get("description") or "")[:500],
                    "webpage_url": info.get("webpage_url") or video_url,
                }
            except Exception:
                pass

        # 2. Extract audio to 16kHz mono WAV for Whisper (graceful silent fallback if video has no audio track)
        cmd_audio = [
            FFMPEG_PATH,
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_path),
        ]
        res_audio = subprocess.run(cmd_audio, capture_output=True, timeout=180)
        if res_audio.returncode != 0 or not audio_path.exists():
            print("⚠️ Aucune piste audio détectée dans cette vidéo — création d'un audio neutre pour poursuivre l'analyse.")
            subprocess.run(
                [FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1", "-acodec", "pcm_s16le", str(audio_path)],
                check=True,
                capture_output=True,
                timeout=60,
            )

        # 3. Extract 1 frame every second (up to 30 frames)
        if extract_frames:
            cmd_frames = [
                FFMPEG_PATH,
                "-y",
                "-i", str(video_path),
                "-vf", "fps=1",
                "-vframes", "30",
                str(frames_dir / "frame_%03d.jpg"),
            ]
            subprocess.run(cmd_frames, check=True, capture_output=True, timeout=180)

        return {
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "frames_dir": str(frames_dir),
            "metadata": metadata,
        }
