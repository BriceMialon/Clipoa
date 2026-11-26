"""
Rapports de plantage et contact support.

Principe :
  - Capture automatique, mais LOCALE : erreurs non rattrapées (serveur, threads), étapes de
    fabrication en échec, et les dernières lignes de la console gardées en mémoire.
    Rien ne quitte l'ordinateur tant que l'utilisateur n'a pas cliqué « Envoyer ».
  - Au clic, le rapport est construit puis nettoyé : clés API (Claude, ElevenLabs…), jetons
    OAuth, mots de passe, cookies, e-mails, adresses IP et nom d'utilisateur (chemins) sont
    masqués. Les valeurs exactes des secrets présents dans storage/*.json sont aussi
    retirées mot pour mot, quel que soit leur format.
  - L'utilisateur peut voir exactement le contenu avant l'envoi (/api/support/preview).
  - Envoi au relais Cloudflare de Clipoa (route /support/report). En cas d'échec, le rapport
    reste dans storage/support/outbox/ et l'interface propose de le télécharger.
"""

import json
import logging
import os
import platform
import re
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BASE_DIR, STORAGE_DIR
from core.security import redact_sensitive_text

SUPPORT_DIR = STORAGE_DIR / "support"
INCIDENTS_FILE = SUPPORT_DIR / "incidents.json"
OUTBOX_DIR = SUPPORT_DIR / "outbox"

MAX_INCIDENTS = 20
MAX_LOG_LINES = 400
MAX_MESSAGE_CHARS = 4000
MAX_FIELD_CHARS = 8000
DEDUP_WINDOW_S = 60
SEND_TIMEOUT_S = 15

_LOCK = threading.Lock()
_LOG_RING: "deque[str]" = deque(maxlen=MAX_LOG_LINES)
_INSTALLED = {"done": False}

_SECRET_KEY_RE = re.compile(r"(key|token|secret|password|passwd|cookie|proxy|auth|session_?id|credential|license)", re.I)
_EXTRA_PATTERNS = (
    # ElevenLabs (sk_…), Stripe (sk_live_/rk_…/whsec_), GitHub, Slack, JWT
    (re.compile(r"\b(?:sk|rk|pk)_(?:live_|test_)?[A-Za-z0-9]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    # Cookie / Set-Cookie headers
    (re.compile(r"((?:set-)?cookie\s*[:=]\s*)[^\n]+", re.I), r"\1[REDACTED]"),
    # E-mails
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # Longs jetons opaques (40+ caractères sans espace) : hachés, refresh tokens, etc.
    (re.compile(r"(?<![A-Za-z0-9/._-])[A-Za-z0-9_\-+=]{40,}(?![A-Za-z0-9/._-])"), "[REDACTED_TOKEN]"),
)


# ---------------------------------------------------------------- capture console

class _Tee:
    """Recopie stdout/stderr dans un anneau mémoire (les print() et tracebacks)."""

    def __init__(self, stream):
        self._stream = stream
        self._buf = ""

    def write(self, data):
        try:
            self._buf += str(data)
            if "\n" in self._buf:
                lines = self._buf.split("\n")
                self._buf = lines.pop()
                stamp = time.strftime("%H:%M:%S")
                for line in lines:
                    if line.strip():
                        _LOG_RING.append(stamp + " " + line[:1000])
        except Exception:
            pass
        return self._stream.write(data)

    def flush(self):
        return self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


class _RingHandler(logging.Handler):
    def emit(self, record):
        try:
            _LOG_RING.append(time.strftime("%H:%M:%S") + " " + record.levelname + " " + self.format(record)[:1000])
        except Exception:
            pass


def recent_logs(n: int = MAX_LOG_LINES) -> List[str]:
    return list(_LOG_RING)[-n:]


# ---------------------------------------------------------------- incidents

def _read_incidents() -> List[Dict[str, Any]]:
    try:
        data = json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_incidents(items: List[Dict[str, Any]]) -> None:
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INCIDENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-MAX_INCIDENTS:], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, INCIDENTS_FILE)


def record_incident(source: str, message: str, step: str = "", job_kind: str = "",
                    job_id: str = "", tb: str = "") -> str:
    """Note une erreur localement (rien n'est envoyé). Renvoie l'identifiant de l'incident."""
    message = str(message or "Erreur inconnue")[:MAX_FIELD_CHARS]
    now = time.time()
    with _LOCK:
        items = _read_incidents()
        for it in reversed(items):
            if it.get("message") == message and it.get("source") == source and now - it.get("at", 0) < DEDUP_WINDOW_S:
                it["count"] = int(it.get("count", 1)) + 1
                if job_id and not it.get("job_id"):
                    it["job_id"] = job_id
                _write_incidents(items)
                return it["id"]
        inc = {
            "id": "inc_" + uuid.uuid4().hex[:10],
            "source": source,
            "message": message,
            "step": str(step or "")[:500],
            "job_kind": str(job_kind or "")[:40],
            "job_id": str(job_id or "")[:40],
            "traceback": str(tb or "")[-MAX_FIELD_CHARS:],
            "logs": recent_logs(150),
            "at": now,
            "count": 1,
            "sent": False,
            "dismissed": False,
        }
        items.append(inc)
        _write_incidents(items)
        return inc["id"]


