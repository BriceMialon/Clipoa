"""
Licence d'abonnement Clipoa (version publique).

Principe :
- l'utilisateur colle sa clé `CLIPOA-XXXX-XXXX-XXXX` reçue après le paiement Stripe ;
- le Worker Cloudflare `clipoa-license` vérifie l'abonnement et renvoie un jeton signé
  (Ed25519) lié à cet appareil, valable quelques jours ;
- l'app vérifie la signature elle-même : elle fonctionne hors ligne jusqu'à l'expiration
  du jeton et le renouvelle sans bruit dès qu'elle est en ligne ;
- sans jeton valide, la fabrication est coupée (lecture seule : rien n'est supprimé).

Format du jeton : base64url(JSON) + "." + base64url(signature Ed25519 du JSON brut).
La clé publique est embarquée (CLIPOA_LICENSE_PUBKEY pour la surcharger en test).
Édition « perso » : la licence n'est pas exigée.
"""

import base64
import hashlib
import json
import os
import platform
import re
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, Optional

from core import edition as _edition

DEFAULT_LICENSE_SERVER = "https://clipoa-license.clipoa-studio.workers.dev"
# Clé publique Ed25519 du serveur de licence (hex, 32 octets). Vide tant que le Worker
# n'est pas déployé : aucune licence ne peut alors être validée en édition publique.
DEFAULT_PUBKEY_HEX = ""

KEY_RE = re.compile(r"^CLIPOA(-[A-Z0-9]{4}){3,4}$")
# Routes de fabrication (POST) réservées aux abonnés en édition publique.
LICENSED_PREFIXES = ("/api/make", "/api/fabrique/")
REFRESH_AFTER_S = 12 * 3600  # renouvellement en ligne au plus toutes les 12 h


# ---------------------------------------------------------------------------
# Vérification Ed25519 (RFC 8032), Python pur : une vérification par lancement,
# pas besoin d'une dépendance compilée.
# ---------------------------------------------------------------------------
_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y: int) -> Optional[int]:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = x * _I % _P
    if (x * x - xx) % _P != 0:
        return None
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
if _BX & 1:
    _BX = _P - _BX
_B = (_BX, _BY, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, p):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _eq(p, q) -> bool:
    x1, y1, z1, _ = p
    x2, y2, z2, _ = q
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _decode_point(b: bytes):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        return None
    x = _xrecover(y)
    if x is None or (x == 0 and sign):
        return None
    if x & 1 != sign:
        x = _P - x
    return (x, y, 1, x * y % _P)


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        if len(signature) != 64:
            return False
        a = _decode_point(public_key)
        r = _decode_point(signature[:32])
        s = int.from_bytes(signature[32:], "little")
        if a is None or r is None or s >= _L:
            return False
        h = int.from_bytes(hashlib.sha512(signature[:32] + public_key + message).digest(), "little") % _L
        return _eq(_mul(s, _B), _add(r, _mul(h, a)))
    except Exception:
        return False


# ---------------------------------------------------------------------------
def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def normalize_key(raw: str) -> str:
    k = re.sub(r"\s+", "", str(raw or "")).upper()
    return k if KEY_RE.match(k) else ""


def _platform_uuid() -> str:
    """Identifiant matériel stable (jamais envoyé en clair : il est haché)."""
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=5).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            return m.group(1) if m else ""
        if sysname == "Windows":
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(p):
                with open(p) as f:
                    return f.read().strip()
    except Exception:
        pass
    return ""


