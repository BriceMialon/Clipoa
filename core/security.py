"""
Clipoa Security, Guardrails & Resource Hygiene Module.

Centralizes:
- SSRF-safe public HTTP(S) URL validation (blocks private/loopback/link-local IPs & flag injection)
- Safe local media path confinement (prevents arbitrary local file read/path traversal)
- OAuth relay URL validation (HTTPS required for remote relays)
- Browser cookie allowlist for yt-dlp
- Bounded sliding-window rate limiter (prevents memory exhaustion)
- Heavy job concurrency guard (prevents CPU/RAM freeze from simultaneous FFmpeg/Whisper/AI jobs)
- Sensitive file permission hardening (0600 on tokens/secrets)
- Temporary storage cleanup & disk health reporting
"""

import ipaddress
import logging
import os
import re
import secrets
import shutil
import socket
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

ALLOWED_COOKIE_BROWSERS = frozenset({
    "chrome",
    "safari",
    "firefox",
    "edge",
    "brave",
    "chromium",
    "opera",
    "vivaldi",
})

ALLOWED_MEDIA_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg",
    ".jpg", ".jpeg", ".png", ".webp",
})


def _is_private_or_reserved_ip(ip_str: str) -> bool:
    ip_obj = ipaddress.ip_address(ip_str)
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def _is_private_ip_literal(host: str) -> bool:
    try:
        return _is_private_or_reserved_ip(host)
    except ValueError:
        return False


