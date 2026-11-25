import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

from config import STORAGE_DIR

PROFILES_DIR = STORAGE_DIR / "social_profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(PROFILES_DIR, 0o700)
except OSError:
    pass

PORTALS: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "name": "YouTube Shorts",
        "login_url": "https://studio.youtube.com",
        "upload_url": "https://studio.youtube.com",
        "cookie_domains": ("youtube.com", "google.com"),
        "auth_cookies": ("SAPISID", "__Secure-3PAPISID"),
        "login_blocklist": ("accounts.google.com", "/signin", "ServiceLogin"),
    },
    "tiktok": {
        "name": "TikTok",
        "login_url": "https://www.tiktok.com/login",
        "upload_url": "https://www.tiktok.com/tiktokstudio/upload",
        "cookie_domains": ("tiktok.com",),
        "auth_cookies": ("sessionid", "sid_tt", "sessionid_ss"),
        "login_blocklist": ("/login",),
    },
    "instagram": {
        "name": "Instagram Reels",
        "login_url": "https://www.instagram.com/accounts/login/",
        "upload_url": "https://www.instagram.com/",
        "cookie_domains": ("instagram.com",),
        "auth_cookies": ("sessionid",),
        "login_blocklist": ("/accounts/login",),
    },
    "facebook": {
        "name": "Facebook Reels",
        "login_url": "https://www.facebook.com/login/",
        "upload_url": "https://business.facebook.com/latest/reels_composer",
        "cookie_domains": ("facebook.com",),
        "auth_cookies": ("c_user",),
        "login_blocklist": ("/login", "checkpoint"),
    },
}

_STATES_LOCK = threading.Lock()
_LOGIN_STATES: Dict[str, Dict[str, Any]] = {}


def _is_logged_in(platform: str, current_url: str, cookies: list) -> bool:
    cfg = PORTALS[platform]
    low_url = (current_url or "").lower()
    if any(b.lower() in low_url for b in cfg["login_blocklist"]):
        return False
    cookie_names = {
        c.get("name")
        for c in cookies
        if any(dom in (c.get("domain") or "").lower() for dom in cfg["cookie_domains"])
        and c.get("value")
    }
    if platform == "youtube":
        return "studio.youtube.com/channel/" in low_url or (
            "studio.youtube.com" in low_url and any(k in cookie_names for k in cfg["auth_cookies"])
        )
    return any(k in cookie_names for k in cfg["auth_cookies"])


