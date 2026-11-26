"""
Comptes ElevenLabs mémorisés : on branche une clé une fois, puis on change de compte en un clic.

ElevenLabs ne propose pas de connexion OAuth pour les apps tierces (doc officielle :
« To link your ElevenLabs account with an external service, you will need to use your API key »).
Le parcours guidé ouvre donc la page des clés et récupère la clé copiée ; ici on garde chaque clé
validée dans settings.json (champ `api_key`, chiffré par core/vault.py), jamais effacée au changement.
"""

import hashlib
from typing import Any, Dict, List

from core.settings_store import load_settings, save_settings
from core.voice_engine import VoiceEngine


def account_id(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()[:12]


def _label(key: str, status: Dict[str, Any]) -> str:
    tier = str(status.get("tier") or "").replace("_", " ")
    tier = "" if tier in ("restricted key",) else tier
    return ("Compte " + tier + " " if tier else "Compte ") + "···" + key.strip()[-4:]


def remember(key: str, status: Dict[str, Any]) -> str:
    """Mémorise une clé déjà validée par VoiceEngine.connect_elevenlabs."""
    key = key.strip()
    aid = account_id(key)
    save_settings({"elevenlabs": {"saved_accounts": {aid: {"api_key": key, "label": _label(key, status)}}}})
    return aid


def _saved() -> Dict[str, Dict[str, Any]]:
    raw = (load_settings().get("elevenlabs") or {}).get("saved_accounts")
    return {k: v for k, v in (raw or {}).items() if isinstance(v, dict) and v.get("api_key")}


def list_accounts() -> List[Dict[str, Any]]:
    """Comptes connus (sans les clés). La clé active d'avant cette fonction apparaît aussi."""
    current = VoiceEngine.get_elevenlabs_key()
    cur_id = account_id(current) if current else ""
    saved = _saved()
    out = [{"id": aid, "label": str(v.get("label") or "Compte ElevenLabs"), "active": aid == cur_id}
           for aid, v in saved.items()]
    if current and cur_id not in saved:
        out.insert(0, {"id": cur_id, "label": "Compte actuel ···" + current[-4:], "active": True})
    return out


def switch(aid: str) -> Dict[str, Any]:
    current = VoiceEngine.get_elevenlabs_key()
    if current and account_id(current) == aid:
        return VoiceEngine.get_elevenlabs_status()
    acc = _saved().get(aid)
    if not acc:
        raise ValueError("Compte introuvable.")
    # garde l'ancien compte pour pouvoir y revenir
    if current and account_id(current) not in _saved():
        remember(current, {})
    res = VoiceEngine.connect_elevenlabs(api_key=acc["api_key"], enabled=True)
    if not res.get("connected"):
        raise ValueError(res.get("message") or "Ce compte ne répond plus : reconnecte-le.")
    return res
