import json
import math
import os
import secrets
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlencode
import requests

from config import STORAGE_DIR
from core.vault import encrypt_sensitive_fields, decrypt_sensitive_fields

ACCOUNTS_FILE = STORAGE_DIR / "social_accounts.json"
OAUTH_APPS_FILE = STORAGE_DIR / "oauth_apps.json"
QUEUE_FILE = STORAGE_DIR / "publish_queue.json"

DEFAULT_OAUTH_RELAY_URL = os.getenv(
    "CLIPOA_OAUTH_RELAY_URL",
    "https://clipoa-oauth.clipoa-studio.workers.dev",
).strip().rstrip("/")

GRAPH_VERSION = "v21.0"

_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_PENDING_OAUTH_STATES: Dict[str, Dict[str, Any]] = {}
_RELAY_CACHE_LOCK = threading.Lock()
_RELAY_STATUS_CACHE: Dict[str, Any] = {"url": "", "ts": 0.0, "providers": {}}

PLATFORMS = {
    "youtube": {
        "name": "YouTube Shorts",
        "short_name": "YouTube",
        "oauth_provider": "youtube",
        "color": "#FF0000",
        "fields": [
            "access_token",
            "refresh_token",
            "expires_at",
            "client_id",
            "client_secret",
            "channel_name",
            "channel_id",
            "via_relay",
        ],
        "help": "YouTube Data API v3 — upload et programmation directe en Shorts.",
    },
    "instagram": {
        "name": "Instagram Reels",
        "short_name": "Instagram",
        "oauth_provider": "meta",
        "color": "#E1306C",
        "fields": [
            "access_token",
            "ig_user_id",
            "username",
            "page_id",
            "page_name",
            "via_relay",
        ],
        "help": "Instagram Graph API (Upload binaire direct Reels — Compte Pro/Créateur).",
    },
    "facebook": {
        "name": "Facebook Reels",
        "short_name": "Facebook",
        "oauth_provider": "meta",
        "color": "#1877F2",
        "fields": [
            "access_token",
            "page_id",
            "page_name",
            "available_pages",
            "via_relay",
        ],
        "help": "Facebook Graph API Reels (Publication directe sur ta Page Facebook).",
    },
    "tiktok": {
        "name": "TikTok",
        "short_name": "TikTok",
        "oauth_provider": "tiktok",
        "color": "#00F2EA",
        "fields": [
            "access_token",
            "refresh_token",
            "expires_at",
            "client_id",
            "client_secret",
            "open_id",
            "username",
            "via_relay",
        ],
        "help": "TikTok Content Posting API v2 — Direct Post & rafraîchissement auto.",
    },
}