def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    for it in _read_incidents():
        if it.get("id") == incident_id:
            return it
    return None


def _mark(incident_id: str, **fields) -> None:
    with _LOCK:
        items = _read_incidents()
        for it in items:
            if it.get("id") == incident_id:
                it.update(fields)
        _write_incidents(items)


def pending_incidents() -> List[Dict[str, Any]]:
    """Incidents ni envoyés ni ignorés (version courte, déjà nettoyée, pour l'interface)."""
    out = []
    for it in _read_incidents():
        if it.get("sent") or it.get("dismissed"):
            continue
        out.append({
            "id": it["id"],
            "source": it.get("source"),
            "message": redact_sensitive_text(it.get("message", ""))[:300],
            "step": it.get("step", ""),
            "job_id": it.get("job_id", ""),
            "at": it.get("at"),
            "count": it.get("count", 1),
        })
    return out


# ---------------------------------------------------------------- nettoyage

def _walk_secrets(obj: Any, key: str, out: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk_secrets(v, str(k), out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_secrets(v, key, out)
    elif isinstance(obj, str) and len(obj) >= 8 and _SECRET_KEY_RE.search(key or ""):
        out.add(obj)


def known_secrets(storage_dir: Optional[Path] = None) -> List[str]:
    """Valeurs exactes des secrets stockés (déchiffrées) + variables d'environnement sensibles."""
    found: set = set()
    sdir = Path(storage_dir or STORAGE_DIR)
    try:
        from core.vault import decrypt_sensitive_fields
    except Exception:  # pragma: no cover
        decrypt_sensitive_fields = None
    try:
        files = list(sdir.glob("*.json"))
    except Exception:
        files = []
    for f in files:
        try:
            if f.stat().st_size > 2_000_000:
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            if decrypt_sensitive_fields:
                try:
                    data = decrypt_sensitive_fields(data)
                except Exception:
                    pass
            _walk_secrets(data, "", found)
        except Exception:
            continue
    for k, v in os.environ.items():
        if v and len(v) >= 8 and _SECRET_KEY_RE.search(k):
            found.add(v)
    # les plus longs d'abord (une valeur peut en contenir une autre)
    return sorted(found, key=len, reverse=True)


def scrub(text: Any, secrets: Optional[List[str]] = None) -> str:
    if text is None:
        return ""
    out = str(text)
    for s in secrets or []:
        if s and s in out:
            out = out.replace(s, "[REDACTED_SECRET]")
    out = redact_sensitive_text(out, mask_ips=True)
    for pattern, repl in _EXTRA_PATTERNS:
        out = pattern.sub(repl, out)
    return out


# ---------------------------------------------------------------- rapport

def app_version() -> str:
    try:
        rel = json.loads((Path(BASE_DIR) / "release.json").read_text(encoding="utf-8"))
        if rel.get("version"):
            return str(rel["version"])
    except Exception:
        pass
    try:
        head = (Path(BASE_DIR) / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = Path(BASE_DIR) / ".git" / head.split(" ", 1)[1].strip()
            head = ref.read_text(encoding="utf-8").strip() if ref.exists() else ""
        return "dev-" + head[:7] if head else "dev"
    except Exception:
        return "dev"


def _system_info() -> Dict[str, Any]:
    try:
        from core import edition as _edition
        edition = _edition.EDITION
    except Exception:
        edition = "?"
    mac = platform.mac_ver()[0]
    return {
        "version": app_version(),
        "edition": edition,
        "os": ("macOS " + mac) if mac else (platform.system() + " " + platform.release()),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "locale": os.environ.get("LANG", ""),
    }


def build_report(kind: str = "crash", incident_id: str = "", message: str = "",
                 contact_email: str = "", include_logs: bool = True,
                 page: str = "") -> Dict[str, Any]:
    """Construit le rapport EXACT qui sera envoyé (déjà nettoyé)."""
    kind = "contact" if kind == "contact" else "crash"
    secrets = known_secrets()
    inc = get_incident(incident_id) if incident_id else None
    report: Dict[str, Any] = {
        "schema": 1,
        "kind": kind,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app": _system_info(),
        "message": scrub(str(message or "")[:MAX_MESSAGE_CHARS], secrets),
        "page": scrub(str(page or "")[:200], secrets),
    }
    # l'adresse de contact est donnée volontairement par l'utilisateur : non masquée, mais validée
    email = str(contact_email or "").strip()[:200]
    if email and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        report["contact_email"] = email
    if inc:
        report["incident"] = {
            "id": inc.get("id"),
            "source": inc.get("source"),
            "step": scrub(inc.get("step", ""), secrets),
            "job_kind": inc.get("job_kind", ""),
            "error": scrub(inc.get("message", ""), secrets),
            "traceback": scrub(inc.get("traceback", ""), secrets),
            "count": inc.get("count", 1),
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(inc.get("at") or time.time())),
        }
    if include_logs:
        lines = (inc or {}).get("logs") or recent_logs(150)
        report["logs"] = [scrub(line, secrets) for line in lines[-150:]]
    return report


def support_url() -> str:
    url = os.getenv("CLIPOA_SUPPORT_URL", "").strip().rstrip("/")
    if not url:
        try:
            from core.social_publisher import DEFAULT_OAUTH_RELAY_URL
            url = DEFAULT_OAUTH_RELAY_URL.rstrip("/") + "/support/report"
        except Exception:
            url = ""
    return url


def _save_outbox(report: Dict[str, Any]) -> Path:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTBOX_DIR / ("rapport_" + time.strftime("%Y%m%d_%H%M%S") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def send_report(report: Dict[str, Any], incident_id: str = "") -> Dict[str, Any]:
    url = support_url()
    if not url.startswith("https://"):
        path = _save_outbox(report)
        return {"ok": False, "error": "Adresse du support non configurée.", "saved": path.name}
    try:
        import requests
        r = requests.post(url, json=report, timeout=SEND_TIMEOUT_S,
                          headers={"User-Agent": "Clipoa/" + report.get("app", {}).get("version", "?")})
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("ok"):
            if incident_id:
                _mark(incident_id, sent=True)
            return {"ok": True, "report_id": data.get("id", "")}
        err = data.get("error") or ("HTTP " + str(r.status_code))
    except Exception as e:
        err = type(e).__name__
    path = _save_outbox(report)
    return {"ok": False, "error": "Envoi impossible (" + str(err)[:80] + ").", "saved": path.name}


# ---------------------------------------------------------------- branchement Flask

def _hook_exceptions() -> None:
    prev_hook = sys.excepthook

    def _excepthook(exc_type, exc, tb):
        try:
            if not issubclass(exc_type, KeyboardInterrupt):
                record_incident("crash", exc_type.__name__ + ": " + str(exc),
                                tb="".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass
        prev_hook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    if hasattr(threading, "excepthook"):
        prev_thread_hook = threading.excepthook

        def _thread_hook(args):
            try:
                if args.exc_type is not SystemExit:
                    record_incident("thread", args.exc_type.__name__ + ": " + str(args.exc_value),
                                    step=getattr(args.thread, "name", ""),
                                    tb="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
            except Exception:
                pass
            prev_thread_hook(args)

        threading.excepthook = _thread_hook


def install_capture() -> None:
    if _INSTALLED["done"]:
        return
    _INSTALLED["done"] = True
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout)
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr)
    handler = _RingHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    _hook_exceptions()


def register(app) -> None:
    from flask import jsonify, request
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def _unhandled(e):
        if isinstance(e, HTTPException):
            return e
        inc_id = record_incident("server", type(e).__name__ + ": " + str(e),
                                 step=request.method + " " + request.path,
                                 tb=traceback.format_exc())
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Erreur interne de Clipoa.", "incident_id": inc_id}), 500
        return "Erreur interne de Clipoa. Tu peux envoyer un rapport depuis le bouton Aide.", 500

    def _args():
        data = request.get_json(silent=True) or {}
        return {
            "kind": str(data.get("kind") or "crash"),
            "incident_id": str(data.get("incident_id") or ""),
            "message": str(data.get("message") or ""),
            "contact_email": str(data.get("contact_email") or ""),
            "include_logs": bool(data.get("include_logs", True)),
            "page": str(data.get("page") or ""),
        }

    @app.route("/api/support/incidents", methods=["GET"])
    def support_incidents():
        return jsonify({"ok": True, "incidents": pending_incidents()})

    @app.route("/api/support/preview", methods=["POST"])
    def support_preview():
        return jsonify({"ok": True, "report": build_report(**_args())})

    @app.route("/api/support/send", methods=["POST"])
    def support_send():
        a = _args()
        if a["kind"] == "contact" and not a["message"].strip():
            return jsonify({"ok": False, "error": "Écris ton message avant d'envoyer."}), 400
        report = build_report(**a)
        res = send_report(report, incident_id=a["incident_id"])
        if not res.get("ok"):
            res["report"] = report
        return jsonify(res), (200 if res.get("ok") else 502)

    @app.route("/api/support/dismiss", methods=["POST"])
    def support_dismiss():
        data = request.get_json(silent=True) or {}
        inc_id = str(data.get("incident_id") or "")
        if inc_id:
            _mark(inc_id, dismissed=True)
        return jsonify({"ok": True})
