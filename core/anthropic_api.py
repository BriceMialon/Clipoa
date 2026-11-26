"""
Claude via l'API officielle Anthropic, avec la clé API de l'utilisateur (« apporte ta clé »).

C'est la voie prévue par Anthropic pour les applications tierces (les abonnements Pro/Max ne doivent
pas être utilisés par une app pour le compte de ses utilisateurs). La clé est rangée chiffrée dans
storage/settings.json (champ `anthropic_api_key`, coffre core/vault.py), sinon lue dans ANTHROPIC_API_KEY.
"""

import base64
import json
import mimetypes
import os
from typing import Dict, Iterator, List, Optional

import requests

API_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
# alias de l'interface (opus / sonnet / haiku) → modèles de l'API ; surchargeable par ANTHROPIC_MODEL_<ALIAS>
MODEL_IDS = {
    "opus": os.getenv("ANTHROPIC_MODEL_OPUS", "claude-opus-5-5"),
    "sonnet": os.getenv("ANTHROPIC_MODEL_SONNET", "claude-sonnet-5-5"),
    "haiku": os.getenv("ANTHROPIC_MODEL_HAIKU", "claude-haiku-5-5"),
}
DEFAULT_ALIAS = "sonnet"
MAX_TOKENS = 16000


class AnthropicApiError(RuntimeError):
    pass


def get_api_key() -> str:
    try:
        from core.settings_store import load_settings
        key = str(load_settings().get("anthropic_api_key") or "").strip()
        if key and not key.startswith("enc:"):
            return key
    except Exception:
        pass
    return os.getenv("ANTHROPIC_API_KEY", "").strip()


def has_api_key() -> bool:
    return bool(get_api_key())


def model_id(alias: Optional[str]) -> str:
    a = (alias or DEFAULT_ALIAS).strip().lower()
    if a.startswith("claude-"):
        return a
    return MODEL_IDS.get(a, MODEL_IDS[DEFAULT_ALIAS])


def _headers(key: str) -> Dict[str, str]:
    return {"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"}


def _error_text(res: requests.Response) -> str:
    try:
        err = (res.json() or {}).get("error") or {}
        msg = err.get("message") or res.text
    except Exception:
        msg = res.text
    if res.status_code == 401:
        return "clé API Anthropic refusée (vérifie qu'elle est complète et active)"
    if res.status_code == 402 or "credit balance" in str(msg).lower():
        return "crédit API Anthropic épuisé (recharge sur console.anthropic.com)"
    if res.status_code == 429:
        return "limite de débit de l'API Anthropic atteinte, réessaie dans une minute"
    return f"erreur API Anthropic {res.status_code} : {str(msg)[:200]}"


def test_key(key: str) -> Dict[str, object]:
    """Vérifie une clé sans consommer de tokens (liste des modèles)."""
    key = (key or "").strip()
    if not key.startswith("sk-ant-"):
        return {"ok": False, "error": "une clé API Anthropic commence par « sk-ant- »"}
    try:
        res = requests.get(f"{API_URL}/models", headers=_headers(key), timeout=15)
    except requests.RequestException as e:
        return {"ok": False, "error": f"connexion impossible à l'API Anthropic : {e}"}
    if res.status_code != 200:
        return {"ok": False, "error": _error_text(res)}
    return {"ok": True}


def _payload(messages: List[dict], system: Optional[str], alias: Optional[str], stream: bool = False) -> dict:
    p = {"model": model_id(alias), "max_tokens": MAX_TOKENS, "messages": messages}
    if system:
        p["system"] = system
    if stream:
        p["stream"] = True
    return p


def _usage(data: dict) -> Dict[str, int]:
    u = data.get("usage") or {}
    return {
        "input_tokens": int(u.get("input_tokens") or 0),
        "output_tokens": int(u.get("output_tokens") or 0),
        "cache_tokens": int(u.get("cache_creation_input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0),
    }


def complete(prompt: str, system: Optional[str] = None, alias: Optional[str] = None, timeout: int = 300):
    """Réponse complète. Renvoie (texte, usage)."""
    key = get_api_key()
    if not key:
        raise AnthropicApiError("aucune clé API Anthropic enregistrée")
    msgs = [{"role": "user", "content": prompt}]
    res = requests.post(f"{API_URL}/messages", headers=_headers(key), json=_payload(msgs, system, alias), timeout=timeout)
    if res.status_code != 200:
        raise AnthropicApiError(_error_text(res))
    data = res.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return text, _usage(data)


def complete_with_images(prompt: str, image_paths: List[str], alias: Optional[str] = None, timeout: int = 420):
    key = get_api_key()
    if not key:
        raise AnthropicApiError("aucune clé API Anthropic enregistrée")
    content: List[dict] = []
    for p in image_paths:
        mt = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        with open(p, "rb") as f:
            content.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(f.read()).decode("ascii")}})
    content.append({"type": "text", "text": prompt})
    res = requests.post(f"{API_URL}/messages", headers=_headers(key),
                        json=_payload([{"role": "user", "content": content}], None, alias), timeout=timeout)
    if res.status_code != 200:
        raise AnthropicApiError(_error_text(res))
    data = res.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"), _usage(data)


def stream(prompt: str, system: Optional[str] = None, alias: Optional[str] = None, timeout: int = 300,
           usage_out: Optional[dict] = None) -> Iterator[str]:
    """Texte au fil de l'eau (événements SSE de l'API). `usage_out` reçoit les tokens à la fin."""
    key = get_api_key()
    if not key:
        raise AnthropicApiError("aucune clé API Anthropic enregistrée")
    msgs = [{"role": "user", "content": prompt}]
    with requests.post(f"{API_URL}/messages", headers=_headers(key), json=_payload(msgs, system, alias, stream=True),
                       timeout=timeout, stream=True) as res:
        if res.status_code != 200:
            raise AnthropicApiError(_error_text(res))
        for raw in res.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data:"):
                continue
            try:
                ev = json.loads(raw[5:].strip())
            except ValueError:
                continue
            et = ev.get("type")
            if et == "content_block_delta":
                txt = (ev.get("delta") or {}).get("text") or ""
                if txt:
                    yield txt
            elif et == "message_start" and usage_out is not None:
                usage_out.update(_usage(ev.get("message") or {}))
            elif et == "message_delta" and usage_out is not None:
                usage_out["output_tokens"] = int(((ev.get("usage") or {}).get("output_tokens")) or 0)
            elif et == "error":
                raise AnthropicApiError(str((ev.get("error") or {}).get("message") or "erreur de l'API Anthropic"))