class BrowserPortalAuth:
    """
    Connexion 1-clic directe aux portails officiels (YouTube, TikTok, Instagram, Facebook)
    via le navigateur Chrome local avec profil persistant isolé — zéro clé développeur requise.
    """

    @classmethod
    def get_state(cls, platform: str) -> Dict[str, Any]:
        with _STATES_LOCK:
            return dict(_LOGIN_STATES.get(platform, {"status": "idle", "message": ""}))

    @classmethod
    def start_login(cls, platform: str) -> Dict[str, Any]:
        if platform not in PORTALS:
            raise ValueError(f"Plateforme inconnue : {platform}")

        with _STATES_LOCK:
            cur = _LOGIN_STATES.get(platform, {})
            if cur.get("status") == "waiting":
                return dict(cur)
            _LOGIN_STATES[platform] = {
                "status": "waiting",
                "platform": platform,
                "message": f"Connecte-toi à {PORTALS[platform]['name']} dans la fenêtre Chrome qui vient de s'ouvrir...",
                "started_at": time.time(),
            }

        def _worker():
            from core.social_publisher import FreeSocialPublisher

            cfg = PORTALS[platform]
            profile_dir = PROFILES_DIR / platform
            profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                with _STATES_LOCK:
                    _LOGIN_STATES[platform] = {
                        "status": "error",
                        "message": "Playwright n'est pas encore installé dans le venv.",
                    }
                return

            ctx = None
            try:
                with sync_playwright() as p:
                    launch_kwargs: Dict[str, Any] = {
                        "user_data_dir": str(profile_dir),
                        "headless": False,
                        "viewport": {"width": 1120, "height": 760},
                        "args": ["--disable-blink-features=AutomationControlled"],
                    }
                    # Prefer real installed Google Chrome so Google/YouTube trusts the login
                    if os.path.exists("/Applications/Google Chrome.app"):
                        launch_kwargs["channel"] = "chrome"

                    ctx = p.chromium.launch_persistent_context(**launch_kwargs)
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=45000)

                    deadline = time.time() + 240  # 4 minutes to complete login + 2FA
                    connected = False
                    while time.time() < deadline:
                        if not ctx.pages:
                            break
                        try:
                            url = page.url
                            cookies = ctx.cookies()
                            if _is_logged_in(platform, url, cookies):
                                connected = True
                                break
                        except Exception:
                            break
                        time.sleep(1.2)

                    label = f"{cfg['name']} (Session Chrome)"
                    if connected:
                        try:
                            title = (page.title() or "").strip()
                            if title and len(title) < 60 and "login" not in title.lower():
                                label = title.split(" - ")[0].split(" | ")[0][:40]
                        except Exception:
                            pass

                    try:
                        ctx.close()
                    except Exception:
                        pass

                    if connected:
                        field_map = {
                            "youtube": {"channel_name": label},
                            "tiktok": {"username": label},
                            "instagram": {"username": label},
                            "facebook": {"page_name": label},
                        }
                        FreeSocialPublisher.save_account(
                            platform,
                            {
                                "access_token": f"browser_session:{platform}",
                                **field_map.get(platform, {}),
                            },
                        )
                        with _STATES_LOCK:
                            _LOGIN_STATES[platform] = {
                                "status": "connected",
                                "platform": platform,
                                "label": label,
                                "message": f"{cfg['name']} connecté ! Retour sur Clipoa.",
                            }
                    else:
                        with _STATES_LOCK:
                            _LOGIN_STATES[platform] = {
                                "status": "cancelled",
                                "platform": platform,
                                "message": "Fenêtre fermée avant la fin de la connexion.",
                            }
            except Exception as e:
                with _STATES_LOCK:
                    _LOGIN_STATES[platform] = {
                        "status": "error",
                        "platform": platform,
                        "message": f"Erreur connexion navigateur : {str(e)[:160]}",
                    }

        threading.Thread(target=_worker, daemon=True).start()
        return cls.get_state(platform)

    @classmethod
    def publish_with_session(cls, platform: str, video_path: str, title: str, caption: str) -> Dict[str, Any]:
        """
        Ouvre le studio d'upload officiel déjà connecté (session persistante) et pré-charge le MP4
        pour publier sur YouTube Studio, TikTok Studio, Instagram ou Facebook Reels.
        """
        if platform not in PORTALS:
            return {"ok": False, "message": f"Plateforme inconnue : {platform}"}
        profile_dir = PROFILES_DIR / platform
        if not profile_dir.exists():
            return {"ok": False, "message": f"Reconnecte {PORTALS[platform]['name']} en 1 clic."}

        def _open_studio():
            try:
                from playwright.sync_api import sync_playwright
                cfg = PORTALS[platform]
                with sync_playwright() as p:
                    launch_kwargs: Dict[str, Any] = {
                        "user_data_dir": str(profile_dir),
                        "headless": False,
                        "viewport": {"width": 1200, "height": 820},
                        "args": ["--disable-blink-features=AutomationControlled"],
                    }
                    if os.path.exists("/Applications/Google Chrome.app"):
                        launch_kwargs["channel"] = "chrome"
                    ctx = p.chromium.launch_persistent_context(**launch_kwargs)
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto(cfg["upload_url"], wait_until="domcontentloaded", timeout=45000)
                    # Try attaching the MP4 automatically if a file input is immediately available
                    try:
                        page.wait_for_timeout(2500)
                        inp = page.locator('input[type="file"]').first
                        if inp.count() > 0:
                            inp.set_input_files(video_path)
                    except Exception:
                        pass
                    # Keep window open until user closes it after confirming publish
                    while ctx.pages:
                        time.sleep(1.5)
            except Exception as e:
                print(f"⚠️ Studio {platform} : {e}")

        threading.Thread(target=_open_studio, daemon=True).start()
        return {
            "ok": True,
            "message": f"Studio {PORTALS[platform]['name']} ouvert avec ta session connectée et ton MP4 prêt !",
        }
