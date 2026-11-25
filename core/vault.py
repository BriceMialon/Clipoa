"""
Clipoa Local Encrypted Vault (Zero-Dependency Authenticated Encryption).

Protects client secrets at rest (OAuth access_token / refresh_token, client_secret,
API keys, proxy credentials) so that even if `storage/*.json` is copied, synced,
or backed up, sensitive fields remain encrypted (`enc:v1:...`).

Design:
- Master 256-bit key stored outside the project/storage tree (`~/.clipoa/vault.key`, mode 0600)
  or overridden via `CLIPOA_VAULT_KEY` env var.
- Encrypt-then-MAC: SHA-256 CTR keystream + HMAC-SHA256 authentication tag with a
  fresh 16-byte random nonce per value.
- 100% backwards-compatible: legacy plaintext values are read seamlessly and
  automatically encrypted on the next save.
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any, FrozenSet

ENC_PREFIX = "enc:v1:"
_logger = logging.getLogger("ClipoaVault")

SENSITIVE_FIELD_NAMES: FrozenSet[str] = frozenset({
    "access_token",
    "refresh_token",
    "client_secret",
    "api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "elevenlabs_api_key",
    "kie_api_key",
    "postiz_api_key",
    "proxy_url",
    "proxy_password",
    "password",
    "secret",
})

_KEY_LOCK = threading.Lock()
_CACHED_KEY: bytes = b""


def _default_key_path() -> Path:
    custom = os.getenv("CLIPOA_VAULT_KEY_PATH", "").strip()
    if custom:
        return Path(custom).expanduser()
    return Path.home() / ".clipoa" / "vault.key"


def get_master_key() -> bytes:
    """Loads or generates the 32-byte local master key (never stored inside storage/)."""
    global _CACHED_KEY
    env_key = os.getenv("CLIPOA_VAULT_KEY", "").strip()
    if env_key:
        return hashlib.sha256(env_key.encode("utf-8")).digest()

    with _KEY_LOCK:
        if _CACHED_KEY:
            return _CACHED_KEY

        key_path = _default_key_path()
        if key_path.exists():
            raw = key_path.read_bytes().strip()
            if len(raw) >= 32:
                _CACHED_KEY = hashlib.sha256(raw).digest()
                try:
                    os.chmod(key_path, 0o600)
                except OSError:
                    pass
                return _CACHED_KEY

        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(key_path.parent, 0o700)
        except OSError:
            pass

        raw_secret = secrets.token_bytes(32)
        key_b64 = base64.urlsafe_b64encode(raw_secret)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, key_b64)
        finally:
            os.close(fd)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        _CACHED_KEY = hashlib.sha256(key_b64).digest()
        return _CACHED_KEY


def _derive_subkeys(master_key: bytes) -> tuple:
    enc_key = hmac.new(master_key, b"clipoa-vault-enc-v1", hashlib.sha256).digest()
    mac_key = hmac.new(master_key, b"clipoa-vault-mac-v1", hashlib.sha256).digest()
    return enc_key, mac_key


def _keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(enc_key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_secret(plaintext: str) -> str:
    """Encrypts a non-empty string into `enc:v1:<b64url>`. Idempotent if already encrypted."""
    if not isinstance(plaintext, str) or not plaintext:
        return plaintext
    if plaintext.startswith(ENC_PREFIX):
        return plaintext
    # Preserve non-secret UI sentinel tokens like "same_browser:tiktok"
    if plaintext.startswith("same_browser:"):
        return plaintext

    enc_key, mac_key = _derive_subkeys(get_master_key())
    nonce = secrets.token_bytes(16)
    pt_bytes = plaintext.encode("utf-8")
    ks = _keystream(enc_key, nonce, len(pt_bytes))
    ct_bytes = bytes(a ^ b for a, b in zip(pt_bytes, ks))
    tag = hmac.new(mac_key, b"v1" + nonce + ct_bytes, hashlib.sha256).digest()
    blob = base64.urlsafe_b64encode(nonce + ct_bytes + tag).decode("ascii").rstrip("=")
    return f"{ENC_PREFIX}{blob}"


def decrypt_secret(value: str) -> str:
    """Decrypts an `enc:v1:...` secret. Returns legacy plaintext untouched."""
    if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
        return value
    blob_b64 = value[len(ENC_PREFIX):]
    pad = "=" * ((4 - len(blob_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(blob_b64 + pad)
        if len(raw) < 16 + 32:
            return ""
        nonce = raw[:16]
        tag = raw[-32:]
        ct_bytes = raw[16:-32]
        enc_key, mac_key = _derive_subkeys(get_master_key())
        expected_tag = hmac.new(mac_key, b"v1" + nonce + ct_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            return ""
        ks = _keystream(enc_key, nonce, len(ct_bytes))
        pt_bytes = bytes(a ^ b for a, b in zip(ct_bytes, ks))
        return pt_bytes.decode("utf-8")
    except Exception:
        return ""


def encrypt_sensitive_fields(obj: Any) -> Any:
    """Returns a deep copy of `obj` with all sensitive string fields encrypted."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_FIELD_NAMES and isinstance(v, str) and v:
                out[k] = encrypt_secret(v)
            else:
                out[k] = encrypt_sensitive_fields(v)
        return out
    if isinstance(obj, list):
        return [encrypt_sensitive_fields(item) for item in obj]
    return obj


def decrypt_sensitive_fields(obj: Any) -> Any:
    """Returns a deep copy of `obj` with all encrypted sensitive fields decrypted."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_FIELD_NAMES and isinstance(v, str) and v.startswith(ENC_PREFIX):
                plain = decrypt_secret(v)
                if not plain:
                    # Clé du coffre différente (autre Mac, CLIPOA_VAULT_KEY changée) : on garde la valeur chiffrée
                    # telle quelle pour qu'une sauvegarde ne l'efface pas ; elle redevient lisible si la clé revient.
                    _logger.warning("Coffre : un secret (%s) ne se déchiffre pas avec la clé actuelle, il est conservé chiffré.", k)
                    plain = v
                out[k] = plain
            else:
                out[k] = decrypt_sensitive_fields(v)
        return out
    if isinstance(obj, list):
        return [decrypt_sensitive_fields(item) for item in obj]
    return obj