def validate_public_http_url(raw_url: str, resolve_dns: bool = False) -> str:
    """
    Validates that `raw_url` is a clean public HTTP(S) URL:
    - Rejects empty strings, whitespace control chars, and leading '-' (CLI flag injection)
    - Requires http:// or https:// scheme
    - Rejects localhost, 127.0.0.1, private RFC1918/link-local/metadata IPs
    - Optionally resolves DNS to block DNS-rebinding to internal IPs
    """
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("URL manquante.")
    if len(url) > 2048:
        raise ValueError("URL trop longue (max 2048 caractères).")
    if url.startswith("-"):
        raise ValueError("URL invalide.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError("Caractères de contrôle interdits dans l'URL.")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Seules les URLs http:// et https:// sont autorisées.")
    if not parsed.hostname:
        raise ValueError("Nom d'hôte manquant dans l'URL.")
    if parsed.username or parsed.password:
        raise ValueError("Identifiants intégrés dans l'URL interdits.")

    host = parsed.hostname.lower().rstrip(".")
    if host in ("localhost", "ip6-localhost", "metadata.google.internal") or host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Accès aux adresses locales/internes bloqué (protection SSRF).")

    # Direct IP literal check
    if _is_private_ip_literal(host):
        raise ValueError("Accès aux adresses IP privées/locales bloqué (protection SSRF).")

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
            for info in infos:
                addr = info[4][0]
                if _is_private_or_reserved_ip(addr):
                    raise ValueError("Résolution DNS vers une adresse IP privée bloquée (protection SSRF).")
        except socket.gaierror:
            # Let downstream caller handle unreachable hostnames cleanly
            pass

    return url


def validate_relay_url(raw_url: str) -> str:
    """
    Validates an OAuth relay base URL.
    Remote relays MUST use https:// so OAuth refresh tokens are never sent in cleartext.
    Local dev relays (localhost / 127.0.0.1) may use http://.
    """
    url = (raw_url or "").strip().rstrip("/")
    if not url:
        return ""
    if len(url) > 512 or any(ord(ch) < 32 for ch in url):
        raise ValueError("URL du relais OAuth invalide.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or parsed.username or parsed.password:
        raise ValueError("URL du relais OAuth invalide.")
    if parsed.scheme == "https":
        if host in ("localhost", "127.0.0.1") or not _is_private_ip_literal(host):
            return url
        raise ValueError("Le relais OAuth ne peut pas pointer vers une IP privée.")
    if parsed.scheme == "http" and host in ("localhost", "127.0.0.1"):
        return url
    raise ValueError("Le relais OAuth distant doit obligatoirement utiliser HTTPS.")


def validate_cookie_browser(browser: Optional[str]) -> Optional[str]:
    """Strict allowlist for yt-dlp --cookies-from-browser to prevent argument abuse."""
    if not browser:
        return None
    cleaned = str(browser).strip().lower()
    if not cleaned:
        return None
    if cleaned not in ALLOWED_COOKIE_BROWSERS:
        raise ValueError(f"Navigateur de cookies non autorisé : {cleaned}")
    return cleaned


def validate_local_media_path(raw_path: str, allowed_roots: Iterable[Path]) -> Path:
    """
    Ensures a local file path resolves strictly inside one of `allowed_roots`
    and has a safe media extension. Prevents arbitrary local file read / path traversal.
    """
    if not raw_path or not str(raw_path).strip():
        raise ValueError("Chemin de fichier manquant.")
    p = Path(str(raw_path).strip()).expanduser().resolve()
    roots = [Path(r).resolve() for r in allowed_roots]
    inside = False
    for root in roots:
        try:
            p.relative_to(root)
            inside = True
            break
        except ValueError:
            continue
    if not inside:
        raise ValueError("Accès refusé : le fichier doit se trouver dans le dossier de stockage Clipoa.")
    if not p.exists() or not p.is_file():
        raise ValueError("Fichier média local introuvable.")
    if p.suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
        raise ValueError(f"Extension de fichier non autorisée : {p.suffix}")
    return p


class BoundedRateLimiter:
    """
    Thread-safe sliding-window rate limiter with bounded memory so a DDoS from
    thousands of random IPs cannot cause unbounded RAM growth.
    """

    def __init__(self, max_buckets: int = 2000):
        self._lock = threading.Lock()
        self._buckets: Dict[str, deque] = defaultdict(deque)
        self._max_buckets = max(100, int(max_buckets))
        self._last_prune = time.time()

    def allow(self, key: str, max_hits: int, window_sec: int) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.time()
        cutoff = now - window_sec
        with self._lock:
            # Periodic pruning if bucket count grows large
            if len(self._buckets) > self._max_buckets or (now - self._last_prune > 300):
                stale_keys = [k for k, dq in self._buckets.items() if not dq or dq[-1] < now - 300]
                for k in stale_keys:
                    del self._buckets[k]
                # Hard eviction if still over max_buckets
                while len(self._buckets) > self._max_buckets:
                    oldest_key = next(iter(self._buckets))
                    del self._buckets[oldest_key]
                self._last_prune = now

            dq = self._buckets[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_hits:
                retry_after = max(1, int(window_sec - (now - dq[0])) + 1)
                return False, retry_after
            dq.append(now)
            return True, 0

    def reset(self):
        with self._lock:
            self._buckets.clear()


class JobConcurrencyGuard:
    """
    Prevents spawning too many simultaneous heavy jobs (FFmpeg / Whisper / AI)
    which could freeze the user's PC or trigger API burst bans.
    """

    def __init__(self, max_concurrent: int = 2, max_queued: int = 6):
        self.max_concurrent = max(1, int(max_concurrent))
        self.max_queued = max(self.max_concurrent, int(max_queued))
        self._sem = threading.Semaphore(self.max_concurrent)
        self._lock = threading.Lock()
        self._inflight = 0
        self._running = 0

    def try_reserve(self) -> bool:
        with self._lock:
            if self._inflight >= self.max_queued:
                return False
            self._inflight += 1
            return True

    def acquire_slot(self):
        self._sem.acquire()
        with self._lock:
            self._running += 1

    def release_slot(self):
        with self._lock:
            self._running = max(0, self._running - 1)
            self._inflight = max(0, self._inflight - 1)
        self._sem.release()

    def cancel_reservation(self):
        with self._lock:
            self._inflight = max(0, self._inflight - 1)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "running": self._running,
                "queued": max(0, self._inflight - self._running),
                "inflight": self._inflight,
                "max_concurrent": self.max_concurrent,
                "max_queued": self.max_queued,
            }


def harden_sensitive_files(storage_dir: Path) -> Dict[str, str]:
    """
    Enforces strict POSIX permissions:
    - 0o700 on storage_dir
    - 0o600 on sensitive JSON files (tokens, OAuth secrets, settings, usage)
    """
    results: Dict[str, str] = {}
    try:
        if storage_dir.exists():
            os.chmod(storage_dir, 0o700)
    except OSError:
        pass

    sensitive_files = (
        "settings.json",
        "social_accounts.json",
        "oauth_apps.json",
        "claude_usage.json",
        "gemini_usage.json",
        "jobs_history.json",
        "publish_queue.json",
    )
    for fname in sensitive_files:
        fpath = storage_dir / fname
        if fpath.exists():
            try:
                os.chmod(fpath, 0o600)
                results[fname] = "0600"
            except OSError as exc:
                results[fname] = f"error:{exc}"
    return results


def cleanup_temp_storage(
    downloads_dir: Path,
    audio_dir: Path,
    max_age_days: int = 7,
) -> Dict[str, object]:
    """
    Removes expired temporary download/audio folders older than `max_age_days`
    to prevent Clipoa from silently filling the user's hard drive.
    Never touches finished renders in storage/renders.
    """
    cutoff = time.time() - max(1, int(max_age_days)) * 86400
    removed_items = 0
    reclaimed_bytes = 0

    for root in (downloads_dir, audio_dir):
        if not root.exists():
            continue
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            try:
                st = entry.stat()
                if st.st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    size = st.st_size
                    entry.unlink(missing_ok=True)
                removed_items += 1
                reclaimed_bytes += size
            except OSError:
                continue

    return {
        "removed_items": removed_items,
        "reclaimed_mb": round(reclaimed_bytes / (1024 * 1024), 2),
        "max_age_days": max(1, int(max_age_days)),
    }


def get_storage_health(storage_dir: Path) -> Dict[str, object]:
    """Returns disk free space and Clipoa storage breakdown (in MB)."""
    def _dir_size_mb(p: Path) -> float:
        if not p.exists():
            return 0.0
        total = 0
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
        return round(total / (1024 * 1024), 1)

    usage = shutil.disk_usage(str(storage_dir if storage_dir.exists() else Path.home()))
    free_gb = round(usage.free / (1024 ** 3), 2)
    return {
        "disk_free_gb": free_gb,
        "low_disk_warning": free_gb < 2.0,
        "renders_mb": _dir_size_mb(storage_dir / "renders"),
        "downloads_mb": _dir_size_mb(storage_dir / "downloads"),
        "audio_mb": _dir_size_mb(storage_dir / "audio"),
        "videos_mb": _dir_size_mb(storage_dir / "videos"),
    }


def generate_lan_token() -> str:
    return secrets.token_urlsafe(24)


# ---------- Privacy & Anti-Leak Redaction (Tokens, Proxies, IPs, Home Paths) ----------

_REDACT_PATTERNS = (
    # Proxy / URL credentials: http://user:pass@host:port -> http://***:***@host:port
    (re.compile(r"(https?|socks5h?|socks4)://([^/\s:@]+):([^/\s@]+)@", re.IGNORECASE), r"\1://***:***@"),
    # Authorization Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-~+/=]{8,}", re.IGNORECASE), r"\1[REDACTED]"),
    # Query / JSON key=value secrets
    (
        re.compile(
            r'((?:access_token|refresh_token|client_secret|api_key|authorization|proxy_password|password|token)["\']?\s*[:=]\s*["\']?)([A-Za-z0-9._\-~+/=]{8,})',
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # Well-known API / OAuth token prefixes (Anthropic, OpenAI, Google API, Google OAuth)
    (re.compile(r"\b(?:sk-ant-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|ya29\.[0-9A-Za-z._-]{20,})\b"), "[REDACTED_KEY]"),
    # User home directories (/Users/name/ or /home/name/ or C:\Users\name\)
    (re.compile(r"(/Users/|/home/)[^/\s\"']+", re.IGNORECASE), r"\1[USER]"),
    (re.compile(r"([A-Za-z]:\\Users\\)[^\\\s\"']+", re.IGNORECASE), r"\1[USER]"),
)

_IPV4_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")


def redact_sensitive_text(text: str, mask_ips: bool = True) -> str:
    """Scrubs OAuth tokens, API keys, proxy credentials, home paths, and non-loopback IPs from logs/errors."""
    if not text:
        return text
    out = str(text)
    for pattern, repl in _REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    if mask_ips:
        def _mask_ip(m):
            ip = m.group(0)
            if ip in ("127.0.0.1", "0.0.0.0"):
                return ip
            return f"{m.group(1)}.{m.group(2)}.***.***"
        out = _IPV4_RE.sub(_mask_ip, out)
    return out


class RedactingLogFilter(logging.Filter):
    """Logging filter that ensures secrets, proxy credentials, and client IPs never reach log files."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = redact_sensitive_text(msg, mask_ips=True)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


def is_allowed_host_header(host_header: str, allow_lan: bool = False, lan_ip: str = "") -> bool:
    """
    Blocks DNS Rebinding attacks against localhost:8080.
    Only accepts localhost, 127.0.0.1, [::1] (and the host's LAN IP when allow_lan is True).
    """
    raw = (host_header or "").strip().lower()
    if not raw:
        return True
    if raw.startswith("["):
        host = raw.split("]", 1)[0] + "]"
    else:
        host = raw.split(":", 1)[0]
    allowed = {"localhost", "127.0.0.1", "[::1]", "::1"}
    if allow_lan and lan_ip:
        allowed.add(lan_ip.strip().lower())
    return host in allowed