def _atomic_write_json(path: Path, data: Any, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = encrypt_sensitive_fields(data) if path in (ACCOUNTS_FILE, OAUTH_APPS_FILE) else data
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(tmp_path, mode)
        except OSError:
            pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _parse_scheduled_datetime(raw: str) -> Optional[datetime]:
    """Parse ISO datetime strings safely across Python 3.9+ (naive or timezone-aware)."""
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def _http_json_with_curl_fallback(
    method: str,
    url: str,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Performs an HTTPS JSON request with fallback to macOS /usr/bin/curl when
    Apple Python 3.9's legacy LibreSSL 2.8.3 fails TLS 1.3 handshakes on Cloudflare Workers.
    """
    try:
        if method.upper() == "POST":
            r = requests.post(url, json=json_body or {}, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        if r.status_code < 500:
            return r.json()
    except requests.exceptions.SSLError:
        try:
            cmd = ["curl", "-sS", "--max-time", str(timeout), "-X", method.upper()]
            if json_body is not None:
                cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(json_body)]
            cmd.append(url)
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout)
        except Exception:
            return None
    except Exception:
        return None
    return None



SAVED_KEY = "_saved"

_IDENTITY_FIELDS = {
    "youtube": ("channel_id",),
    "tiktok": ("open_id", "username"),
    "instagram": ("ig_user_id", "ig_username"),
    "facebook": ("page_id",),
}


def _identity_from(platform: str, data: Dict[str, Any]) -> str:
    for f in _IDENTITY_FIELDS.get(platform, ()):
        v = str((data or {}).get(f) or "").strip()
        if v:
            return v
    return ""


def _account_key(platform: str, entry: Dict[str, Any]) -> str:
    """Identifiant stable d'un compte : id de chaîne / profil / page, sinon son nom."""
    ident = _identity_from(platform, entry)
    if ident:
        return ident
    label = str((entry or {}).get("channel_name") or (entry or {}).get("username") or (entry or {}).get("page_name") or "").strip()
    return f"label:{label}" if label else "default"


# Noms par défaut posés quand TikTok n'a pas donné le nom du compte : jamais affichés comme un vrai compte
_GENERIC_TIKTOK_NAMES = {"", "compte tiktok", "tiktok", "tiktok connecté", "tiktok (connecté)", "connecté", "compte"}


def _is_generic_name(name: Any) -> bool:
    return str(name or "").strip().lower() in _GENERIC_TIKTOK_NAMES


def _tiktok_display_name(access_token: str) -> str:
    """Nom du compte TikTok (« @pseudo » ou nom affiché). « username » exige le scope user.info.profile :
    sans lui TikTok refuse toute la requête, d'où le second essai avec display_name seul (scope user.info.basic)."""
    if not access_token or access_token.startswith(("same_browser:", "browser_session:")):
        return ""
    for fields in ("open_id,display_name,username", "open_id,display_name"):
        try:
            r = requests.get(
                f"https://open.tiktokapis.com/v2/user/info/?fields={fields}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if r.status_code != 200:
                continue
            user = (r.json().get("data") or {}).get("user") or {}
            if user.get("username"):
                return "@" + str(user["username"]).lstrip("@")
            if user.get("display_name"):
                return str(user["display_name"]).strip()
        except Exception:
            continue
    return ""


def _account_label(entry: Dict[str, Any]) -> str:
    return str(
        entry.get("channel_name") or entry.get("username") or entry.get("page_name")
        or entry.get("ig_username") or "Compte"
    )


class FreeSocialPublisher:
    """
    Système de connexion OAuth 2.0 1-clic et d'auto-publication programmée de Shorts/Reels :
    - YouTube Shorts (YouTube Data API v3 resumable upload + auto-refresh)
    - Instagram Reels (Instagram Graph API resumable binary upload via rupload.facebook.com — zéro ngrok requis)
    - Facebook Reels (Facebook Graph API 3-phase video_reels via rupload.facebook.com)
    - TikTok (TikTok Content Posting API v2 + auto-refresh 365j)
    """

    _scheduler_started = False

    # ---------- OAuth CSRF State Store ----------

    @classmethod
    def create_oauth_state(cls, provider: str, target: str = "", return_view: str = "auto") -> str:
        nonce = secrets.token_urlsafe(24)
        now = time.time()
        with _STATE_LOCK:
            expired = [k for k, v in _PENDING_OAUTH_STATES.items() if now - v.get("ts", 0) > 900]
            for k in expired:
                _PENDING_OAUTH_STATES.pop(k, None)
            _PENDING_OAUTH_STATES[nonce] = {
                "provider": provider,
                "target": target or provider,
                "return_view": return_view or "auto",
                "ts": now,
            }
        return nonce

    @classmethod
    def consume_oauth_state(cls, nonce: str) -> Optional[Dict[str, Any]]:
        if not nonce:
            return None
        with _STATE_LOCK:
            entry = _PENDING_OAUTH_STATES.pop(nonce, None)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > 900:
            return None
        return entry

    @staticmethod
    def resolve_provider_and_target(platform_or_provider: str) -> Tuple[str, str]:
        key = (platform_or_provider or "").strip().lower()
        if key == "instagram":
            return "meta", "instagram"
        if key == "facebook":
            return "meta", "facebook"
        if key == "meta":
            return "meta", "both"
        if key in ("youtube", "tiktok"):
            return key, key
        raise ValueError(f"Réseau ou provider OAuth inconnu : {platform_or_provider}")

    # ---------- Accounts Management ----------

    @classmethod
    def load_accounts(cls) -> Dict[str, Any]:
        with _LOCK:
            data: Dict[str, Any] = {}
            try:
                if ACCOUNTS_FILE.exists():
                    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                        data = decrypt_sensitive_fields(json.load(f))
                if not isinstance(data, dict):
                    data = {}
                for k in PLATFORMS:
                    data.setdefault(k, {"connected": False})
                saved = data.setdefault(SAVED_KEY, {})
                for k in PLATFORMS:
                    saved.setdefault(k, {})
                    active = data.get(k) or {}
                    if active.get("access_token"):
                        akey = _account_key(k, active)
                        if akey and akey not in saved[k]:
                            saved[k][akey] = dict(active)
                return data
            except Exception:
                out: Dict[str, Any] = {k: {"connected": False} for k in PLATFORMS}
                out[SAVED_KEY] = {k: {} for k in PLATFORMS}
                return out

    @classmethod
    def get_public_accounts_status(cls) -> Dict[str, Any]:
        """Returns connection state without leaking raw secret tokens to HTML templates."""
        raw = cls.load_accounts()
        oauth_apps = cls.get_public_oauth_apps()
        out = {}
        for key, meta in PLATFORMS.items():
            cfg = raw.get(key, {})
            tok_str = str(cfg.get("access_token") or "")
            has_token = bool(tok_str)
            is_shortcut = tok_str.startswith(("same_browser:", "browser_session:"))
            auto_api = has_token and not is_shortcut
            oa_prov = meta["oauth_provider"]

            raw_pages = cfg.get("available_pages") if isinstance(cfg.get("available_pages"), list) else []
            safe_pages = [
                {
                    "id": str(p.get("id") or ""),
                    "name": str(p.get("name") or "Page Facebook"),
                    "ig_user_id": str((p.get("instagram_business_account") or {}).get("id") or ""),
                    "ig_username": str((p.get("instagram_business_account") or {}).get("username") or ""),
                }
                for p in raw_pages
                if isinstance(p, dict) and p.get("id")
            ]

            out[key] = {
                "id": key,
                "name": meta["name"],
                "short_name": meta["short_name"],
                "oauth_provider": oa_prov,
                "oauth_ready": bool(oauth_apps.get(oa_prov, {}).get("configured")),
                "color": meta["color"],
                "help": meta["help"],
                "connected": has_token,
                "auto_api": auto_api,
                "auth_mode": "shortcut" if is_shortcut else ("oauth_api" if has_token else "none"),
                "label": (
                    cfg.get("channel_name")
                    or cfg.get("username")
                    or cfg.get("page_name")
                    or ("Connecté" if auto_api else ("Raccourci Studio" if is_shortcut else "Non connecté"))
                ),
                "ig_user_id": cfg.get("ig_user_id", ""),
                "page_id": cfg.get("page_id", ""),
                "open_id": cfg.get("open_id", ""),
                "available_pages": safe_pages,
                "account_key": _account_key(key, cfg) if has_token else "",
                "accounts": [
                    {
                        "key": akey,
                        "label": _account_label(aval),
                        "active": has_token and akey == _account_key(key, cfg),
                    }
                    for akey, aval in ((raw.get(SAVED_KEY) or {}).get(key) or {}).items()
                    if isinstance(aval, dict) and aval.get("access_token")
                    # ancienne fiche « TikTok (Connecté) » sans identifiant de compte : ce n'est pas un vrai compte
                    and not (key == "tiktok" and not aval.get("open_id") and _is_generic_name(_account_label(aval)))
                ],
            }
        return out

    @classmethod
    def save_account(cls, platform: str, credentials: Dict[str, Any], account_key: str = "") -> Dict[str, Any]:
        if platform not in PLATFORMS:
            raise ValueError(f"Plateforme inconnue : {platform}")
        accounts = cls.load_accounts()
        saved = accounts[SAVED_KEY].setdefault(platform, {})
        active_entry = accounts.get(platform, {}) or {}
        active_key = _account_key(platform, active_entry) if active_entry.get("access_token") else ""

        # Mise à jour d'un compte enregistré mais non actif (ex. renouvellement de jeton
        # pour une publication programmée sur une autre chaîne) : on ne touche pas au compte actif.
        if account_key and account_key != active_key and account_key in saved:
            entry = dict(saved[account_key])
            for field in PLATFORMS[platform]["fields"]:
                if field in credentials and credentials[field] is not None:
                    val = credentials[field]
                    entry[field] = val if isinstance(val, (list, dict, bool, int, float)) else (str(val).strip() or entry.get(field, ""))
            entry["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            saved[account_key] = entry
            with _LOCK:
                _atomic_write_json(ACCOUNTS_FILE, accounts, mode=0o600)
            return cls.get_public_accounts_status()[platform]

        entry = active_entry
        # Nouveau compte (autre chaîne / autre profil) : on repart d'une fiche vierge
        # pour ne jamais mélanger les jetons de deux comptes.
        new_ident = _identity_from(platform, credentials)
        old_ident = _identity_from(platform, entry)
        if new_ident and old_ident and new_ident != old_ident:
            old_rt = entry.get("refresh_token")
            entry = dict(saved.get(new_ident) or {})
            if old_rt and credentials.get("refresh_token") == old_rt and not entry.get("refresh_token"):
                credentials = {k: v for k, v in credentials.items() if k != "refresh_token"}
        # If switching from shortcut mode to real OAuth (or vice-versa), clean stale mode fields
        new_tok = str(credentials.get("access_token") or "").strip()
        old_tok = str(entry.get("access_token") or "").strip()
        if new_tok and old_tok.startswith(("same_browser:", "browser_session:")) and not new_tok.startswith(("same_browser:", "browser_session:")):
            entry = {}

        for field in PLATFORMS[platform]["fields"]:
            if field in credentials and credentials[field] is not None:
                val = credentials[field]
                if isinstance(val, (list, dict, bool, int, float)):
                    entry[field] = val
                else:
                    sval = str(val).strip()
                    if sval:
                        entry[field] = sval
        entry["connected"] = bool(entry.get("access_token"))
        entry["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
        accounts[platform] = entry
        if entry.get("access_token"):
            new_key = _account_key(platform, entry)
            if new_key:
                saved[new_key] = dict(entry)
        with _LOCK:
            _atomic_write_json(ACCOUNTS_FILE, accounts, mode=0o600)
        return cls.get_public_accounts_status()[platform]

    @classmethod
    def refresh_tiktok_names(cls) -> int:
        """Comptes TikTok branchés sous un nom générique (« Compte TikTok ») : redemande leur vrai nom à TikTok.
        Ne touche qu'au champ username (jetons conservés). Renvoie le nombre de comptes renommés."""
        raw = cls.load_accounts()
        renamed = 0
        for akey, entry in list(((raw.get(SAVED_KEY) or {}).get("tiktok") or {}).items()):
            if not isinstance(entry, dict) or not entry.get("access_token") or not entry.get("open_id"):
                continue
            if not _is_generic_name(entry.get("username")):
                continue
            try:
                token = cls._ensure_tiktok_token(dict(entry, _account_key=akey))
                name = _tiktok_display_name(token)
                if name:
                    cls.save_account("tiktok", {"open_id": entry["open_id"], "username": name}, account_key=akey)
                    renamed += 1
            except Exception as e:
                print(f"⚠️ Nom du compte TikTok non récupéré : {e}")
        return renamed

    @classmethod
    def disconnect_account(cls, platform: str, account_key: str = "") -> Dict[str, Any]:
        """Retire un compte enregistré (par défaut le compte actif). S'il en reste d'autres,
        le premier devient actif."""
        if platform not in PLATFORMS:
            raise ValueError(f"Plateforme inconnue : {platform}")
        accounts = cls.load_accounts()
        saved = accounts[SAVED_KEY].setdefault(platform, {})
        active = accounts.get(platform, {}) or {}
        active_key = _account_key(platform, active) if active.get("access_token") else ""
        target = account_key or active_key
        if target:
            saved.pop(target, None)
        if not target or target == active_key:
            remaining = [v for v in saved.values() if isinstance(v, dict) and v.get("access_token")]
            accounts[platform] = dict(remaining[0]) if remaining else {"connected": False}
        with _LOCK:
            _atomic_write_json(ACCOUNTS_FILE, accounts, mode=0o600)
        return cls.get_public_accounts_status()[platform]

    @classmethod
    def _saved_refresh_token(cls, platform: str, ident: str) -> str:
        if not ident:
            return ""
        saved = (cls.load_accounts().get(SAVED_KEY) or {}).get(platform) or {}
        return str((saved.get(ident) or {}).get("refresh_token") or "")

    @classmethod
    def switch_account(cls, platform: str, account_key: str) -> Dict[str, Any]:
        """Rend actif un compte déjà enregistré (changement de chaîne en 1 clic)."""
        if platform not in PLATFORMS:
            raise ValueError(f"Plateforme inconnue : {platform}")
        accounts = cls.load_accounts()
        saved = accounts[SAVED_KEY].setdefault(platform, {})
        if account_key not in saved:
            raise ValueError("Ce compte n'est pas enregistré dans ClipRoll.")
        accounts[platform] = dict(saved[account_key])
        with _LOCK:
            _atomic_write_json(ACCOUNTS_FILE, accounts, mode=0o600)
        return cls.get_public_accounts_status()[platform]

    @classmethod
    def get_account_config(cls, platform: str, account_key: str = "", accounts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fiche complète d'un compte (actif par défaut), annotée de sa clé pour les renouvellements de jeton."""
        accounts = accounts or cls.load_accounts()
        if account_key:
            cfg = dict(((accounts.get(SAVED_KEY) or {}).get(platform) or {}).get(account_key) or {})
        else:
            cfg = dict(accounts.get(platform, {}) or {})
        if cfg.get("access_token"):
            cfg["_account_key"] = account_key or _account_key(platform, cfg)
        return cfg

    # ---------- OAuth 2.0 App Config & Relay Resolution ----------

    @classmethod
    def load_oauth_apps(cls) -> Dict[str, Any]:
        with _LOCK:
            default = {
                "youtube": {},
                "tiktok": {},
                "meta": {},
                "relay": {
                    "url": DEFAULT_OAUTH_RELAY_URL,
                    "enabled": True,
                    "prefer_relay": bool(os.getenv("CLIPOA_OAUTH_RELAY_URL")),
                },
            }
            if not OAUTH_APPS_FILE.exists():
                return default
            try:
                with open(OAUTH_APPS_FILE, "r", encoding="utf-8") as f:
                    data = decrypt_sensitive_fields(json.load(f))
                for k in ("youtube", "tiktok", "meta"):
                    data.setdefault(k, {})
                relay_cfg = data.get("relay") if isinstance(data.get("relay"), dict) else {}
                data["relay"] = {
                    "url": (os.getenv("CLIPOA_OAUTH_RELAY_URL") or relay_cfg.get("url") or DEFAULT_OAUTH_RELAY_URL).strip().rstrip("/"),
                    "enabled": bool(relay_cfg.get("enabled", True)),
                    "prefer_relay": bool(os.getenv("CLIPOA_OAUTH_RELAY_URL") or relay_cfg.get("prefer_relay", False)),
                }
                return data
            except Exception:
                return default

    @classmethod
    def save_relay_config(cls, relay_url: str, enabled: bool = True, prefer_relay: bool = False) -> Dict[str, Any]:
        from core.security import validate_relay_url

        cleaned_url = validate_relay_url(relay_url or DEFAULT_OAUTH_RELAY_URL)
        apps = cls.load_oauth_apps()
        apps["relay"] = {
            "url": cleaned_url or DEFAULT_OAUTH_RELAY_URL,
            "enabled": bool(enabled),
            "prefer_relay": bool(prefer_relay),
        }
        with _LOCK:
            _atomic_write_json(OAUTH_APPS_FILE, apps, mode=0o600)
        with _RELAY_CACHE_LOCK:
            _RELAY_STATUS_CACHE["ts"] = 0.0
        return cls.get_public_oauth_apps()

    @classmethod
    def _probe_relay_providers(cls, relay_url: str, force: bool = False) -> Dict[str, bool]:
        if not relay_url:
            return {}
        now = time.time()
        with _RELAY_CACHE_LOCK:
            if not force and _RELAY_STATUS_CACHE["url"] == relay_url and (now - _RELAY_STATUS_CACHE["ts"] < 60):
                return dict(_RELAY_STATUS_CACHE["providers"])

        data = _http_json_with_curl_fallback("GET", f"{relay_url}/oauth/status", timeout=3)
        providers = {}
        if isinstance(data, dict) and isinstance(data.get("providers"), dict):
            providers = {k: bool(v) for k, v in data["providers"].items()}
        with _RELAY_CACHE_LOCK:
            _RELAY_STATUS_CACHE["url"] = relay_url
            _RELAY_STATUS_CACHE["ts"] = now
            _RELAY_STATUS_CACHE["providers"] = providers
        return providers

    @classmethod
    def _provider_mode(cls, provider: str, apps: Optional[Dict[str, Any]] = None) -> str:
        """
        Returns 'local', 'relay', or 'unconfigured' for a given OAuth provider ('youtube'|'tiktok'|'meta').
        """
        apps = apps or cls.load_oauth_apps()
        cfg = apps.get(provider, {})
        local_ok = bool(cfg.get("client_id") and cfg.get("client_secret"))
        relay_cfg = apps.get("relay", {})
        relay_url = (relay_cfg.get("url") or "").strip().rstrip("/")
        relay_enabled = bool(relay_cfg.get("enabled", True) and relay_url)

        if local_ok and not relay_cfg.get("prefer_relay"):
            return "local"

        if relay_enabled:
            # Explicit env override trusts the relay URL directly if probe is skipped, else checks /oauth/status
            relay_provs = cls._probe_relay_providers(relay_url)
            if relay_provs.get(provider):
                return "relay"

        if local_ok:
            return "local"
        return "unconfigured"

    @classmethod
    def get_public_oauth_apps(cls) -> Dict[str, Any]:
        raw = cls.load_oauth_apps()
        relay_cfg = raw.get("relay", {})
        relay_url = relay_cfg.get("url", DEFAULT_OAUTH_RELAY_URL)
        out: Dict[str, Any] = {}
        for k in ("youtube", "tiktok", "meta"):
            mode = cls._provider_mode(k, raw)
            out[k] = {
                "configured": mode in ("local", "relay"),
                "mode": mode,
                "client_id": raw.get(k, {}).get("client_id", ""),
                "via_relay": mode == "relay",
            }
        out["relay"] = {
            "url": relay_url,
            "enabled": bool(relay_cfg.get("enabled", True)),
            "prefer_relay": bool(relay_cfg.get("prefer_relay", False)),
        }
        return out

    @classmethod
    def save_oauth_app(cls, provider: str, client_id: str, client_secret: str) -> Dict[str, Any]:
        if provider not in ("youtube", "tiktok", "meta"):
            raise ValueError("Provider OAuth invalide")
        cid = client_id.strip()
        csec = client_secret.strip()
        if provider == "youtube":
            if cid.startswith("AIza") or csec.startswith("AIza") or not cid.endswith(".apps.googleusercontent.com"):
                raise ValueError(
                    "Ce n'est pas un ID client OAuth Google : dans Google Cloud → Identifiants → + Créer des identifiants → "
                    "choisis « ID client OAuth » (Application Web, pas « Clé API »). Le Client ID finit par .apps.googleusercontent.com."
                )
        apps = cls.load_oauth_apps()
        apps[provider] = {"client_id": cid, "client_secret": csec}
        with _LOCK:
            _atomic_write_json(OAUTH_APPS_FILE, apps, mode=0o600)
        return cls.get_public_oauth_apps()[provider]

    @classmethod
    def build_oauth_authorize_url(
        cls,
        platform_or_provider: str,
        base_url: str,
        return_view: str = "auto",
    ) -> str:
        provider, target = cls.resolve_provider_and_target(platform_or_provider)
        apps = cls.load_oauth_apps()
        mode = cls._provider_mode(provider, apps)
        nonce = cls.create_oauth_state(provider=provider, target=target, return_view=return_view)

        if mode == "relay":
            relay_url = apps["relay"]["url"].rstrip("/")
            return_to = f"{base_url.rstrip('/')}/oauth/{provider}/relay-done"
            return f"{relay_url}/oauth/{provider}/start?" + urlencode(
                {"return_to": return_to, "nonce": nonce, "target": target}
            )

        cfg = apps.get(provider, {})
        cid = cfg.get("client_id", "")
        if not cid or mode == "unconfigured":
            label_map = {"youtube": "YouTube", "tiktok": "TikTok", "meta": "Meta (Instagram / Facebook)"}
            raise ValueError(
                f"Identifiants OAuth {label_map.get(provider, provider)} non configurés."
            )

        redirect_uri = f"{base_url.rstrip('/')}/oauth/{provider}/callback"
        if provider == "youtube":
            params = {
                "client_id": cid,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
                "access_type": "offline",
                "prompt": "consent select_account",
                "include_granted_scopes": "true",
                "state": nonce,
            }
            return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

        if provider == "tiktok":
            params = {
                "client_key": cid,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "user.info.basic,video.publish,video.upload",
                "state": nonce,
            }
            return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(params)

        if provider == "meta":
            params = {
                "client_id": cid,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management",
                "state": nonce,
            }
            return f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth?" + urlencode(params)

        raise ValueError("Provider OAuth inconnu")

    # ---------- Meta Pages & Instagram Helper ----------

    @classmethod
    def _save_meta_pages_and_accounts(
        cls,
        user_token: str,
        pages: List[Dict[str, Any]],
        target: str = "both",
        via_relay: bool = False,
    ) -> Dict[str, Any]:
        """
        Saves Facebook Page and/or linked Instagram Professional account from /me/accounts.
        Scans all returned Pages so an Instagram Business/Creator account on Page #2 is never missed.
        """
        connected_platforms: List[str] = []
        if not pages:
            if target == "instagram":
                raise RuntimeError(
                    "Aucune Page Facebook liée à ton compte Meta n'a été trouvée. "
                    "Pour l'API Instagram Reels, ton compte Instagram doit être en mode Professionnel (Créateur/Business) et lié à une Page Facebook."
                )
            raise RuntimeError(
                "Aucune Page Facebook détectée sur ce compte Meta (coche bien ta Page lors de l'autorisation Facebook)."
            )

        existing_accounts = cls.load_accounts()
        preferred_fb_id = existing_accounts.get("facebook", {}).get("page_id", "")
        preferred_ig_id = existing_accounts.get("instagram", {}).get("ig_user_id", "")

        # Pick Facebook Page (preserve previously chosen page if still in list, else first page)
        fb_page = next((p for p in pages if p.get("id") == preferred_fb_id), None) or pages[0]

        # Pick Page that actually owns an instagram_business_account
        ig_pages = [p for p in pages if isinstance(p.get("instagram_business_account"), dict) and p["instagram_business_account"].get("id")]
        ig_page = next((p for p in ig_pages if p["instagram_business_account"].get("id") == preferred_ig_id), None) or (ig_pages[0] if ig_pages else None)

        if target in ("facebook", "both", "meta") or (target == "instagram" and not existing_accounts.get("facebook", {}).get("access_token")):
            fb_token = fb_page.get("access_token") or user_token
            cls.save_account("facebook", {
                "access_token": fb_token,
                "page_id": fb_page.get("id", ""),
                "page_name": fb_page.get("name", "Page Facebook"),
                "available_pages": pages,
                "via_relay": via_relay,
            })
            connected_platforms.append("facebook")

        if ig_page:
            ig = ig_page["instagram_business_account"]
            ig_token = ig_page.get("access_token") or user_token
            ig_handle = ig.get("username") or ig.get("name") or "instagram"
            if not ig_handle.startswith("@"):
                ig_handle = f"@{ig_handle}"
            cls.save_account("instagram", {
                "access_token": ig_token,
                "ig_user_id": ig["id"],
                "username": ig_handle,
                "page_id": ig_page.get("id", ""),
                "page_name": ig_page.get("name", ""),
                "via_relay": via_relay,
            })
            connected_platforms.append("instagram")
        elif target == "instagram":
            raise RuntimeError(
                f"Page Facebook « {fb_page.get('name', '')} » connectée, mais aucun compte Instagram Professionnel (Créateur/Business) "
                "n'y est rattaché. Dans Instagram → Paramètres → Type de compte, passe en Créateur/Pro et lie ta Page Facebook."
            )

        return {"ok": True, "connected_platforms": connected_platforms}

    @classmethod
    def select_meta_page(cls, page_id: str) -> Dict[str, Any]:
        """Switches active Facebook Page (and linked Instagram account if attached) when user manages multiple Pages."""
        accounts = cls.load_accounts()
        fb_cfg = accounts.get("facebook", {})
        pages = fb_cfg.get("available_pages") or []
        chosen = next((p for p in pages if str(p.get("id")) == str(page_id)), None)
        if not chosen:
            raise ValueError("Page Facebook introuvable dans les pages autorisées.")
        page_token = chosen.get("access_token") or fb_cfg.get("access_token", "")
        cls.save_account("facebook", {
            "access_token": page_token,
            "page_id": chosen.get("id", ""),
            "page_name": chosen.get("name", "Page Facebook"),
            "available_pages": pages,
            "via_relay": bool(fb_cfg.get("via_relay")),
        })
        ig = chosen.get("instagram_business_account")
        if isinstance(ig, dict) and ig.get("id"):
            uname = ig.get("username") or ig.get("name") or "instagram"
            if not uname.startswith("@"):
                uname = f"@{uname}"
            cls.save_account("instagram", {
                "access_token": page_token,
                "ig_user_id": ig["id"],
                "username": uname,
                "page_id": chosen.get("id", ""),
                "page_name": chosen.get("name", ""),
                "via_relay": bool(fb_cfg.get("via_relay")),
            })
        return cls.get_public_accounts_status()

    # ---------- OAuth Callback Handlers (Local & Relay) ----------

    @classmethod
    def handle_oauth_callback(
        cls,
        provider: str,
        code: str,
        base_url: str,
        target: str = "",
    ) -> Dict[str, Any]:
        apps = cls.load_oauth_apps()
        cfg = apps.get(provider, {})
        cid = cfg.get("client_id", "")
        csec = cfg.get("client_secret", "")
        redirect_uri = f"{base_url.rstrip('/')}/oauth/{provider}/callback"

        if provider == "youtube":
            r = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": cid,
                    "client_secret": csec,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=20,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Erreur token YouTube : {r.text[:250]}")
            tok = r.json()
            access_token = tok.get("access_token", "")
            refresh_token = tok.get("refresh_token", "")
            expires_in = int(tok.get("expires_in") or 3600)
            channel_name = "Chaîne YouTube"
            channel_id = ""
            try:
                ch = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                if ch.status_code == 200 and ch.json().get("items"):
                    first = ch.json()["items"][0]
                    channel_name = first["snippet"]["title"]
                    channel_id = first.get("id", "")
            except Exception:
                pass
            existing_rt = cls._saved_refresh_token("youtube", channel_id)
            acc = cls.save_account("youtube", {
                "access_token": access_token,
                "refresh_token": refresh_token or existing_rt,
                "expires_at": int(time.time()) + expires_in,
                "client_id": cid,
                "client_secret": csec,
                "channel_name": channel_name,
                "channel_id": channel_id,
                "via_relay": False,
            })
            return {"ok": True, "connected_platforms": ["youtube"], "account": acc}

        if provider == "tiktok":
            r = requests.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": cid,
                    "client_secret": csec,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Erreur token TikTok : {r.text[:250]}")
            tok = r.json()
            access_token = tok.get("access_token", "")
            if not access_token:
                raise RuntimeError(f"TikTok n'a pas renvoyé de token : {r.text[:200]}")
            expires_in = int(tok.get("expires_in") or 86400)
            username = _tiktok_display_name(access_token) or "Compte TikTok"
            acc = cls.save_account("tiktok", {
                "access_token": access_token,
                "refresh_token": tok.get("refresh_token", ""),
                "expires_at": int(time.time()) + expires_in,
                "client_id": cid,
                "client_secret": csec,
                "open_id": tok.get("open_id", ""),
                "username": username,
                "via_relay": False,
            })
            return {"ok": True, "connected_platforms": ["tiktok"], "account": acc}

        if provider == "meta":
            r = requests.get(
                f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
                params={
                    "client_id": cid,
                    "client_secret": csec,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                timeout=20,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Erreur token Meta : {r.text[:250]}")
            short_token = r.json().get("access_token", "")
            if not short_token:
                raise RuntimeError("Token Meta manquant")

            # Exchange 1-hour user token -> 60-day Long-Lived User Token so Page/IG tokens NEVER expire
            user_token = short_token
            try:
                ll_res = requests.get(
                    f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": cid,
                        "client_secret": csec,
                        "fb_exchange_token": short_token,
                    },
                    timeout=15,
                )
                if ll_res.status_code == 200 and ll_res.json().get("access_token"):
                    user_token = ll_res.json()["access_token"]
            except Exception:
                pass

            pages_res = requests.get(
                f"https://graph.facebook.com/{GRAPH_VERSION}/me/accounts",
                params={
                    "fields": "id,name,access_token,instagram_business_account{id,username,name}",
                    "access_token": user_token,
                },
                timeout=15,
            )
            pages = pages_res.json().get("data", []) if pages_res.status_code == 200 else []
            return cls._save_meta_pages_and_accounts(
                user_token=user_token,
                pages=pages,
                target=target or "both",
                via_relay=False,
            )

        raise ValueError("Provider inconnu")

    @classmethod
    def handle_relay_done(cls, provider: str, payload: Dict[str, Any], target: str = "") -> Dict[str, Any]:
        token = (payload.get("access_token") or "").strip()
        if not token:
            raise ValueError("token_manquant")

        if provider == "youtube":
            expires_in = int(payload.get("expires_in") or 3600)
            channel_name = (payload.get("name") or "").strip()
            channel_id = (payload.get("channel_id") or "").strip()
            if not channel_name or channel_name == "Chaîne YouTube":
                try:
                    ch = requests.get(
                        "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                    )
                    if ch.status_code == 200 and ch.json().get("items"):
                        first = ch.json()["items"][0]
                        channel_name = first["snippet"]["title"]
                        channel_id = first.get("id", "")
                except Exception:
                    channel_name = channel_name or "Chaîne YouTube"
            existing_rt = cls._saved_refresh_token("youtube", channel_id)
            cls.save_account("youtube", {
                "access_token": token,
                "refresh_token": (payload.get("refresh_token") or "").strip() or existing_rt,
                "expires_at": int(time.time()) + expires_in,
                "channel_name": channel_name or "Chaîne YouTube",
                "channel_id": channel_id,
                "via_relay": True,
            })
            return {"ok": True, "connected_platforms": ["youtube"]}

        if provider == "tiktok":
            expires_in = int(payload.get("expires_in") or 86400)
            cls.save_account("tiktok", {
                "access_token": token,
                "refresh_token": (payload.get("refresh_token") or "").strip(),
                "expires_at": int(time.time()) + expires_in,
                "open_id": (payload.get("open_id") or "").strip(),
                # le relais peut ne pas avoir obtenu le nom : on le redemande ici avec le jeton
                "username": ((payload.get("name") or "").strip() if not _is_generic_name(payload.get("name"))
                             else (_tiktok_display_name(token) or "Compte TikTok")),
                "via_relay": True,
            })
            return {"ok": True, "connected_platforms": ["tiktok"]}

        if provider == "meta":
            pages: List[Dict[str, Any]] = []
            raw_pages = payload.get("pages_json")
            if raw_pages:
                try:
                    parsed = json.loads(raw_pages)
                    if isinstance(parsed, list):
                        pages = parsed
                except Exception:
                    pages = []
            if not pages and payload.get("page_id"):
                page_obj: Dict[str, Any] = {
                    "id": payload.get("page_id"),
                    "name": payload.get("page_name", "Page Facebook"),
                    "access_token": token,
                }
                if payload.get("ig_user_id"):
                    page_obj["instagram_business_account"] = {
                        "id": payload.get("ig_user_id"),
                        "username": payload.get("ig_username", "instagram"),
                    }
                pages = [page_obj]
            if not pages:
                try:
                    p_res = requests.get(
                        f"https://graph.facebook.com/{GRAPH_VERSION}/me/accounts",
                        params={
                            "fields": "id,name,access_token,instagram_business_account{id,username,name}",
                            "access_token": token,
                        },
                        timeout=15,
                    )
                    if p_res.status_code == 200:
                        pages = p_res.json().get("data", [])
                except Exception:
                    pass
            return cls._save_meta_pages_and_accounts(
                user_token=token,
                pages=pages,
                target=target or "both",
                via_relay=True,
            )

        raise ValueError("Provider inconnu")

    # ---------- Queue & Scheduler ----------

    @classmethod
    def load_queue(cls) -> List[Dict[str, Any]]:
        with _LOCK:
            if not QUEUE_FILE.exists():
                return []
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []

    @classmethod
    def save_queue(cls, items: List[Dict[str, Any]]):
        with _LOCK:
            _atomic_write_json(QUEUE_FILE, items, mode=0o600)

    @classmethod
    def _update_queue_post(cls, post_id: str, **updates) -> Optional[Dict[str, Any]]:
        with _LOCK:
            if not QUEUE_FILE.exists():
                return None
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    queue = json.load(f)
            except Exception:
                return None
            found = None
            for item in queue:
                if item.get("id") == post_id:
                    item.update(updates)
                    found = dict(item)
                    break
            if found is not None:
                _atomic_write_json(QUEUE_FILE, queue, mode=0o600)
            return found

    @classmethod
    def create_post(
        cls,
        render_id: str,
        video_path: str,
        title: str,
        caption: str,
        platforms: List[str],
        scheduled_at: Optional[str] = None,
        publish_now: bool = False,
        public_video_url: Optional[str] = None,
        async_publish: bool = False,
    ) -> Dict[str, Any]:
        valid_platforms = [p for p in platforms if p in PLATFORMS]
        if not valid_platforms:
            raise ValueError("Sélectionne au moins un réseau social valide.")

        is_scheduled = bool(scheduled_at and not publish_now)
        if is_scheduled:
            dt = _parse_scheduled_datetime(scheduled_at or "")
            if dt is None:
                raise ValueError("Format de date/heure de programmation invalide.")

        initial_results = (
            {p: {"ok": False, "pending": True, "message": "Envoi API en cours…"} for p in valid_platforms}
            if not is_scheduled
            else {}
        )

        post = {
            "id": f"post_{uuid.uuid4().hex[:8]}",
            "render_id": render_id,
            "video_path": video_path,
            "public_video_url": public_video_url or "",
            "title": title.strip()[:100],
            "caption": caption.strip(),
            "platforms": valid_platforms,
            "account_keys": cls._active_account_keys(valid_platforms),
            "scheduled_at": scheduled_at if is_scheduled else "",
            "status": "scheduled" if is_scheduled else "publishing",
            "results": initial_results,
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        queue = cls.load_queue()
        queue.insert(0, post)
        cls.save_queue(queue)

        if not is_scheduled:
            if async_publish:
                threading.Thread(target=cls.execute_post, args=(post["id"],), daemon=True).start()
                return post
            return cls.execute_post(post["id"])
        return post

    @classmethod
    def _active_account_keys(cls, platforms: List[str]) -> Dict[str, str]:
        accounts = cls.load_accounts()
        out = {}
        for p in platforms:
            cfg = accounts.get(p, {}) or {}
            if cfg.get("access_token"):
                out[p] = _account_key(p, cfg)
        return out

    @classmethod
    def delete_post(cls, post_id: str) -> bool:
        queue = cls.load_queue()
        new_q = [p for p in queue if p.get("id") != post_id]
        if len(new_q) == len(queue):
            return False
        cls.save_queue(new_q)
        return True

    @classmethod
    def execute_post(cls, post_id: str) -> Dict[str, Any]:
        queue = cls.load_queue()
        target = next((p for p in queue if p.get("id") == post_id), None)
        if not target:
            raise FileNotFoundError("Publication introuvable")

        # Mark as publishing immediately so background scheduler cannot trigger it twice
        target["status"] = "publishing"
        cls.save_queue(queue)

        accounts = cls.load_accounts()
        video_path = target["video_path"]
        if not os.path.exists(video_path):
            target["status"] = "failed"
            target["results"] = {"file": {"ok": False, "message": f"Fichier introuvable : {video_path}"}}
            cls.save_queue(queue)
            return target

        results: Dict[str, Any] = dict(target.get("results") or {})
        ok_count = 0
        manual_count = 0
        post_keys = target.get("account_keys") or {}
        for plat in target.get("platforms", []):
            cfg = cls.get_account_config(plat, post_keys.get(plat, ""), accounts)
            if post_keys.get(plat) and not cfg.get("access_token"):
                results[plat] = {
                    "ok": False,
                    "message": f"Le compte {PLATFORMS[plat]['name']} choisi pour cette publication a été déconnecté de ClipRoll.",
                }
                cls._update_queue_post(post_id, results=dict(results))
                continue
            if not cfg.get("access_token"):
                results[plat] = {
                    "ok": False,
                    "message": f"Compte {PLATFORMS[plat]['name']} non connecté.",
                }
                cls._update_queue_post(post_id, results=dict(results))
                continue
            try:
                tok = str(cfg.get("access_token", ""))
                if tok.startswith("same_browser:"):
                    from core.browser_auth import PORTALS
                    pinfo = PORTALS.get(plat, {})
                    results[plat] = {
                        "ok": False,
                        "manual": True,
                        "open_url": pinfo.get("upload_url", ""),
                        "message": f"Raccourci Studio ({pinfo.get('name', plat)}) — connecte l'API OAuth 1-clic pour l'envoi 100% automatique sans action manuelle.",
                    }
                    manual_count += 1
                    cls._update_queue_post(post_id, results=dict(results))
                    continue
                elif tok.startswith("browser_session:"):
                    from core.browser_auth import BrowserPortalAuth
                    results[plat] = BrowserPortalAuth.publish_with_session(plat, video_path, target["title"], target["caption"])
                elif plat == "youtube":
                    results[plat] = cls._publish_youtube(cfg, video_path, target["title"], target["caption"])
                elif plat == "tiktok":
                    results[plat] = cls._publish_tiktok(cfg, video_path, target["title"], target["caption"])
                elif plat == "instagram":
                    results[plat] = cls._publish_instagram(
                        cfg,
                        video_path=video_path,
                        public_video_url=target.get("public_video_url", ""),
                        caption=target["caption"] or target["title"],
                    )
                elif plat == "facebook":
                    results[plat] = cls._publish_facebook(cfg, video_path, target["title"], target["caption"])

                if results[plat].get("ok"):
                    ok_count += 1
            except Exception as e:
                results[plat] = {"ok": False, "message": str(e)}

            cls._update_queue_post(post_id, results=dict(results))

        total = max(1, len(target.get("platforms", [])))
        if ok_count == total:
            new_status = "published"
        elif ok_count > 0:
            new_status = "partial"
        elif manual_count > 0:
            new_status = "manual_upload"
        else:
            new_status = "failed"
        published_at = time.strftime("%Y-%m-%d %H:%M")
        try:
            from core import notifier
            notifier.published(new_status, [p for p in target.get("platforms", []) if (results.get(p) or {}).get("ok")])
        except Exception:
            pass

        fresh_queue = cls.load_queue()
        updated_target = None
        for item in fresh_queue:
            if item.get("id") == post_id:
                item["status"] = new_status
                item["published_at"] = published_at
                item["results"] = results
                updated_target = item
                break
        if updated_target is not None:
            cls.save_queue(fresh_queue)
            target = updated_target
        else:
            target["status"] = new_status
            target["published_at"] = published_at
            target["results"] = results

        if ok_count > 0:
            def _auto_analyze(post_snapshot):
                try:
                    from core.analytics_engine import AnalyticsEngine
                    AnalyticsEngine.analyze_published_post(post_snapshot)
                except Exception as ae:
                    print(f"⚠️ Auto-analyse interne ignorée : {ae}")
            threading.Thread(target=_auto_analyze, args=(dict(target),), daemon=True).start()

        return target

    # ---------- Token Auto-Refresh Helpers ----------

    @classmethod
    def _ensure_youtube_token(cls, cfg: Dict[str, Any], force: bool = False) -> str:
        now = int(time.time())
        expires_at = int(cfg.get("expires_at") or 0)
        if not force and expires_at > now + 120 and cfg.get("access_token"):
            return cfg["access_token"]

        refresh_token = (cfg.get("refresh_token") or "").strip()
        if not refresh_token:
            return cfg["access_token"]

        apps = cls.load_oauth_apps()
        cid = cfg.get("client_id") or apps.get("youtube", {}).get("client_id", "")
        csec = cfg.get("client_secret") or apps.get("youtube", {}).get("client_secret", "")

        new_token = ""
        new_exp = 3600
        if cid and csec and not cfg.get("via_relay"):
            r = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": cid,
                    "client_secret": csec,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
            if r.status_code == 200 and r.json().get("access_token"):
                tok = r.json()
                new_token = tok["access_token"]
                new_exp = int(tok.get("expires_in") or 3600)
        else:
            relay_url = (apps.get("relay", {}).get("url") or DEFAULT_OAUTH_RELAY_URL).rstrip("/")
            if relay_url:
                tok = _http_json_with_curl_fallback(
                    "POST",
                    f"{relay_url}/oauth/youtube/refresh",
                    json_body={"refresh_token": refresh_token},
                    timeout=15,
                )
                if isinstance(tok, dict) and tok.get("access_token"):
                    new_token = tok["access_token"]
                    new_exp = int(tok.get("expires_in") or 3600)

        if new_token:
            cfg["access_token"] = new_token
            cfg["expires_at"] = int(time.time()) + new_exp
            cls.save_account("youtube", {
                "access_token": new_token,
                "expires_at": cfg["expires_at"],
            }, account_key=cfg.get("_account_key", ""))
            return new_token
        return cfg["access_token"]

    @classmethod
    def _ensure_tiktok_token(cls, cfg: Dict[str, Any], force: bool = False) -> str:
        now = int(time.time())
        expires_at = int(cfg.get("expires_at") or 0)
        if not force and expires_at > now + 300 and cfg.get("access_token"):
            return cfg["access_token"]

        refresh_token = (cfg.get("refresh_token") or "").strip()
        if not refresh_token:
            return cfg["access_token"]

        apps = cls.load_oauth_apps()
        cid = cfg.get("client_id") or apps.get("tiktok", {}).get("client_id", "")
        csec = cfg.get("client_secret") or apps.get("tiktok", {}).get("client_secret", "")

        new_token = ""
        new_rt = refresh_token
        new_exp = 86400
        if cid and csec and not cfg.get("via_relay"):
            r = requests.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                data={
                    "client_key": cid,
                    "client_secret": csec,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            if r.status_code == 200 and r.json().get("access_token"):
                tok = r.json()
                new_token = tok["access_token"]
                new_rt = tok.get("refresh_token") or refresh_token
                new_exp = int(tok.get("expires_in") or 86400)
        else:
            relay_url = (apps.get("relay", {}).get("url") or DEFAULT_OAUTH_RELAY_URL).rstrip("/")
            if relay_url:
                tok = _http_json_with_curl_fallback(
                    "POST",
                    f"{relay_url}/oauth/tiktok/refresh",
                    json_body={"refresh_token": refresh_token},
                    timeout=15,
                )
                if isinstance(tok, dict) and tok.get("access_token"):
                    new_token = tok["access_token"]
                    new_rt = tok.get("refresh_token") or refresh_token
                    new_exp = int(tok.get("expires_in") or 86400)

        if new_token:
            cfg["access_token"] = new_token
            cfg["refresh_token"] = new_rt
            cfg["expires_at"] = int(time.time()) + new_exp
            cls.save_account("tiktok", {
                "access_token": new_token,
                "refresh_token": new_rt,
                "expires_at": cfg["expires_at"],
            }, account_key=cfg.get("_account_key", ""))
            return new_token
        return cfg["access_token"]

    # ---------- Official Direct Platform Publishers ----------

    @classmethod
    def _publish_youtube(cls, cfg: Dict[str, Any], video_path: str, title: str, description: str) -> Dict[str, Any]:
        token = cls._ensure_youtube_token(cfg)
        clean_title = (title or "ClipRoll Short").strip()[:100]
        clean_desc = (description or "").strip()
        if "#short" not in clean_title.lower() and "#short" not in clean_desc.lower():
            clean_desc = (clean_desc + "\n\n#Shorts").strip()

        meta = {
            "snippet": {
                "title": clean_title,
                "description": clean_desc,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }
        file_size = os.path.getsize(video_path)

        def _init_upload(bearer: str):
            return requests.post(
                "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Length": str(file_size),
                    "X-Upload-Content-Type": "video/mp4",
                },
                json=meta,
                timeout=30,
            )

        init_res = _init_upload(token)
        if init_res.status_code == 401 and cfg.get("refresh_token"):
            token = cls._ensure_youtube_token(cfg, force=True)
            init_res = _init_upload(token)

        if init_res.status_code not in (200, 201):
            return {"ok": False, "message": f"YouTube init {init_res.status_code}: {init_res.text[:220]}"}

        upload_url = init_res.headers.get("Location")
        if not upload_url:
            return {"ok": False, "message": "YouTube n'a pas renvoyé d'URL d'upload."}
        with open(video_path, "rb") as f:
            up_res = requests.put(
                upload_url,
                headers={"Content-Type": "video/mp4", "Content-Length": str(file_size)},
                data=f,
                timeout=300,
            )
        if up_res.status_code in (200, 201):
            vid_id = up_res.json().get("id", "")
            return {
                "ok": True,
                "video_id": vid_id,
                "url": f"https://youtube.com/shorts/{vid_id}",
                "message": "Publié sur YouTube Shorts !",
            }
        return {"ok": False, "message": f"YouTube upload {up_res.status_code}: {up_res.text[:220]}"}

    @classmethod
    def _publish_tiktok(cls, cfg: Dict[str, Any], video_path: str, title: str, caption: str) -> Dict[str, Any]:
        token = cls._ensure_tiktok_token(cfg)
        file_size = os.path.getsize(video_path)
        chunk_size = min(file_size, 64 * 1024 * 1024)
        total_chunks = max(1, math.ceil(file_size / chunk_size))
        if total_chunks == 1:
            chunk_size = file_size

        # Query creator_info to discover allowed privacy levels on this TikTok app/account
        preferred_privacy = "PUBLIC_TO_EVERYONE"
        try:
            ci = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                json={},
                timeout=12,
            )
            if ci.status_code == 401 and cfg.get("refresh_token"):
                token = cls._ensure_tiktok_token(cfg, force=True)
                ci = requests.post(
                    "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                    json={},
                    timeout=12,
                )
            if ci.status_code == 200:
                opts = ((ci.json().get("data") or {}).get("privacy_level_options")) or []
                if opts and "PUBLIC_TO_EVERYONE" not in opts:
                    preferred_privacy = "SELF_ONLY" if "SELF_ONLY" in opts else opts[0]
        except Exception:
            pass

        def _init_tiktok(privacy: str):
            return requests.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={
                    "post_info": {
                        "title": (caption or title or "ClipRoll")[:2200],
                        "privacy_level": privacy,
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": chunk_size,
                        "total_chunk_count": total_chunks,
                    },
                },
                timeout=30,
            )

        used_privacy = preferred_privacy
        init_res = _init_tiktok(used_privacy)
        if init_res.status_code != 200 and used_privacy != "SELF_ONLY" and (
            "unaudited" in init_res.text.lower() or "privacy" in init_res.text.lower()
        ):
            used_privacy = "SELF_ONLY"
            init_res = _init_tiktok("SELF_ONLY")
        sent_to_inbox = False
        if init_res.status_code != 200 and "unaudited_client_can_only_post_to_private_accounts" in init_res.text:
            # App TikTok pas encore auditée + compte public : la publication directe est refusée.
            # Repli : envoi en brouillon dans la boîte de réception TikTok (scope video.upload),
            # l'utilisateur termine la publication dans l'app TikTok.
            init_res = requests.post(
                "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": chunk_size,
                        "total_chunk_count": total_chunks,
                    },
                },
                timeout=30,
            )
            sent_to_inbox = init_res.status_code == 200
        if init_res.status_code != 200:
            return {"ok": False, "message": f"TikTok init {init_res.status_code}: {init_res.text[:220]}"}

        payload = init_res.json().get("data", {})
        upload_url = payload.get("upload_url")
        publish_id = payload.get("publish_id", "")
        if not upload_url:
            return {"ok": False, "message": f"TikTok réponse incomplète : {init_res.text[:200]}"}

        with open(video_path, "rb") as f:
            for idx in range(total_chunks):
                chunk_bytes = f.read(chunk_size)
                start_b = idx * chunk_size
                end_b = start_b + len(chunk_bytes) - 1
                up_res = requests.put(
                    upload_url,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk_bytes)),
                        "Content-Range": f"bytes {start_b}-{end_b}/{file_size}",
                    },
                    data=chunk_bytes,
                    timeout=300,
                )
                if up_res.status_code not in (200, 201, 206):
                    return {"ok": False, "message": f"TikTok upload {up_res.status_code}: {up_res.text[:200]}"}

        # Quick status check so immediate ingestion errors are caught cleanly
        if publish_id:
            for _ in range(3):
                time.sleep(2)
                try:
                    st = requests.post(
                        "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
                        json={"publish_id": publish_id},
                        timeout=10,
                    )
                    if st.status_code == 200:
                        status_val = ((st.json().get("data") or {}).get("status") or "").upper()
                        if status_val == "FAILED":
                            fail_reason = (st.json().get("data") or {}).get("fail_reason", "inconnu")
                            return {"ok": False, "message": f"TikTok a refusé le traitement vidéo ({fail_reason})."}
                        if status_val in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                            break
                except Exception:
                    break

        if sent_to_inbox:
            return {
                "ok": True,
                "publish_id": publish_id,
                "privacy": "INBOX_DRAFT",
                "message": "Envoyé dans tes brouillons TikTok : ouvre l'app TikTok (notification) pour finir la publication. "
                "La publication directe arrivera quand l'app ClipRoll sera validée par TikTok.",
            }
        note = (
            "Publié sur TikTok !"
            if used_privacy == "PUBLIC_TO_EVERYONE"
            else "Envoyé sur TikTok (en visibilité Privée car l'app TikTok n'est pas encore auditée en production)."
        )
        return {"ok": True, "publish_id": publish_id, "privacy": used_privacy, "message": note}

    @classmethod
    def tiktok_publish_status(cls, publish_id: str, account_key: str = "") -> Dict[str, Any]:
        """Interroge TikTok sur l'état réel d'un envoi (publication directe ou brouillon)."""
        cfg = cls.get_account_config("tiktok", account_key)
        if not cfg.get("access_token"):
            return {"ok": False, "message": "TikTok non connecté."}
        token = cls._ensure_tiktok_token(cfg)
        res = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"},
            json={"publish_id": publish_id},
            timeout=15,
        )
        try:
            body = res.json()
        except Exception:
            body = {"raw": res.text[:300]}
        data = body.get("data") or {}
        err = body.get("error") or {}
        return {
            "ok": res.status_code == 200 and (err.get("code") in (None, "", "ok")),
            "http": res.status_code,
            "status": data.get("status"),
            "fail_reason": data.get("fail_reason"),
            "uploaded_bytes": data.get("uploaded_bytes"),
            "error_code": err.get("code"),
            "error_message": err.get("message"),
        }

    @classmethod
    def _publish_instagram(
        cls,
        cfg: Dict[str, Any],
        video_path: str = "",
        public_video_url: str = "",
        caption: str = "",
    ) -> Dict[str, Any]:
        """
        Publishes an Instagram Reel directly from local MP4 via Meta Resumable Upload
        (rupload.facebook.com/ig-api-upload — ZERO ngrok or external S3 URL required!),
        or via public_video_url if explicitly supplied.
        """
        ig_user_id = cfg.get("ig_user_id")
        token = cfg.get("access_token", "")
        if not ig_user_id:
            return {"ok": False, "message": "IG User ID manquant — reconnecte Instagram via OAuth."}

        creation_id = ""
        if video_path and os.path.exists(video_path) and not public_video_url:
            file_size = os.path.getsize(video_path)
            init_res = requests.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": token,
                },
                timeout=30,
            )
            if init_res.status_code != 200:
                return {"ok": False, "message": f"Instagram init {init_res.status_code}: {init_res.text[:220]}"}
            init_json = init_res.json()
            creation_id = init_json.get("id", "")
            upload_uri = init_json.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{GRAPH_VERSION}/{creation_id}"
            if not creation_id:
                return {"ok": False, "message": f"Instagram container ID manquant : {init_res.text[:180]}"}

            with open(video_path, "rb") as f:
                up_res = requests.post(
                    upload_uri,
                    headers={
                        "Authorization": f"OAuth {token}",
                        "offset": "0",
                        "file_size": str(file_size),
                        "Content-Type": "application/octet-stream",
                    },
                    data=f,
                    timeout=300,
                )
            if up_res.status_code not in (200, 201):
                return {"ok": False, "message": f"Instagram binary upload {up_res.status_code}: {up_res.text[:220]}"}
        elif public_video_url:
            create = requests.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}/media",
                data={
                    "media_type": "REELS",
                    "video_url": public_video_url,
                    "caption": caption,
                    "share_to_feed": "true",
                    "access_token": token,
                },
                timeout=30,
            )
            if create.status_code != 200:
                return {"ok": False, "message": f"Instagram container {create.status_code}: {create.text[:220]}"}
            creation_id = create.json().get("id", "")
        else:
            return {"ok": False, "message": "Fichier vidéo introuvable pour Instagram Reels."}

        # Poll container processing status (up to ~96s)
        finished = False
        for _ in range(24):
            time.sleep(4)
            try:
                st = requests.get(
                    f"https://graph.facebook.com/{GRAPH_VERSION}/{creation_id}",
                    params={"fields": "status_code,status", "access_token": token},
                    timeout=12,
                )
                if st.status_code == 200:
                    st_json = st.json()
                    code = (st_json.get("status_code") or "").upper()
                    if code == "FINISHED":
                        finished = True
                        break
                    if code in ("ERROR", "EXPIRED"):
                        detail = st_json.get("status") or st.text[:160]
                        return {"ok": False, "message": f"Instagram a refusé la vidéo ({detail})."}
            except Exception:
                pass

        if not finished:
            return {"ok": False, "message": "Délai dépassé pendant l'encodage Instagram Reels (réessaie dans 1 minute)."}

        pub = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        if pub.status_code == 200:
            media_id = pub.json().get("id", "")
            permalink = ""
            if media_id:
                try:
                    pm = requests.get(
                        f"https://graph.facebook.com/{GRAPH_VERSION}/{media_id}",
                        params={"fields": "permalink", "access_token": token},
                        timeout=10,
                    )
                    if pm.status_code == 200:
                        permalink = pm.json().get("permalink", "")
                except Exception:
                    pass
            return {
                "ok": True,
                "video_id": media_id,
                "url": permalink,
                "message": "Publié sur Instagram Reels !",
            }
        return {"ok": False, "message": f"Instagram publish {pub.status_code}: {pub.text[:220]}"}

    @classmethod
    def _publish_facebook(cls, cfg: Dict[str, Any], video_path: str, title: str, caption: str) -> Dict[str, Any]:
        """
        Publishes a real Facebook Reel via the official 3-phase /{page_id}/video_reels API
        (start -> rupload.facebook.com binary upload -> finish PUBLISHED).
        """
        page_id = cfg.get("page_id")
        token = cfg.get("access_token", "")
        if not page_id:
            return {"ok": False, "message": "Page ID Facebook manquant — reconnecte Facebook via OAuth."}

        file_size = os.path.getsize(video_path)
        start_res = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": token},
            timeout=30,
        )
        if start_res.status_code == 200 and start_res.json().get("video_id"):
            start_json = start_res.json()
            video_id = start_json["video_id"]
            upload_url = start_json.get("upload_url") or f"https://rupload.facebook.com/video-upload/{GRAPH_VERSION}/{video_id}"

            with open(video_path, "rb") as f:
                up_res = requests.post(
                    upload_url,
                    headers={
                        "Authorization": f"OAuth {token}",
                        "offset": "0",
                        "file_size": str(file_size),
                        "Content-Type": "application/octet-stream",
                    },
                    data=f,
                    timeout=300,
                )
            if up_res.status_code not in (200, 201):
                return {"ok": False, "message": f"Facebook Reels upload {up_res.status_code}: {up_res.text[:220]}"}

            fin_res = requests.post(
                f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/video_reels",
                data={
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "video_state": "PUBLISHED",
                    "title": (title or "")[:100],
                    "description": caption or title,
                    "access_token": token,
                },
                timeout=30,
            )
            if fin_res.status_code == 200:
                return {
                    "ok": True,
                    "video_id": video_id,
                    "url": f"https://www.facebook.com/reel/{video_id}",
                    "message": "Publié sur Facebook Reels !",
                }
            return {"ok": False, "message": f"Facebook Reels finish {fin_res.status_code}: {fin_res.text[:220]}"}

        # Fallback to classic /{page_id}/videos if video_reels edge is unavailable on that Page
        with open(video_path, "rb") as f:
            res = requests.post(
                f"https://graph-video.facebook.com/{GRAPH_VERSION}/{page_id}/videos",
                data={"title": title, "description": caption, "access_token": token},
                files={"source": f},
                timeout=300,
            )
        if res.status_code == 200:
            vid_id = res.json().get("id", "")
            return {
                "ok": True,
                "video_id": vid_id,
                "url": f"https://www.facebook.com/{page_id}/videos/{vid_id}" if vid_id else "",
                "message": "Publié sur Facebook !",
            }
        return {"ok": False, "message": f"Facebook {res.status_code}: {res.text[:220]}"}

    # ---------- Background Scheduler ----------

    @classmethod
    def start_scheduler(cls):
        if cls._scheduler_started:
            return
        cls._scheduler_started = True

        # Recover any interrupted 'publishing' items from a sudden server stop back to 'failed' with clear retry hint
        try:
            q = cls.load_queue()
            changed = False
            for item in q:
                if item.get("status") == "publishing":
                    item["status"] = "failed"
                    item["results"] = {"server": {"ok": False, "message": "Envoi interrompu par un redémarrage — clique sur Réessayer."}}
                    changed = True
            if changed:
                cls.save_queue(q)
        except Exception:
            pass

        def _loop():
            while True:
                try:
                    now = datetime.now()
                    queue = cls.load_queue()
                    for item in queue:
                        if item.get("status") == "scheduled" and item.get("scheduled_at"):
                            dt = _parse_scheduled_datetime(item["scheduled_at"])
                            if dt is not None and dt <= now:
                                try:
                                    cls.execute_post(item["id"])
                                except Exception as ex:
                                    print(f"⚠️ Scheduler post {item.get('id')} : {ex}")
                except Exception:
                    pass
                time.sleep(20)

        threading.Thread(target=_loop, daemon=True).start()
