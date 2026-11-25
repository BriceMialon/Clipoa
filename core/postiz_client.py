import requests
import os
import logging
from typing import Dict, Any, List, Optional
from config import POSTIZ_API_URL, POSTIZ_API_KEY

logger = logging.getLogger("PostizClient")

class PostizClient:
    """
    Automated multi-platform scheduler via Postiz (TikTok, YouTube Shorts, Instagram Reels).
    """

    @classmethod
    def is_configured(cls) -> bool:
        return bool(POSTIZ_API_KEY)

    @classmethod
    def schedule_post(
        cls,
        video_path: str,
        caption: str,
        scheduled_time_iso: str,
        platforms: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        platforms = platforms or ["tiktok", "youtube", "instagram"]
        
        if not cls.is_configured():
            logger.info("Postiz non configuré. Le short est prêt pour publication manuelle.")
            return {
                "status": "ready_for_manual_post",
                "video_path": video_path,
                "caption": caption,
                "platforms": platforms,
                "recommended_time": scheduled_time_iso,
                "note": "Ajoute POSTIZ_API_KEY dans config.py pour activer l'envoi 100% automatique."
            }

        headers = {
            "Authorization": f"Bearer {POSTIZ_API_KEY}"
        }
        data = {
            "content": caption,
            "scheduledFor": scheduled_time_iso,
            "platforms": platforms
        }

        with open(video_path, "rb") as f:
            files = {"file": f}
            res = requests.post(f"{POSTIZ_API_URL}/posts", headers=headers, data=data, files=files, timeout=60)
            if res.status_code in (200, 201):
                return {"status": "scheduled", "data": res.json()}
            else:
                logger.error(f"Postiz scheduling failed: {res.status_code} {res.text}")
                return {"status": "error", "message": res.text}