def verify_token(token: str, pubkey_hex: str, device: str, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Renvoie le contenu du jeton s'il est signé, lié à cet appareil et non expiré."""
    try:
        body_b64, sig_b64 = str(token or "").split(".", 1)
        body = _b64d(body_b64)
        if not pubkey_hex or not ed25519_verify(bytes.fromhex(pubkey_hex), body, _b64d(sig_b64)):
            return None
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    now = time.time() if now is None else now
    if data.get("dev") != device or float(data.get("exp", 0)) <= now:
        return None
    if data.get("status") not in ("active", "trialing", "past_due"):
        return None
    return data


class LicenseManager:
    def __init__(self, storage_dir: str, server_url: str = None, pubkey_hex: str = None):
        self.path = os.path.join(storage_dir, "license.json")
        self.server = (server_url or os.getenv("CLIPOA_LICENSE_URL") or DEFAULT_LICENSE_SERVER).rstrip("/")
        self.pubkey = (pubkey_hex if pubkey_hex is not None else os.getenv("CLIPOA_LICENSE_PUBKEY", DEFAULT_PUBKEY_HEX)).strip()
        self._lock = threading.RLock()

    # -- stockage local -------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def device_id(self) -> str:
        if getattr(self, "_dev", None):
            return self._dev
        with self._lock:
            data = self._load()
            if not data.get("install_id"):
                data["install_id"] = uuid.uuid4().hex
                self._save(data)
        raw = (_platform_uuid() or data["install_id"]) + "|clipoa"
        self._dev = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return self._dev

    # -- état -------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        if not _edition.is_public():
            return {"required": False, "valid": True, "state": "perso"}
        data = self._load()
        payload = verify_token(data.get("token", ""), self.pubkey, self.device_id())
        if not data.get("key"):
            state = "none"
        elif payload:
            state = payload.get("status", "active")
        else:
            state = "expired"
        out = {"required": True, "valid": bool(payload), "state": state,
               "key_hint": (data.get("key") or "")[-4:]}
        if payload:
            out.update({"plan": payload.get("plan"), "expires_at": payload.get("exp"),
                        "period_end": payload.get("period_end")})
        return out

    def can_fabricate(self) -> bool:
        return bool(self.status().get("valid"))

    # -- réseau -----------------------------------------------------------------
    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        import requests
        r = requests.post(self.server + path, json=body, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code >= 400:
            raise RuntimeError(data.get("error") or f"Serveur de licence : HTTP {r.status_code}")
        return data

    def activate(self, raw_key: str) -> Dict[str, Any]:
        key = normalize_key(raw_key)
        if not key:
            raise ValueError("Clé invalide (format attendu : CLIPOA-XXXX-XXXX-XXXX).")
        dev = self.device_id()
        resp = self._post("/license/activate", {"key": key, "device": dev,
                                                  "device_name": platform.node()[:60]})
        token = resp.get("token", "")
        if not verify_token(token, self.pubkey, dev):
            raise RuntimeError("Réponse du serveur de licence non valide.")
        with self._lock:
            data = self._load()
            data.update({"key": key, "token": token, "checked_at": time.time()})
            self._save(data)
        return self.status()

    def refresh(self, force: bool = False) -> Dict[str, Any]:
        """Renouvelle le jeton en ligne ; hors ligne, garde l'ancien jusqu'à son expiration."""
        data = self._load()
        if not _edition.is_public() or not data.get("key"):
            return self.status()
        if not force and time.time() - float(data.get("checked_at", 0)) < REFRESH_AFTER_S:
            return self.status()
        try:
            dev = self.device_id()
            resp = self._post("/license/refresh", {"key": data["key"], "device": dev})
            token = resp.get("token", "")
            with self._lock:
                data = self._load()
                data["checked_at"] = time.time()
                if verify_token(token, self.pubkey, dev):
                    data["token"] = token
                elif resp.get("revoked"):
                    data["token"] = ""  # abonnement terminé : lecture seule
                self._save(data)
        except Exception:
            pass  # hors ligne : le jeton en cache reste valable jusqu'à son expiration
        return self.status()

    def deactivate(self) -> Dict[str, Any]:
        """Libère cet appareil (pour activer la licence sur un autre)."""
        data = self._load()
        if data.get("key"):
            try:
                self._post("/license/deactivate", {"key": data["key"], "device": self.device_id()})
            except Exception:
                pass
        with self._lock:
            data = self._load()
            for k in ("key", "token", "checked_at"):
                data.pop(k, None)
            self._save(data)
        return self.status()

    def auth_header(self) -> Dict[str, str]:
        """En-tête à joindre aux appels du relais OAuth (réservé aux abonnés)."""
        tok = self._load().get("token", "")
        return {"X-Clipoa-License": tok} if tok else {}
