# -*- coding: utf-8 -*-
"""
Espace de travail = le compte choisi en haut à droite (chaîne YouTube, compte Instagram, TikTok ou Page Facebook).
- Changer d'espace rend ce compte actif pour la publication et n'affiche que les vidéos fabriquées pour lui.
- Chaque nouvelle vidéo est rattachée à l'espace actif au moment de sa fabrication (metadata.json → "account").
- Les vidéos d'avant cette fonction sont rattachées au premier espace choisi (« legacy »).
"""
import json
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from config import STORAGE_DIR
from core.settings_store import load_settings, save_settings

AVATARS_FILE = STORAGE_DIR / "account_avatars.json"
_LOCK = threading.Lock()
ORDER = ("youtube", "instagram", "tiktok", "facebook")
PLATFORM_LABEL = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok", "facebook": "Facebook"}


def _avatars() -> Dict[str, str]:
    try:
        return json.loads(AVATARS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_avatar(k: str, url: str) -> None:
    with _LOCK:
        d = _avatars()
        d[k] = url
        AVATARS_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _fetch_avatar(platform: str, key: str) -> str:
    """Photo / logo du compte via l'API de la plateforme (meilleur effort, mis en cache)."""
    from core.social_publisher import FreeSocialPublisher as P
    cfg = P.get_account_config(platform, key)
    tok = str(cfg.get("access_token") or "")
    if not tok or tok.startswith(("same_browser:", "browser_session:")):
        return ""
    try:
        if platform == "youtube":
            tok = P._ensure_youtube_token(cfg)
            r = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                             headers={"Authorization": f"Bearer {tok}"}, timeout=10)
            th = ((((r.json().get("items") or [{}])[0]).get("snippet") or {}).get("thumbnails") or {})
            return (th.get("default") or th.get("medium") or {}).get("url", "")
        if platform == "tiktok":
            r = requests.get("https://open.tiktokapis.com/v2/user/info/", params={"fields": "avatar_url,display_name"},
                             headers={"Authorization": f"Bearer {tok}"}, timeout=10)
            return (((r.json().get("data") or {}).get("user") or {}).get("avatar_url")) or ""
        if platform == "instagram" and cfg.get("ig_user_id"):
            r = requests.get(f"https://graph.facebook.com/v21.0/{cfg['ig_user_id']}", params={"fields": "profile_picture_url", "access_token": tok}, timeout=10)
            return r.json().get("profile_picture_url") or ""
        if platform == "facebook" and cfg.get("page_id"):
            r = requests.get(f"https://graph.facebook.com/v21.0/{cfg['page_id']}/picture", params={"redirect": "false", "access_token": tok}, timeout=10)
            return ((r.json().get("data") or {}).get("url")) or ""
    except Exception:
        return ""
    return ""


def list_accounts(fetch_avatars: bool = True) -> List[Dict[str, Any]]:
    from core.social_publisher import FreeSocialPublisher as P, SAVED_KEY, _account_key, _account_label
    raw = P.load_accounts()
    av = _avatars()
    out: List[Dict[str, Any]] = []
    for plat in ORDER:
        active = raw.get(plat) or {}
        active_key = _account_key(plat, active) if active.get("access_token") else ""
        for key, cfg in ((raw.get(SAVED_KEY) or {}).get(plat) or {}).items():
            if not isinstance(cfg, dict) or not cfg.get("access_token"):
                continue
            k = f"{plat}:{key}"
            if fetch_avatars and k not in av:
                url = _fetch_avatar(plat, key)
                _save_avatar(k, url)
                av[k] = url
            out.append({"platform": plat, "platform_label": PLATFORM_LABEL[plat], "key": key, "id": k,
                        "name": _account_label(cfg), "avatar": av.get(k) or "", "active": key == active_key})
    return out


def current(accounts: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    accounts = accounts if accounts is not None else list_accounts(fetch_avatars=False)
    ws = (load_settings().get("workspace") or {}).get("id")
    pick = next((a for a in accounts if a["id"] == ws), None) or next((a for a in accounts if a["platform"] == "youtube" and a["active"]), None) \
        or (accounts[0] if accounts else None)
    st = load_settings()
    if pick and not (st.get("workspace") or {}).get("legacy"):
        # les vidéos d'avant les espaces appartiennent au premier espace choisi
        save_settings({"workspace": {"id": pick["id"], "legacy": pick["id"]}})
    return pick


def select(account_id: str) -> Dict[str, Any]:
    from core.social_publisher import FreeSocialPublisher as P
    accounts = list_accounts(fetch_avatars=False)
    acc = next((a for a in accounts if a["id"] == account_id), None)
    if not acc:
        raise ValueError("Compte introuvable : connecte-le d'abord.")
    P.switch_account(acc["platform"], acc["key"])
    save_settings({"workspace": {"id": acc["id"]}})
    return acc


def owner_tag() -> Optional[Dict[str, str]]:
    """À enregistrer dans metadata.json de chaque nouvelle vidéo."""
    acc = current()
    return {"id": acc["id"], "platform": acc["platform"], "name": acc["name"]} if acc else None


def belongs(render: Dict[str, Any], ws_id: Optional[str]) -> bool:
    if not ws_id:
        return True
    tag = (render.get("account") or {}).get("id")
    if tag:
        return tag == ws_id
    return ws_id == (load_settings().get("workspace") or {}).get("legacy")
