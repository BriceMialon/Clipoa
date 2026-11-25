import os
import re
import json
import time
import uuid
import shutil
import socket
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import quote, urlparse
from flask import Flask, render_template, request, jsonify, send_file, Response, redirect
from werkzeug.utils import secure_filename

from config import (
    RENDERS_DIR,
    VIDEOS_DIR,
    AUDIO_DIR,
    DOWNLOADS_DIR,
    STORAGE_DIR,
    BASE_DIR,
    FFMPEG_PATH,
    DEFAULT_THEME,
    DEFAULT_SUBTITLE_STYLE,
    DEFAULT_TTS_VOICE,
    CLIPOA_HOST,
    CLIPOA_ALLOW_LAN,
    CLIPOA_ACCESS_TOKEN,
    CLIPOA_MAX_CONCURRENT_JOBS,
    CLIPOA_MAX_ACTIVE_JOBS,
    CLIPOA_TEMP_TTL_DAYS,
)
from core.security import (
    BoundedRateLimiter,
    JobConcurrencyGuard,
    ALLOWED_MEDIA_EXTENSIONS,
    RedactingLogFilter,
    validate_public_http_url,
    validate_local_media_path,
    harden_sensitive_files,
    cleanup_temp_storage,
    get_storage_health,
    generate_lan_token,
    redact_sensitive_text,
    is_allowed_host_header,
)
from core.scraper import CompetitorScraper
from core.pipeline import ShortCrewPipeline
from core.claude_bridge import ClaudeBridge, ClaudeQuotaExceededError
from core.voice_engine import VoiceEngine, GEMINI_VOICES
from core.video_composer import THEMES, SUBTITLE_STYLES
from core.drive_client import DriveClient
from core.style_plugins import (
    StylePluginStore,
    PLUGIN_GRADIENTS,
    PLUGIN_CATEGORIES,
    SCRIPT_LANGUAGES,
    SHEET_ROLES,
)
from core.gemini_studio import GeminiStudio, GEMINI_MODELS
from core.antigravity_bridge import AntigravityBridge
from core.script_template import (
    build_script_generation_prompt,
    build_script_refinement_prompt,
    extract_spoken_script_from_template,
    extract_title_from_template,
    extract_shots_from_template,
    list_script_templates,
    save_custom_script_template,
    delete_custom_script_template,
    recent_video_titles,
)
from core.timing_tracker import (
    get_learned_estimates,
    estimate_job_seconds,
    record_actual_timing,
)
from core.social_publisher import FreeSocialPublisher, PLATFORMS
from core.browser_auth import BrowserPortalAuth
from core.analytics_engine import AnalyticsEngine, PRESET_NICHES
from core.night_factory import NightFactory
from core.blender_engine import BlenderEngine
from core.settings_store import (
    load_settings,
    save_settings,
    CLAUDE_PLAN_BUDGETS,
    reset_claude_quota_counter,
    list_presets,
    save_custom_preset,
    delete_custom_preset,
)
from agents.team import LeStratege, LeCloneur
from agents.script_expert import ScriptExpertAgent
from core.transcriber import AudioTranscriber
from core.video_composer import VideoComposer
from core.quality_controller import QualityController

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
# Identifiant de cette version du serveur : un onglet resté ouvert sur une ancienne version le détecte
APP_BUILD = f"{int(time.time())}"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB max upload
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Install privacy redacting filter on Flask & root loggers (never log tokens, proxies, or client IPs)
import logging as _logging
_REDACT_FILTER = RedactingLogFilter()
_logging.getLogger().addFilter(_REDACT_FILTER)
app.logger.addFilter(_REDACT_FILTER)
_logging.getLogger("werkzeug").addFilter(_REDACT_FILTER)

# ---------- Security: Anti-Scraping, Rate Limiting, LAN Auth, Concurrency & Headers ----------

_RATE_LIMITER = BoundedRateLimiter(max_buckets=2000)
_RATE_LOCK = _RATE_LIMITER._lock
_RATE_BUCKETS = _RATE_LIMITER._buckets
JOB_GUARD = JobConcurrencyGuard(
    max_concurrent=CLIPOA_MAX_CONCURRENT_JOBS,
    max_queued=CLIPOA_MAX_ACTIVE_JOBS,
)
_LAN_ACCESS_TOKEN = CLIPOA_ACCESS_TOKEN or (generate_lan_token() if CLIPOA_ALLOW_LAN else "")
_LAN_COOKIE_NAME = "clipoa_lan_auth"

_BLOCKED_SCRAPER_UAS = (
    "httrack", "webcopier", "teleport", "offline explorer", "sitegrab",
    "scrapy", "wget", "masscan", "sqlmap", "nikto", "nmap", "dirbuster",
    "gobuster", "semrushbot", "ahrefsbot", "mj12bot", "dotbot", "petalbot",
)
_HEAVY_API_PATHS = frozenset({
    "/api/make",
    "/api/cut",
    "/api/clone",
    "/api/make-from-script",
    "/api/revise",
    "/api/analyze-short",
    "/api/gemini/create",
    "/api/gemini/video",
    "/api/videos/upload",
    "/api/social/publish",
    "/api/scan",
})
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _is_safe_id(val: str) -> bool:
    return bool(val and _SAFE_ID_RE.match(val) and ".." not in val)


def _client_ip() -> str:
    return (request.remote_addr or "127.0.0.1").strip()


def _is_loopback_ip(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1", "localhost")


def _check_rate_limit(key: str, max_hits: int, window_sec: int) -> bool:
    allowed, _ = _RATE_LIMITER.allow(key, max_hits, window_sec)
    return allowed


def _rate_limited_response(msg: str, retry_after: int):
    resp = jsonify({"error": msg, "retry_after": retry_after})
    resp.status_code = 429
    resp.headers["Retry-After"] = str(max(1, int(retry_after)))
    return resp


def _run_with_job_guard(job_id: str, fn):
    """Runs a heavy background job inside JOB_GUARD so the user's PC never freezes."""
    if not JOB_GUARD.try_reserve():
        _finish_job(
            job_id,
            error="Trop de tâches lourdes en cours — attends qu'une génération se termine avant d'en lancer une autre.",
        )
        return False

    def _wrapped():
        acquired = False
        try:
            _update_job(job_id, 8, "⏳ En file d'attente (protection CPU/RAM)...")
            JOB_GUARD.acquire_slot()
            acquired = True
            fn()
        finally:
            if acquired:
                JOB_GUARD.release_slot()
            else:
                JOB_GUARD.cancel_reservation()

    threading.Thread(target=_wrapped, daemon=True).start()
    return True


@app.before_request
def _security_guard():
    # 0. Anti-DNS-Rebinding guard (blocks malicious domains pointing to 127.0.0.1)
    lan_ip_allowed = get_lan_ip() if CLIPOA_ALLOW_LAN else ""
    if not is_allowed_host_header(request.host, allow_lan=CLIPOA_ALLOW_LAN, lan_ip=lan_ip_allowed):
        return Response("Forbidden Host (DNS Rebinding blocked)", status=403)

    # 1. Block known automated scrapers / site rippers
    ua = (request.headers.get("User-Agent") or "").lower()
    if any(bot in ua for bot in _BLOCKED_SCRAPER_UAS):
        return Response("Forbidden", status=403)

    ip = _client_ip()
    path = request.path or "/"

    # 1b. Block cross-site browser exfiltration/CSRF via Fetch Metadata headers
    sec_fetch_site = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if path.startswith("/api/") and sec_fetch_site == "cross-site":
        return jsonify({"error": "Requête cross-site bloquée (protection des données)."}), 403

    # 2. LAN access guard: if server is exposed beyond loopback, require pairing token
    if _LAN_ACCESS_TOKEN and not _is_loopback_ip(ip) and not path.startswith("/oauth/"):
        import hmac
        provided = (
            request.args.get("token")
            or request.headers.get("X-Clipoa-Token")
            or request.cookies.get(_LAN_COOKIE_NAME)
            or ""
        )
        if not hmac.compare_digest(str(provided), _LAN_ACCESS_TOKEN):
            if path.startswith("/api/"):
                return jsonify({"error": "Accès LAN non autorisé — ouvre l'URL avec ton jeton Clipoa."}), 401
            return Response(
                "Accès LAN protégé — ouvre l'URL complète avec ?token=... affichée au démarrage de Clipoa.",
                status=401,
                mimetype="text/plain; charset=utf-8",
            )

    # 3. Sliding-window rate limiting per IP (3 tiers: polling, standard API, heavy AI/render)
    if path.startswith("/api/"):
        if path in _HEAVY_API_PATHS:
            ok, retry = _RATE_LIMITER.allow(f"heavy:{ip}", 15, 60)
            if not ok:
                return _rate_limited_response(
                    "Trop d'actions lourdes (IA/rendu) en peu de temps — patiente quelques secondes.",
                    retry,
                )
        elif path in ("/api/jobs", "/api/status", "/api/videos", "/api/thumb", "/api/system/health") or path.endswith("/status"):
            ok, retry = _RATE_LIMITER.allow(f"poll:{ip}", 240, 60)
            if not ok:
                return _rate_limited_response("Trop de requêtes, patiente quelques secondes.", retry)
        else:
            ok, retry = _RATE_LIMITER.allow(f"api:{ip}", 60, 60)
            if not ok:
                return _rate_limited_response("Limite de requêtes atteinte, réessaie dans une minute.", retry)

    # 4. Same-origin CSRF guard for state-changing API routes
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/"):
        origin = request.headers.get("Origin") or ""
        referer = request.headers.get("Referer") or ""
        req_host = (request.host or "").lower()
        if origin:
            orig_host = (urlparse(origin).netloc or "").lower()
            if orig_host and orig_host != req_host:
                return jsonify({"error": "Origine non autorisée"}), 403
        elif referer:
            ref_host = (urlparse(referer).netloc or "").lower()
            if ref_host and ref_host != req_host:
                return jsonify({"error": "Referer non autorisé"}), 403


@app.after_request
def _security_headers(response):
    # Persist LAN pairing token in an HttpOnly cookie when opened via ?token=...
    if _LAN_ACCESS_TOKEN and request.args.get("token"):
        import hmac
        if hmac.compare_digest(str(request.args.get("token")), _LAN_ACCESS_TOKEN):
            response.set_cookie(
                _LAN_COOKIE_NAME,
                _LAN_ACCESS_TOKEN,
                httponly=True,
                samesite="Lax",
                max_age=86400 * 7,
            )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
        # Redact any accidental token/proxy/IP/path leakage in JSON error responses
        if response.status_code >= 400 and response.is_json:
            try:
                body = response.get_json(silent=True)
                if isinstance(body, dict) and isinstance(body.get("error"), str):
                    cleaned = redact_sensitive_text(body["error"], mask_ips=True)
                    if cleaned != body["error"]:
                        body["error"] = cleaned
                        response.set_data(json.dumps(body, ensure_ascii=False))
            except Exception:
                pass
    return response


@app.route("/robots.txt")
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")

EDGE_VOICES = [
    {"id": "edge:fr-FR-VivienneMultilingualNeural", "label": "Vivienne (Gratuit · Naturelle)"},
    {"id": "edge:fr-FR-HenriNeural", "label": "Henri (Gratuit · Dynamique)"},
    {"id": "edge:fr-FR-DeniseNeural", "label": "Denise (Gratuit · Posée)"},
    {"id": "edge:fr-FR-EloiseNeural", "label": "Éloïse (Gratuit · Jeune)"},
]

JOBS_FILE = STORAGE_DIR / "jobs_history.json"
JOBS = {}
JOBS_LOCK = threading.Lock()


def _persist_jobs():
    try:
        # Keep only the 20 most recent jobs (atomic write to prevent corruption)
        ordered = sorted(JOBS.values(), key=lambda j: j.get("created_at", 0), reverse=True)[:20]
        JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(JOBS_FILE.parent), prefix=".jobs_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(ordered, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, JOBS_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass


def _load_persisted_jobs():
    if not JOBS_FILE.exists():
        return
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
        for j in items:
            if j.get("status") == "running":
                j["status"] = "error"
                j["error"] = "Interrompu par un redémarrage du serveur"
                j["step"] = "Interrompu — relance la génération"
            JOBS[j["id"]] = j
    except Exception:
        pass


_load_persisted_jobs()


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _create_job(kind: str, label: str, params: dict = None, resume_session_id: str = "") -> str:
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    sess = resume_session_id or f"{kind}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "kind": kind,
            "label": label,
            "params": params or {},
            "resume_session_id": sess,
            "status": "running",
            "progress": 5,
            "step": "Démarrage...",
            "session_id": "",
            "video_title": "",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        _persist_jobs()
    return job_id


def _pause_job_quota(job_id: str, msg: str):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["status"] = "paused_quota"
            JOBS[job_id]["error"] = msg
            JOBS[job_id]["updated_at"] = time.time()
            JOBS[job_id]["step"] = "⏸️ Quota Claude atteint — progression sauvegardée ! Change de compte ou attends le reset puis clique Reprendre."
            _persist_jobs()


def _update_job(job_id: str, progress: int, step: str):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["progress"] = progress
            JOBS[job_id]["step"] = step
            JOBS[job_id]["updated_at"] = time.time()
            _persist_jobs()


def _finish_job(job_id: str, result=None, error: str = None):
    with JOBS_LOCK:
        if job_id in JOBS:
            if error:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = error
                JOBS[job_id]["step"] = f"Erreur : {error}"
            else:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["progress"] = 100
                JOBS[job_id]["step"] = "Terminé — enregistré dans Mes Shorts"
                JOBS[job_id]["result"] = result
                if isinstance(result, dict):
                    if result.get("session_id"):
                        JOBS[job_id]["session_id"] = result["session_id"]
                        JOBS[job_id]["video_title"] = (result.get("script") or {}).get("title") or result["session_id"]
                    elif result.get("clips"):
                        first = result["clips"][0]
                        JOBS[job_id]["session_id"] = first.get("session_id", "")
                        JOBS[job_id]["video_title"] = f"{len(result['clips'])} short(s) extrait(s)"
            _persist_jobs()


_FR_DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
_FR_MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
_TYPE_LABELS = {
    "direct": "Short IA",
    "short": "Short IA",
    "custom_script": "Script IA",
    "clone": "Cloné",
    "monteur_cut": "Découpé",
    "plugin_da": "Plugin DA",
    "uploaded_short": "Importé",
    "gemini_short": "Short Gemini",
    "gemini_video": "Vidéo IA",
}


def _load_renders():
    renders = []
    if RENDERS_DIR.exists():
        for d in sorted(RENDERS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if d.is_dir():
                meta_file = d / "metadata.json"
                video_file = d / "final_short.mp4"
                if video_file.exists():
                    st = video_file.stat()
                    dt = datetime.fromtimestamp(st.st_mtime)
                    item = {
                        "id": d.name,
                        "video_path": str(video_file),
                        "script": {},
                        "audit": {},
                        "type": "short",
                        "type_label": "Short IA",
                        "validated": False,
                        "created_ts": st.st_mtime,
                        "created_date": dt.strftime("%Y-%m-%d"),
                        "created_label": f"{_FR_DAYS[dt.weekday()]} {dt.day}",
                        "social_caption": "",
                        "has_meta": meta_file.exists(),
                        "size_mb": round(st.st_size / (1024 * 1024), 1),
                    }
                    if meta_file.exists():
                        try:
                            with open(meta_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                item["script"] = data.get("script", {})
                                item["audit"] = data.get("audit", {})
                                rtype = data.get("type", "short")
                                item["type"] = rtype
                                item["plugin_id"] = data.get("plugin_id", "")
                                item["plugin_name"] = data.get("plugin_name", "")
                                item["type_label"] = data.get("plugin_name") or _TYPE_LABELS.get(rtype, "Short IA")
                                item["validated"] = bool(data.get("validated", False))
                                item["theme"] = data.get("theme", "")
                                item["subtitle_style"] = data.get("subtitle_style", "")
                                item["social_caption"] = (
                                    data.get("social_caption")
                                    or data.get("script", {}).get("social_caption")
                                    or ""
                                )
                        except Exception:
                            pass
                    renders.append(item)
    return renders


def _build_week_overview(renders, publish_queue, night_tasks):
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        week_range = f"Semaine du {monday.day} au {sunday.day} {_FR_MONTHS[sunday.month - 1]}"
    else:
        week_range = f"Du {monday.day} {_FR_MONTHS[monday.month - 1]} au {sunday.day} {_FR_MONTHS[sunday.month - 1]}"

    queue_by_date = {}
    for p in (publish_queue or []):
        raw_dt = (p.get("scheduled_at") or p.get("created_at_iso") or "")[:10]
        if len(raw_dt) == 10 and raw_dt not in queue_by_date:
            queue_by_date[raw_dt] = p

    render_by_date = {}
    for r in (renders or []):
        dkey = r.get("created_date") or ""
        if dkey and dkey not in render_by_date:
            render_by_date[dkey] = r

    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        d_iso = d.strftime("%Y-%m-%d")
        label = f"{_FR_DAYS[i]} {d.day}"
        q_item = queue_by_date.get(d_iso)
        r_item = render_by_date.get(d_iso)
        if q_item:
            st = q_item.get("status", "")
            if st == "published":
                status_txt = "Publiée"
                tone = "ok"
            elif st == "scheduled":
                hr = (q_item.get("scheduled_at") or "")[11:16]
                status_txt = f"Partira à {hr}" if hr else "Programmée"
                tone = "ok"
            else:
                status_txt = "En file Pulse"
                tone = "indigo"
            title = q_item.get("title") or "Short programmé"
        elif r_item:
            if r_item.get("validated"):
                status_txt = "Validée · prête"
                tone = "ok"
            else:
                status_txt = "À regarder"
                tone = "warn"
            title = (r_item.get("script") or {}).get("title") or r_item.get("id", "")
        elif d == today and night_tasks:
            status_txt = f"{len(night_tasks)} en Mode Nuit"
            tone = "indigo"
            title = night_tasks[0].get("topic", "Fabrication nocturne")
        else:
            status_txt = "Libre"
            tone = "muted"
            title = ""
        days.append({
            "date": d_iso,
            "label": label,
            "is_today": d == today,
            "status": status_txt,
            "tone": tone,
            "title": title,
            "render_id": r_item["id"] if r_item else "",
        })
    return week_range, days


@app.route("/")
def index():
    renders = _load_renders()
    claude_status = ClaudeBridge.check_status(live_probe=False)
    el_status = VoiceEngine.get_elevenlabs_status()
    drive_status = DriveClient.get_status()
    social_accounts = FreeSocialPublisher.get_public_accounts_status()
    publish_queue = FreeSocialPublisher.load_queue()
    night_tasks = NightFactory.load_tasks()
    style_plugins = StylePluginStore.list_plugins(include_script_body=False)
    bib = DriveClient.load_bibliotheque()
    custom_voices = [
        {"role": k, "name": v.get("nom", k), "voice_id": v.get("voice_id", "")}
        for k, v in (bib.get("voix") or {}).items()
        if isinstance(v, dict) and v.get("voice_id")
    ]

    validated_count = sum(1 for r in renders if r.get("validated"))
    unvalidated_count = max(0, len(renders) - validated_count)
    week_range_label, week_days = _build_week_overview(renders, publish_queue, night_tasks)

    lan_ip = get_lan_ip()
    port = request.host.split(":")[-1] if ":" in request.host else "8080"
    mobile_url = f"http://{lan_ip}:{port}"

    return render_template(
        "index.html",
        app_build=APP_BUILD,
        renders=renders,
        validated_count=validated_count,
        unvalidated_count=unvalidated_count,
        week_range_label=week_range_label,
        week_days=week_days,
        themes=THEMES,
        subtitle_styles=SUBTITLE_STYLES,
        edge_voices=EDGE_VOICES,
        gemini_voices=GEMINI_VOICES,
        custom_voices=custom_voices,
        default_voice=f"edge:{DEFAULT_TTS_VOICE}",
        claude_status=claude_status,
        claude_plans=CLAUDE_PLAN_BUDGETS,
        gemini_status=GeminiStudio.get_status(),
        agy_status=AntigravityBridge.check_status(live_probe=False),
        el_status=el_status,
        drive_status=drive_status,
        social_accounts=social_accounts,
        oauth_apps=FreeSocialPublisher.get_public_oauth_apps(),
        publish_queue=publish_queue,
        night_tasks=night_tasks,
        style_plugins=style_plugins,
        plugin_gradients=PLUGIN_GRADIENTS,
        plugin_categories=PLUGIN_CATEGORIES,
        script_languages=SCRIPT_LANGUAGES,
        sheet_roles=SHEET_ROLES,
        blender_available=BlenderEngine.is_available(),
        internal_reports=AnalyticsEngine.load_internal_reports(),
        external_report=AnalyticsEngine.load_external_report(),
        analytics_niches=PRESET_NICHES,
        presets=list_presets(),
        learned_estimates=get_learned_estimates(),
        script_templates=list_script_templates(),
        mobile_url=mobile_url,
    )


@app.route("/manifest.json")
def pwa_manifest():
    return jsonify({
        "name": "Clipoa",
        "short_name": "Clipoa",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0E0E11",
        "theme_color": "#0E0E11",
        "orientation": "portrait-primary",
        "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
    })


@app.route("/icon.svg")
def pwa_icon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="none">
  <rect width="512" height="512" rx="120" fill="#E11D48"/>
  <rect x="200" y="80" width="184" height="288" rx="48" fill="#FFFFFF" fill-opacity="0.42"/>
  <rect x="120" y="128" width="216" height="320" rx="52" fill="#FFFFFF" stroke="#E11D48" stroke-width="20"/>
  <path d="M202 234L290 288L202 342V234Z" fill="#E11D48"/>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


@app.route("/stream/<render_id>")
def stream_video(render_id):
    if not _is_safe_id(render_id):
        return "Invalid ID", 400
    video_path = RENDERS_DIR / render_id / "final_short.mp4"
    if not video_path.exists():
        return "Video not found", 404
    return send_file(str(video_path), mimetype="video/mp4", conditional=True)


@app.route("/download/<render_id>")
def download_video(render_id):
    if not _is_safe_id(render_id):
        return "Invalid ID", 400
    video_path = RENDERS_DIR / render_id / "final_short.mp4"
    if not video_path.exists():
        return "Video not found", 404
    return send_file(str(video_path), mimetype="video/mp4", as_attachment=True, download_name=f"clipoa_{render_id}.mp4")


# ---------- Claude Account & Quota APIs ----------

@app.route("/api/status", methods=["GET"])
def api_status():
    probe = request.args.get("probe", "0") in ("1", "true", "yes")
    return jsonify(ClaudeBridge.check_status(live_probe=probe))


@app.route("/api/claude/plan", methods=["POST"])
def api_claude_plan():
    data = request.json or {}
    plan = data.get("plan", "pro")
    if plan not in CLAUDE_PLAN_BUDGETS:
        return jsonify({"error": "Plan invalide"}), 400
    save_settings({"claude": {"plan": plan}})
    return jsonify(ClaudeBridge.check_status(live_probe=False))


@app.route("/api/claude/model", methods=["POST"])
def api_claude_model():
    data = request.json or {}
    model = (data.get("model") or "opus").strip().lower()
    effort = (data.get("effort") or "medium").strip().lower()
    if model not in ("opus", "sonnet", "haiku", "fable"):
        return jsonify({"error": "Modèle invalide"}), 400
    if effort not in ("low", "medium", "high", "max"):
        effort = "medium"
    save_settings({"claude": {"model": model, "effort": effort}})
    return jsonify(ClaudeBridge.check_status(live_probe=False))


@app.route("/api/claude/logout", methods=["POST"])
def api_claude_logout():
    return jsonify(ClaudeBridge.logout_cli())


@app.route("/api/claude/login", methods=["POST"])
def api_claude_login():
    return jsonify(ClaudeBridge.start_login_cli())


@app.route("/api/claude/reset-quota", methods=["POST"])
def api_claude_reset_quota():
    reset_claude_quota_counter()
    return jsonify(ClaudeBridge.check_status(live_probe=False))


@app.route("/api/claude/sync-quota", methods=["POST"])
def api_claude_sync_quota():
    ClaudeBridge.sync_real_quota()
    return jsonify(ClaudeBridge.check_status(live_probe=True))


# ---------- Google Gemini Studio APIs ----------

@app.route("/api/gemini/connect", methods=["POST"])
def api_gemini_connect():
    data = request.json or {}
    try:
        st = GeminiStudio.connect(
            api_key=data.get("api_key", ""),
            model=data.get("model", "gemini-3-flash-preview"),
        )
        return jsonify(st)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/gemini/check-tier", methods=["POST"])
def api_gemini_check_tier():
    GeminiStudio.detect_tier()
    return jsonify(GeminiStudio.get_status())


@app.route("/api/gemini/budget", methods=["POST"])
def api_gemini_budget():
    data = request.json or {}
    try:
        budget_usd = float(data.get("budget_usd", 10.0))
        reset_spent = bool(data.get("reset_spent", False))
        return jsonify(GeminiStudio.set_credit_budget(budget_usd, reset_spent=reset_spent))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/gemini/login-google", methods=["POST"])
def api_gemini_login_google():
    return jsonify({"ok": False, "message": "Google a désactivé la connexion CLI personnelle — utilise ta clé gratuite Google AI Studio."})


@app.route("/api/gemini/switch-account", methods=["POST"])
def api_gemini_switch_account():
    return jsonify(GeminiStudio.logout_and_switch())


@app.route("/api/gemini/create", methods=["POST"])
def api_gemini_create():
    bg_video = None
    if request.content_type and "multipart/form-data" in request.content_type:
        topic = (request.form.get("topic") or "").strip()
        plugin_id = (request.form.get("plugin_id") or "").strip() or None
        custom_script = (request.form.get("custom_script") or "").strip() or None
        custom_title = (request.form.get("custom_title") or "").strip() or None
        try:
            target_duration_sec = max(15, min(180, int(request.form.get("target_duration_sec") or 60)))
        except (TypeError, ValueError):
            target_duration_sec = 60
        model = request.form.get("model") or GeminiStudio.get_best_available_model()
        theme = request.form.get("theme", DEFAULT_THEME)
        subtitle_style = request.form.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
        voice = request.form.get("voice") or None
        use_blender_3d = request.form.get("use_blender_3d", "false").lower() in ("1", "true", "yes", "on")
        retention_boost = request.form.get("retention_boost", "true").lower() in ("1", "true", "yes", "on")
        uploaded_bg = request.files.get("bg_file")
        if uploaded_bg and uploaded_bg.filename:
            safe_bg = secure_filename(uploaded_bg.filename) or "bg.mp4"
            if Path(safe_bg).suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
                return jsonify({"error": "Extension de fichier de fond non autorisée."}), 400
            fname = f"broll_{int(time.time())}_{safe_bg}"
            save_path = VIDEOS_DIR / fname
            uploaded_bg.save(str(save_path))
            bg_video = str(save_path)
    else:
        data = request.json or {}
        topic = (data.get("topic") or "").strip()
        plugin_id = (data.get("plugin_id") or "").strip() or None
        custom_script = (data.get("custom_script") or "").strip() or None
        custom_title = (data.get("custom_title") or "").strip() or None
        try:
            target_duration_sec = max(15, min(180, int(data.get("target_duration_sec") or 60)))
        except (TypeError, ValueError):
            target_duration_sec = 60
        model = data.get("model") or GeminiStudio.get_best_available_model()
        theme = data.get("theme", DEFAULT_THEME)
        subtitle_style = data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
        voice = data.get("voice") or None
        use_blender_3d = bool(data.get("use_blender_3d", False))
        retention_boost = bool(data.get("retention_boost", True))

    if not topic and not custom_script:
        return jsonify({"error": "Écris un sujet ou colle ton script pour Gemini"}), 400

    display_lbl = (custom_title or topic or (custom_script or "")[:40])[:38]
    job_id = _create_job("gemini", f"✨ Gemini ({model}) : {display_lbl}")

    def _run():
        try:
            res = GeminiStudio.create_short(
                topic=topic,
                plugin_id=plugin_id,
                custom_script=custom_script,
                custom_title=custom_title,
                target_duration_sec=target_duration_sec,
                model=model,
                theme=theme,
                subtitle_style=subtitle_style,
                voice=voice,
                background_video=bg_video,
                use_blender_3d=use_blender_3d,
                retention_boost=retention_boost,
                progress_cb=lambda pct, msg: _update_job(job_id, pct, msg),
            )
            _finish_job(job_id, result=res)
        except Exception as e:
            _finish_job(job_id, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/gemini/video", methods=["POST"])
def api_gemini_video():
    data = request.json or {}
    prompt = (data.get("prompt") or "").strip()
    video_model = data.get("video_model", "gemini-omni-1.2-flash")
    plugin_id = (data.get("plugin_id") or "").strip() or None
    if not prompt:
        return jsonify({"error": "Décris la scène vidéo 9:16 à générer"}), 400

    job_id = _create_job("veo", f"🎬 Vidéo IA ({video_model}) : {prompt[:36]}")

    def _run():
        try:
            res = GeminiStudio.generate_ai_video(
                prompt=prompt,
                video_model=video_model,
                aspect_ratio="9:16",
                plugin_id=plugin_id,
                progress_cb=lambda pct, msg: _update_job(job_id, pct, msg),
            )
            _finish_job(job_id, result=res)
        except Exception as e:
            _finish_job(job_id, error=str(e))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job_id})


# ---------- ElevenLabs Native APIs ----------

@app.route("/api/elevenlabs/status", methods=["GET"])
def api_el_status():
    return jsonify(VoiceEngine.get_elevenlabs_status())


@app.route("/api/elevenlabs/connect", methods=["POST"])
def api_el_connect():
    data = request.json or {}
    api_key = (data.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"error": "Clé API ElevenLabs manquante"}), 400
    res = VoiceEngine.connect_elevenlabs(
        api_key=api_key,
        default_voice_id=data.get("default_voice_id"),
        model_id=data.get("model_id", "eleven_multilingual_v2"),
        enabled=bool(data.get("enabled", True)),
    )
    if not res.get("connected"):
        return jsonify({"error": res.get("message", "Connexion échouée")}), 400
    return jsonify(res)


@app.route("/api/elevenlabs/voices", methods=["GET"])
def api_el_voices():
    return jsonify({"voices": VoiceEngine.list_elevenlabs_voices()})


@app.route("/api/elevenlabs/disconnect", methods=["POST"])
def api_el_disconnect():
    """Déconnecte la clé ElevenLabs actuelle pour permettre de changer facilement de compte."""
    save_settings({"elevenlabs": {"api_key": "", "enabled": False, "default_voice_id": ""}})
    st = VoiceEngine.get_elevenlabs_status()
    st["ok"] = True
    st["message"] = "Compte ElevenLabs déconnecté — colle ta nouvelle clé API pour changer de compte."
    return jsonify(st)


# ---------- Creative Workspace Drive & Style Plugins (DA) APIs ----------

@app.route("/api/drive/status", methods=["GET"])
def api_drive_status():
    return jsonify(DriveClient.get_status())


@app.route("/api/drive/ideas", methods=["GET"])
def api_drive_ideas():
    q = request.args.get("q", "")
    try:
        limit = max(1, min(200, int(request.args.get("limit", 40))))
    except (ValueError, TypeError):
        limit = 40
    return jsonify({"ideas": DriveClient.load_ideas(query=q, limit=limit)})


@app.route("/api/drive/sync", methods=["POST"])
def api_drive_sync():
    data = request.json or {}
    folder = (data.get("folder_path") or "").strip()
    if not folder:
        return jsonify({"status": DriveClient.get_status(), "message": "Dossier synchronisé vérifié."})
    try:
        res = DriveClient.sync_from_local_folder(folder)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/plugins", methods=["GET", "POST"])
def api_plugins():
    if request.method == "GET":
        return jsonify({"plugins": StylePluginStore.list_plugins(include_script_body=False)})
    data = request.json or {}
    try:
        created = StylePluginStore.create_plugin(data)
        return jsonify({"plugin": created, "plugins": StylePluginStore.list_plugins(include_script_body=False)})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plugins/<plugin_id>", methods=["GET", "PUT", "DELETE"])
def api_plugin_item(plugin_id):
    if request.method == "GET":
        p = StylePluginStore.get_plugin(plugin_id, include_script_body=True)
        if not p:
            return jsonify({"error": "Plugin introuvable"}), 404
        return jsonify({"plugin": p})
    if request.method == "PUT":
        data = request.json or {}
        try:
            updated = StylePluginStore.update_plugin(plugin_id, data)
            return jsonify({"plugin": updated, "plugins": StylePluginStore.list_plugins(include_script_body=False)})
        except FileNotFoundError:
            return jsonify({"error": "Plugin introuvable"}), 404
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    ok = StylePluginStore.delete_plugin(plugin_id)
    if not ok:
        return jsonify({"error": "Plugin introuvable"}), 404
    return jsonify({"deleted": True, "plugins": StylePluginStore.list_plugins(include_script_body=False)})


@app.route("/api/plugins/<plugin_id>/sheets", methods=["POST"])
def api_plugin_upload_sheets(plugin_id):
    files = request.files.getlist("files") or ([request.files["file"]] if "file" in request.files else [])
    if not files:
        return jsonify({"error": "Sélectionne au moins une planche de modèle."}), 400
    role = (request.form.get("role") or "reference").strip().lower()
    updated = None
    try:
        for f in files:
            if f and f.filename:
                updated = StylePluginStore.add_model_sheet(plugin_id, f, role=role)
        if not updated:
            return jsonify({"error": "Aucun fichier valide reçu."}), 400
        return jsonify({"plugin": updated, "plugins": StylePluginStore.list_plugins(include_script_body=False)})
    except FileNotFoundError:
        return jsonify({"error": "Plugin introuvable"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plugins/<plugin_id>/sheets/<filename>", methods=["GET", "DELETE"])
def api_plugin_sheet_item(plugin_id, filename):
    if request.method == "GET":
        fpath = StylePluginStore.get_sheet_path(plugin_id, filename)
        if not fpath:
            return "Sheet not found", 404
        return send_file(str(fpath), conditional=True)
    try:
        updated = StylePluginStore.delete_model_sheet(plugin_id, filename)
        return jsonify({"plugin": updated, "plugins": StylePluginStore.list_plugins(include_script_body=False)})
    except FileNotFoundError:
        return jsonify({"error": "Plugin introuvable"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400


@app.route("/api/plugins/<plugin_id>/script", methods=["POST"])
def api_plugin_upload_script(plugin_id):
    try:
        if request.content_type and "multipart/form-data" in request.content_type:
            up = request.files.get("file") or request.files.get("script")
            lang = (request.form.get("script_language") or "").strip().lower() or None
            updated = StylePluginStore.upload_script_file(plugin_id, up, language=lang)
        else:
            data = request.json or {}
            updated = StylePluginStore.update_plugin(
                plugin_id,
                {
                    "script_language": data.get("script_language", "python"),
                    "script_filename": data.get("script_filename", ""),
                    "script_content": data.get("script_content", ""),
                },
            )
        return jsonify({"plugin": updated, "plugins": StylePluginStore.list_plugins(include_script_body=False)})
    except FileNotFoundError:
        return jsonify({"error": "Plugin introuvable"}), 404
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _normalize_engine_params(params: dict) -> dict:
    """
    Anciennes pages (et tâches enregistrées avant le correctif) envoyaient « Claude » sous la forme
    engine=antigravity + engine_model=claude-… : c'était exécuté par Antigravity et vidait son quota.
    Sans choix explicite d'Antigravity par l'utilisateur (`engine_choice`), on repasse sur le Claude CLI.
    """
    p = dict(params or {})
    model = str(p.get("engine_model") or "").lower()
    if p.get("engine") == "antigravity" and model.startswith("claude") and p.get("engine_choice") != "antigravity":
        p["engine"] = "claude"
        p["engine_model"] = None
    return p


def _launch_pipeline_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["error"] = None
        kind = job["kind"]
        params = _normalize_engine_params(job.get("params") or {})
        job["params"] = params
        sess = job.get("resume_session_id") or None
        _persist_jobs()

    def _run():
        try:
            cb = lambda pct, msg: _update_job(job_id, pct, msg)
            if kind == "style_only":
                from core.style_analyzer import create_style_from_reference
                res = create_style_from_reference(
                    params["url"], engine=params.get("engine") or "claude", model=params.get("engine_model") or None, progress=cb,
                )
                _finish_job(job_id, result=res)
                return
            if kind == "style_ref" and not params.get("plugin_id"):
                # 1) l'agent regarde la vidéo d'exemple et crée le style ; 2) il fabrique la vidéo dans ce style
                from core.style_analyzer import create_style_from_reference
                made = create_style_from_reference(
                    params["url"], engine=params.get("engine") or "claude", model=params.get("engine_model") or None,
                    progress=lambda pct, msg: cb(int(pct * 0.4), msg),
                )
                with JOBS_LOCK:
                    params["plugin_id"] = made["plugin"]["id"]
                    params["style_analysis"] = {k: made.get(k) for k in ("renderer", "tool_guess", "confidence", "vision")}
                    JOBS[job_id]["params"] = params
                    _persist_jobs()
                cb(40, f"✅ Style « {made['plugin']['name']} » créé (rendu {made['renderer']}). Fabrication de ta vidéo...")
            if kind == "clone":
                res = ShortCrewPipeline.clone_competitor_short(
                    video_url=params["url"],
                    my_topic=params["topic"],
                    theme=params.get("theme", DEFAULT_THEME),
                    subtitle_style=params.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
                    cookies_from_browser=params.get("cookies"),
                    voice=params.get("voice"),
                    progress_cb=cb,
                    resume_session_id=sess,
                )
            else:
                res = ShortCrewPipeline.create_direct_short(
                    topic=params.get("topic", ""),
                    user_style=params.get("style"),
                    background_video=params.get("background_video"),
                    theme=params.get("theme", DEFAULT_THEME),
                    subtitle_style=params.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
                    voice=params.get("voice"),
                    use_blender_3d=bool(params.get("use_blender_3d", False)),
                    retention_boost=bool(params.get("retention_boost", True)),
                    plugin_id=params.get("plugin_id") or None,
                    custom_script=params.get("custom_script") or None,
                    custom_title=params.get("custom_title") or None,
                    target_duration_sec=int(params.get("target_duration_sec") or 60),
                    engine=params.get("engine") or "claude",
                    engine_model=params.get("engine_model") or None,
                    enable_music=bool(params.get("enable_music", True)),
                    enable_sfx=bool(params.get("enable_sfx", True)),
                    template_shots=params.get("template_shots") or None,
                    progress_cb=cb,
                    resume_session_id=sess,
                )
            _finish_job(job_id, result=res)
        except ClaudeQuotaExceededError as qe:
            _pause_job_quota(job_id, str(qe))
        except Exception as e:
            _finish_job(job_id, error=str(e))

    _run_with_job_guard(job_id, _run)


# ---------- Free Self-Hosted Postiz (Multi-Platform Publisher) ----------

@app.route("/api/social/accounts", methods=["GET"])
def api_social_accounts():
    return jsonify({"accounts": FreeSocialPublisher.get_public_accounts_status()})


@app.route("/api/social/connect", methods=["POST"])
def api_social_connect():
    data = request.json or {}
    platform = data.get("platform")
    try:
        updated = FreeSocialPublisher.save_account(platform, data)
        return jsonify({"account": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/disconnect", methods=["POST"])
def api_social_disconnect():
    data = request.json or {}
    platform = data.get("platform")
    try:
        return jsonify({"account": FreeSocialPublisher.disconnect_account(platform, (data.get("account_key") or "").strip())})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/switch-account", methods=["POST"])
def api_social_switch_account():
    data = request.json or {}
    try:
        acc = FreeSocialPublisher.switch_account(data.get("platform") or "", (data.get("account_key") or "").strip())
        return jsonify({"account": acc})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/portal-login/<platform>", methods=["POST"])
def api_social_portal_login(platform):
    """Enregistre la connexion effectuée directement dans le même navigateur de l'utilisateur."""
    from core.browser_auth import PORTALS
    plat = platform.strip().lower()
    if plat not in PORTALS:
        return jsonify({"error": f"Plateforme inconnue : {plat}"}), 400
    data = request.json or {}
    cfg = PORTALS[plat]
    if data.get("confirm"):
        handle = (data.get("handle") or "").strip() or f"{cfg['name']} (Connecté)"
        field_map = {
            "youtube": {"channel_name": handle},
            "tiktok": {"username": handle},
            "instagram": {"username": handle},
            "facebook": {"page_name": handle},
        }
        acc = FreeSocialPublisher.save_account(
            plat,
            {"access_token": f"same_browser:{plat}", **field_map.get(plat, {})},
        )
        return jsonify({"status": "connected", "account": acc, "message": f"{cfg['name']} connecté !"})
    return jsonify({
        "status": "open_portal",
        "platform": plat,
        "name": cfg["name"],
        "login_url": cfg["login_url"],
        "upload_url": cfg["upload_url"],
    })


@app.route("/api/social/portal-login/<platform>/status", methods=["GET"])
def api_social_portal_login_status(platform):
    return jsonify(BrowserPortalAuth.get_state(platform.strip().lower()))


@app.route("/api/social/oauth-app", methods=["POST"])
def api_social_oauth_app():
    data = request.json or {}
    provider = (data.get("provider") or "").strip().lower()
    cid = (data.get("client_id") or "").strip()
    csec = (data.get("client_secret") or "").strip()
    if not cid or not csec:
        return jsonify({"error": "Client ID et Client Secret requis"}), 400
    try:
        res = FreeSocialPublisher.save_oauth_app(provider, cid, csec)
        return jsonify({"app": res, "oauth_apps": FreeSocialPublisher.get_public_oauth_apps()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/relay-config", methods=["POST"])
def api_social_relay_config():
    data = request.json or {}
    try:
        res = FreeSocialPublisher.save_relay_config(
            relay_url=data.get("url") or "",
            enabled=bool(data.get("enabled", True)),
            prefer_relay=bool(data.get("prefer_relay", False)),
        )
        return jsonify({"oauth_apps": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/meta/select-page", methods=["POST"])
def api_social_meta_select_page():
    data = request.json or {}
    page_id = (data.get("page_id") or "").strip()
    if not page_id:
        return jsonify({"error": "page_id manquant"}), 400
    try:
        accounts = FreeSocialPublisher.select_meta_page(page_id)
        return jsonify({"accounts": accounts})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def _oauth_base_url() -> str:
    host = request.host.split(":")[0]
    port = request.host.split(":")[1] if ":" in request.host else "8080"
    if host in ("localhost", "127.0.0.1") or host.startswith(("192.168.", "10.", "172.")):
        return f"http://localhost:{port}"
    return request.host_url.rstrip("/")


def _oauth_return_redirect(return_view: str, **query_params) -> Response:
    base_q = "open=reglages" if return_view == "reglages" else "view=auto"
    extra = "&".join(f"{k}={quote(str(v)[:180], safe='')}" for k, v in query_params.items() if v)
    return redirect(f"/?{base_q}" + (f"&{extra}" if extra else ""))


@app.route("/oauth/<provider>/start", methods=["GET"])
def oauth_start(provider):
    return_view = "reglages" if request.args.get("from") == "reglages" else "auto"
    try:
        auth_url = FreeSocialPublisher.build_oauth_authorize_url(
            provider,
            _oauth_base_url(),
            return_view=return_view,
        )
        return redirect(auth_url)
    except Exception as e:
        return _oauth_return_redirect(return_view, oauth_error=str(e))


@app.route("/oauth/<provider>/relay-done", methods=["GET", "POST"])
def oauth_relay_done(provider):
    """Réceptionne le retour 1-clic sécurisé (POST/GET) du relais OAuth Clipoa et enregistre le compte."""
    src = request.form if request.method == "POST" else request.args
    nonce = (src.get("nonce") or "").strip()
    state_entry = FreeSocialPublisher.consume_oauth_state(nonce) if nonce else None
    return_view = (state_entry or {}).get("return_view", "auto")
    target = (state_entry or {}).get("target") or (src.get("target") or provider)

    error = src.get("error")
    if error:
        return _oauth_return_redirect(return_view, oauth_error=error)
    if not state_entry:
        return _oauth_return_redirect(return_view, oauth_error="Session OAuth expirée — reclique sur Se connecter.")

    try:
        res = FreeSocialPublisher.handle_relay_done(provider, dict(src), target=target)
        connected_list = ",".join(res.get("connected_platforms") or [provider])
        return _oauth_return_redirect(return_view, connected=connected_list)
    except Exception as e:
        return _oauth_return_redirect(return_view, oauth_error=str(e))


@app.route("/oauth/<provider>/callback", methods=["GET"])
def oauth_callback(provider):
    state_raw = (request.args.get("state") or "").strip()
    state_entry = FreeSocialPublisher.consume_oauth_state(state_raw) if state_raw else None
    return_view = (state_entry or {}).get("return_view", "auto")
    target = (state_entry or {}).get("target") or provider

    error = request.args.get("error_description") or request.args.get("error")
    if error:
        return _oauth_return_redirect(return_view, oauth_error=error)
    code = request.args.get("code")
    if not code:
        return _oauth_return_redirect(return_view, oauth_error="code_manquant")
    if not state_entry:
        return _oauth_return_redirect(return_view, oauth_error="Session OAuth expirée — reclique sur Se connecter.")
    try:
        res = FreeSocialPublisher.handle_oauth_callback(provider, code, _oauth_base_url(), target=target)
        connected_list = ",".join(res.get("connected_platforms") or [provider])
        return _oauth_return_redirect(return_view, connected=connected_list)
    except Exception as e:
        return _oauth_return_redirect(return_view, oauth_error=str(e))


@app.route("/api/thumb", methods=["GET"])
def api_thumb_proxy():
    """Proxy léger pour afficher nettes les miniatures TikTok / YouTube / Reels sans blocage Referer."""
    import requests as _req
    img_url = (request.args.get("url") or "").strip()
    if not img_url.startswith("https://"):
        return "Bad URL", 400
    host = (urlparse(img_url).hostname or "").lower()
    allowed_suffixes = ("ytimg.com", "cdninstagram.com", "fbcdn.net", "muscdn.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com")
    if not any(host == suf or host.endswith("." + suf) for suf in allowed_suffixes):
        return "Forbidden host", 403
    try:
        r = _req.get(
            img_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=10,
            allow_redirects=False,
        )
        if r.status_code != 200 or len(r.content) > 5 * 1024 * 1024:
            return "Not found", 404
        ctype = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            return "Invalid content type", 400
        return Response(r.content, mimetype=ctype, headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        return "Error", 502


@app.route("/api/social/queue", methods=["GET"])
def api_social_queue():
    return jsonify({"queue": FreeSocialPublisher.load_queue()})


@app.route("/api/social/publish", methods=["POST"])
def api_social_publish():
    data = request.json or {}
    render_id = (data.get("render_id") or "").strip()
    platforms = data.get("platforms") or []
    title = data.get("title") or "Clipoa Short"
    caption = data.get("caption") or ""
    scheduled_at = (data.get("scheduled_at") or "").strip() or None
    publish_now = bool(data.get("publish_now", not scheduled_at))
    public_video_url = (data.get("public_video_url") or "").strip() or None
    async_publish = bool(data.get("async", False))

    if not render_id or not platforms:
        return jsonify({"error": "Choisis une vidéo et au moins une plateforme"}), 400
    if not _is_safe_id(render_id):
        return jsonify({"error": "ID vidéo invalide"}), 400
    if not publish_now and not scheduled_at:
        return jsonify({"error": "Choisis une date et une heure pour programmer l'envoi."}), 400

    acc_status = FreeSocialPublisher.get_public_accounts_status()
    if not publish_now:
        missing_auto = [acc_status[p]["name"] for p in platforms if p in acc_status and not acc_status[p]["auto_api"]]
        if missing_auto:
            return jsonify({
                "error": f"Pour programmer un envoi 100% automatique, connecte d'abord {', '.join(missing_auto)} via le bouton « Se connecter »."
            }), 400
    else:
        missing = [acc_status[p]["name"] for p in platforms if p in acc_status and not acc_status[p]["connected"]]
        if missing:
            return jsonify({
                "error": f"Connecte d'abord {', '.join(missing)} via le bouton « Se connecter » juste au-dessus."
            }), 400

    video_path = RENDERS_DIR / render_id / "final_short.mp4"
    if not video_path.exists():
        return jsonify({"error": "Vidéo introuvable"}), 404

    try:
        post = FreeSocialPublisher.create_post(
            render_id=render_id,
            video_path=str(video_path),
            title=title,
            caption=caption,
            platforms=platforms,
            scheduled_at=scheduled_at,
            publish_now=publish_now,
            public_video_url=public_video_url,
            async_publish=async_publish,
        )
        return jsonify({"post": post})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/queue/<post_id>/publish-now", methods=["POST"])
def api_social_publish_now_item(post_id):
    if not _is_safe_id(post_id):
        return jsonify({"error": "ID publication invalide"}), 400
    data = request.json or {}
    if data.get("async", True):
        threading.Thread(target=FreeSocialPublisher.execute_post, args=(post_id,), daemon=True).start()
        return jsonify({"ok": True, "status": "publishing"})
    try:
        post = FreeSocialPublisher.execute_post(post_id)
        return jsonify({"ok": True, "post": post})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/social/queue/<post_id>", methods=["DELETE"])
def api_social_delete(post_id):
    ok = FreeSocialPublisher.delete_post(post_id)
    return jsonify({"deleted": ok})


# ---------- Analytics (Interne + Externe Tendances & Concurrence) ----------

@app.route("/api/analytics/internal", methods=["GET"])
def api_analytics_internal_list():
    return jsonify({"reports": AnalyticsEngine.load_internal_reports()})


@app.route("/api/analytics/internal/analyze", methods=["POST"])
def api_analytics_internal_analyze():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    engine = (data.get("engine") or "gemini").strip().lower()
    if not url:
        return jsonify({"error": "Colle le lien de ta vidéo YouTube Shorts, TikTok ou Reel"}), 400
    try:
        rep = AnalyticsEngine.analyze_internal_video(url=url, engine=engine)
        return jsonify({"report": rep})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/internal/sync", methods=["POST"])
def api_analytics_internal_sync():
    data = request.json or {}
    engine = (data.get("engine") or "gemini").strip().lower()
    try:
        res = AnalyticsEngine.sync_published_posts(engine=engine)
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics/internal/<report_id>", methods=["DELETE"])
def api_analytics_internal_delete(report_id):
    ok = AnalyticsEngine.delete_internal_report(report_id)
    return jsonify({"deleted": ok})


@app.route("/api/analytics/external", methods=["GET"])
def api_analytics_external_get():
    return jsonify({"report": AnalyticsEngine.load_external_report()})


@app.route("/api/analytics/external/scan", methods=["POST"])
def api_analytics_external_scan():
    data = request.json or {}
    niches = data.get("niches") or []
    custom_niche = (data.get("custom_niche") or "").strip()
    lang = (data.get("lang") or "fr").strip().lower()
    engine = (data.get("engine") or "gemini").strip().lower()
    try:
        rep = AnalyticsEngine.analyze_external_niches(niche_ids=niches, custom_niche=custom_niche, lang=lang, engine=engine)
        return jsonify({"report": rep})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Night Factory (Créer des vidéos pendant que je dors) ----------

@app.route("/api/night/tasks", methods=["GET"])
def api_night_tasks():
    return jsonify({"tasks": NightFactory.load_tasks()})


@app.route("/api/night/enqueue", methods=["POST"])
def api_night_enqueue():
    data = request.json or {}
    topics = data.get("topics") or []
    if isinstance(topics, str):
        topics = [line.strip() for line in topics.splitlines() if line.strip()]
    if not topics:
        return jsonify({"error": "Ajoute au moins un sujet pour le Mode Nuit"}), 400

    try:
        target_dur = max(15, min(180, int(data.get("target_duration_sec") or 60)))
    except (TypeError, ValueError):
        target_dur = 60

    created = NightFactory.enqueue_batch(
        topics=topics,
        plugin_id=(data.get("plugin_id") or "").strip() or None,
        target_duration_sec=target_dur,
        engine=data.get("engine", "claude"),
        model=data.get("model") or None,
        start_at=data.get("start_at", ""),
        theme=data.get("theme", DEFAULT_THEME),
        subtitle_style=data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
        voice=data.get("voice") or None,
        keep_awake=bool(data.get("keep_awake", True)),
        auto_publish_platforms=data.get("auto_publish_platforms") or [],
    )
    return jsonify({"created": len(created), "tasks": NightFactory.load_tasks()})


@app.route("/api/night/tasks/<task_id>", methods=["DELETE"])
def api_night_delete(task_id):
    NightFactory.cancel_task(task_id)
    return jsonify({"tasks": NightFactory.load_tasks()})


@app.route("/api/night/clear", methods=["POST"])
def api_night_clear():
    NightFactory.clear_completed()
    return jsonify({"tasks": NightFactory.load_tasks()})


# ---------- Core ShortCrew Creation / Cutting / Scanning APIs ----------

@app.route("/api/videos", methods=["GET"])
def api_videos():
    return jsonify({"videos": _load_renders()})


@app.route("/api/videos/upload", methods=["POST"])
def api_upload_short_video():
    """Importe un Short existant (.mp4 / .mov / .webm) directement dans Clipoa pour publication ou programmation."""
    uploaded = request.files.get("video")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Sélectionne un fichier vidéo (.mp4 ou .mov)."}), 400

    safe_name = secure_filename(uploaded.filename) or "short.mp4"
    ext = Path(safe_name).suffix.lower()
    if ext not in (".mp4", ".mov", ".m4v", ".webm"):
        return jsonify({"error": "Format non supporté — utilise un fichier .mp4, .mov ou .webm."}), 400

    stem_title = Path(uploaded.filename).stem.replace("_", " ").replace("-", " ").strip()
    title = (request.form.get("title") or stem_title or "Short importé").strip()[:100]
    caption = (request.form.get("caption") or f"{title} #Shorts").strip()

    session_id = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    dest_dir = RENDERS_DIR / session_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw_dest = dest_dir / f"source{ext}"
    final_mp4 = dest_dir / "final_short.mp4"

    try:
        uploaded.save(str(raw_dest))
        if ext == ".mp4":
            # Fast remux with +faststart for Instagram Reels / TikTok compatibility (no re-encode if valid H.264/AAC)
            proc = subprocess.run(
                [FFMPEG_PATH, "-y", "-i", str(raw_dest), "-c", "copy", "-movflags", "+faststart", str(final_mp4)],
                capture_output=True,
                timeout=90,
            )
            if proc.returncode != 0 or not final_mp4.exists():
                shutil.move(str(raw_dest), str(final_mp4))
            else:
                raw_dest.unlink(missing_ok=True)
        else:
            proc = subprocess.run(
                [
                    FFMPEG_PATH, "-y", "-i", str(raw_dest),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                    str(final_mp4),
                ],
                capture_output=True,
                timeout=240,
            )
            raw_dest.unlink(missing_ok=True)
            if proc.returncode != 0 or not final_mp4.exists():
                shutil.rmtree(dest_dir, ignore_errors=True)
                return jsonify({"error": "Échec de conversion de la vidéo importée en MP4 H.264."}), 400

        meta = {
            "session_id": session_id,
            "type": "uploaded_short",
            "status": "ready",
            "script": {"title": title, "social_caption": caption},
            "video_path": str(final_mp4),
            "social_caption": caption,
        }
        with open(dest_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        size_mb = round(final_mp4.stat().st_size / (1024 * 1024), 1)
        return jsonify({
            "video": {
                "id": session_id,
                "title": title,
                "social_caption": caption,
                "size_mb": size_mb,
            }
        })
    except Exception as e:
        shutil.rmtree(dest_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<render_id>", methods=["DELETE"])
def api_delete_video(render_id):
    if not _is_safe_id(render_id):
        return jsonify({"error": "ID invalide"}), 400
    target = RENDERS_DIR / render_id
    if not target.exists():
        return jsonify({"error": "Vidéo introuvable"}), 404
    shutil.rmtree(target)
    return jsonify({"deleted": render_id})


@app.route("/api/videos/<render_id>/validate", methods=["POST"])
def api_validate_video(render_id):
    if not _is_safe_id(render_id):
        return jsonify({"error": "ID invalide"}), 400
    target = RENDERS_DIR / render_id
    video_file = target / "final_short.mp4"
    if not video_file.exists():
        return jsonify({"error": "Vidéo introuvable"}), 404
    meta_file = target / "metadata.json"
    meta = {}
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    payload = request.json or {}
    if "validated" in payload:
        new_val = bool(payload.get("validated"))
    else:
        new_val = not bool(meta.get("validated", False))
    meta["validated"] = new_val
    fd, tmp_path = tempfile.mkstemp(dir=str(target), prefix=".meta_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, meta_file)
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return jsonify({"error": str(e)}), 500
    return jsonify({"id": render_id, "validated": new_val})


@app.route("/api/voice/preview", methods=["POST"])
def api_voice_preview():
    data = request.json or {}
    voice = (data.get("voice") or "").strip() or None
    try:
        res = VoiceEngine.generate_voice(
            text="Salut, ici ton studio Clipoa. Prêt à fabriquer tes prochains shorts viraux.",
            output_name="studio_voice_preview",
            voice=voice,
        )
        wav = Path(res["audio_wav"])
        if not wav.exists():
            return jsonify({"error": "Échantillon audio introuvable"}), 500
        return jsonify({"audio_url": f"/api/voice/preview-audio?t={int(time.time())}", "engine": res.get("engine", "free")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/voice/preview-audio", methods=["GET"])
def api_voice_preview_audio():
    wav = AUDIO_DIR / "studio_voice_preview.wav"
    if not wav.exists():
        return "Audio not found", 404
    return send_file(str(wav), mimetype="audio/wav", conditional=True)


@app.route("/api/jobs", methods=["GET"])
def api_jobs_list():
    with JOBS_LOCK:
        ordered = sorted(JOBS.values(), key=lambda j: j.get("created_at", 0), reverse=True)[:12]
    return jsonify({"jobs": ordered})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def api_job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Tâche introuvable"}), 404
    return jsonify(job)


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def api_job_dismiss(job_id):
    with JOBS_LOCK:
        JOBS.pop(job_id, None)
        _persist_jobs()
    return jsonify({"dismissed": job_id})


@app.route("/api/jobs/<job_id>/resume", methods=["POST"])
def api_job_resume(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Tâche introuvable"}), 404
        if job.get("status") == "running":
            return jsonify({"error": "Cette tâche est déjà en cours d'exécution"}), 409
        if job.get("kind") not in ("make", "clone", "style_ref", "style_only"):
            return jsonify({"error": "Cette tâche ne supporte pas la reprise automatique"}), 400
    _launch_pipeline_job(job_id)
    return jsonify({"resumed": job_id})


@app.route("/api/presets", methods=["GET", "POST"])
def api_presets():
    if request.method == "GET":
        return jsonify({"presets": list_presets()})
    data = request.json or {}
    if not (data.get("label") or "").strip():
        return jsonify({"error": "Nom du preset requis"}), 400
    saved = save_custom_preset(data)
    return jsonify({"preset": saved, "presets": list_presets()})


@app.route("/api/presets/<preset_id>", methods=["DELETE"])
def api_delete_preset(preset_id):
    if not _is_safe_id(preset_id):
        return jsonify({"error": "ID invalide"}), 400
    ok = delete_custom_preset(preset_id)
    return jsonify({"deleted": ok, "presets": list_presets()})


@app.route("/api/week", methods=["POST"])
def api_week():
    data = request.json or {}
    niche = (data.get("niche") or "").strip()
    engine = (data.get("engine") or "gemini").strip().lower()
    if not niche:
        return jsonify({"error": "Indique ta niche"}), 400
    try:
        plan = LeStratege.plan_weekly_shorts(niche, engine=engine)
        return jsonify({"niche": niche, "engine": engine, "plan": plan})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    try:
        threshold = max(0.5, min(50.0, float(data.get("threshold", 2.0))))
        limit = max(1, min(100, int(data.get("limit", 30))))
    except (ValueError, TypeError):
        return jsonify({"error": "Paramètres threshold ou limit invalides"}), 400
    cookies = data.get("cookies") or None
    if not url:
        return jsonify({"error": "URL manquante"}), 400
    if not url.startswith("@"):
        try:
            url = validate_public_http_url(url)
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
    try:
        res = CompetitorScraper.find_outliers(url, limit=limit, threshold=threshold, cookies_from_browser=cookies)
        return jsonify(res)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-short", methods=["POST"])
def api_analyze_short():
    """
    Télécharge un short concurrent (YouTube Shorts ou TikTok), extrait son script complet
    mot-par-mot (Whisper) et explique POURQUOI il a explosé (Le Cloneur / Claude).
    """
    data = request.json or {}
    url = (data.get("url") or "").strip()
    cookies = data.get("cookies") or None
    if not url:
        return jsonify({"error": "Lien de la vidéo manquant"}), 400
    try:
        url = validate_public_http_url(url)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    try:
        dl_id = f"inspect_{int(time.time())}_{uuid.uuid4().hex[:5]}"
        dl = CompetitorScraper.download_video(url, output_id=dl_id, cookies_from_browser=cookies, extract_frames=False)
        meta = dl.get("metadata", {})
        tr = AudioTranscriber.transcribe(dl["audio_path"])
        analysis = LeCloneur.analyze_recipe(
            transcript=tr.get("text", ""),
            title=meta.get("title") or Path(url).name,
            views=int(meta.get("views") or 0),
        )
        return jsonify({
            "url": url,
            "metadata": meta,
            "transcript": tr.get("text", ""),
            "duration": tr.get("duration", 0),
            "analysis": analysis,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/script-lab/from-competitors", methods=["POST"])
def api_script_lab_from_competitors():
    data = request.json or {}
    outliers = data.get("outliers") or []
    my_niche = (data.get("niche") or "ma chaîne").strip()
    engine = (data.get("engine") or "claude").strip().lower()
    plugin_id = (data.get("plugin_id") or "").strip() or None
    if not outliers:
        return jsonify({"error": "Scanne d'abord un compte concurrent pour obtenir des pépites."}), 400
    try:
        ideas = ScriptExpertAgent.propose_from_outliers(outliers, niche=my_niche, plugin_id=plugin_id, engine=engine)
        return jsonify({"engine": engine, "ideas": ideas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/script-lab/generate", methods=["POST"])
def api_script_lab_generate():
    """Agent Expert Script (Claude ou Gemini) : part de 0, applique un Plugin DA, ou s'inspire d'un concurrent."""
    data = request.json or {}
    try:
        try:
            target_dur = max(15, min(180, int(data.get("target_duration_sec") or 60)))
        except (TypeError, ValueError):
            target_dur = 60
        res = ScriptExpertAgent.generate(
            topic=data.get("topic", ""),
            niche=data.get("niche", ""),
            competitor_url=data.get("competitor_url", ""),
            plugin_id=(data.get("plugin_id") or "").strip() or None,
            target_duration_sec=target_dur,
            engine=(data.get("engine") or "claude").strip().lower(),
        )
        return jsonify({"engine": data.get("engine", "claude"), "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/script-lab/refine", methods=["POST"])
def api_script_lab_refine():
    data = request.json or {}
    if not (data.get("script") or "").strip() or not (data.get("instruction") or "").strip():
        return jsonify({"error": "Script ou consigne de modification manquant"}), 400
    try:
        res = ScriptExpertAgent.refine(
            current_script=data.get("script", ""),
            title=data.get("title", ""),
            instruction=data.get("instruction", ""),
            plugin_id=(data.get("plugin_id") or "").strip() or None,
            engine=(data.get("engine") or "claude").strip().lower(),
        )
        return jsonify({"engine": data.get("engine", "claude"), "data": res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/make-from-script", methods=["POST"])
def api_make_from_script():
    """
    Fabrique un short 1080x1920 directement à partir d'un script personnalisé / modifié par l'utilisateur,
    en appliquant la DA du Plugin de Style choisi si fourni.
    """
    data = request.json or {}
    script_text = (data.get("script_text") or "").strip()
    title = (data.get("title") or "Short personnalisé").strip()
    hook_text = (data.get("hook_screen_text") or title).strip()
    theme = data.get("theme", DEFAULT_THEME)
    subtitle_style = data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
    voice = data.get("voice") or None
    plugin_id = (data.get("plugin_id") or "").strip() or None
    retention_boost = bool(data.get("retention_boost", True))

    if not script_text:
        return jsonify({"error": "Le script est vide"}), 400

    plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=False) if plugin_id else None
    lbl = f"🎨 {plugin['name']} (Mon script) : {title[:32]}" if plugin else f"✍️ Mon script : {title[:40]}"
    params = {
        "topic": title,
        "custom_script": script_text,
        "custom_title": hook_text or title,
        "plugin_id": plugin_id,
        "theme": theme,
        "subtitle_style": subtitle_style,
        "voice": voice,
        "retention_boost": retention_boost,
    }
    job_id = _create_job("make", lbl, params=params)
    _launch_pipeline_job(job_id)
    return jsonify({"job_id": job_id})


@app.route("/api/make", methods=["POST"])
def api_make():
    if request.content_type and "multipart/form-data" in request.content_type:
        topic = (request.form.get("topic") or "").strip()
        custom_script = (request.form.get("custom_script") or "").strip() or None
        custom_title = (request.form.get("custom_title") or "").strip() or None
        plugin_id = (request.form.get("plugin_id") or "").strip() or None
        try:
            target_duration_sec = max(15, min(180, int(request.form.get("target_duration_sec") or 60)))
        except (TypeError, ValueError):
            target_duration_sec = 60
        style = (request.form.get("style") or "").strip() or None
        theme = request.form.get("theme", DEFAULT_THEME)
        subtitle_style = request.form.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
        voice = request.form.get("voice") or None
        use_blender_3d = request.form.get("use_blender_3d", "false").lower() in ("1", "true", "yes", "on")
        retention_boost = request.form.get("retention_boost", "true").lower() in ("1", "true", "yes", "on")
        enable_music = request.form.get("enable_music", "true").lower() in ("1", "true", "yes", "on")
        enable_sfx = request.form.get("enable_sfx", "true").lower() in ("1", "true", "yes", "on")
        engine = (request.form.get("engine") or "claude").strip().lower()
        engine_model = (request.form.get("engine_model") or "").strip() or None
        engine_choice = (request.form.get("engine_choice") or "").strip().lower()
        bg_video = (request.form.get("background_video") or "").strip() or None
        uploaded_bg = request.files.get("bg_file")
        if uploaded_bg and uploaded_bg.filename:
            safe_bg = secure_filename(uploaded_bg.filename) or "bg.mp4"
            if Path(safe_bg).suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
                return jsonify({"error": "Extension de fichier de fond non autorisée."}), 400
            fname = f"broll_{int(time.time())}_{safe_bg}"
            save_path = VIDEOS_DIR / fname
            uploaded_bg.save(str(save_path))
            bg_video = str(save_path)
    else:
        data = request.json or {}
        topic = (data.get("topic") or "").strip()
        custom_script = (data.get("custom_script") or "").strip() or None
        custom_title = (data.get("custom_title") or "").strip() or None
        plugin_id = (data.get("plugin_id") or "").strip() or None
        try:
            target_duration_sec = max(15, min(180, int(data.get("target_duration_sec") or 60)))
        except (TypeError, ValueError):
            target_duration_sec = 60
        style = (data.get("style") or "").strip() or None
        theme = data.get("theme", DEFAULT_THEME)
        subtitle_style = data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
        voice = data.get("voice") or None
        use_blender_3d = bool(data.get("use_blender_3d", False))
        retention_boost = bool(data.get("retention_boost", True))
        enable_music = bool(data.get("enable_music", True))
        enable_sfx = bool(data.get("enable_sfx", True))
        engine = (data.get("engine") or "claude").strip().lower()
        engine_model = (data.get("engine_model") or "").strip() or None
        engine_choice = (data.get("engine_choice") or "").strip().lower()
        bg_video = (data.get("background_video") or "").strip() or None

    if bg_video:
        try:
            bg_video = str(validate_local_media_path(bg_video, [STORAGE_DIR]))
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400

    if not topic and not custom_script:
        return jsonify({"error": "Écris un sujet ou colle ton script"}), 400

    # Si l'utilisateur fournit un script au format Template complet (tableaux Markdown),
    # on extrait les plans (pour le rendu multi-plans) ET les répliques parlées pour la voix off.
    template_shots = []
    if custom_script and "## 3." in custom_script and "|" in custom_script:
        template_shots = extract_shots_from_template(custom_script)
        extracted_spoken = extract_spoken_script_from_template(custom_script)
        if extracted_spoken:
            if not custom_title:
                custom_title = extract_title_from_template(custom_script, fallback=topic or "Mon Short")
            custom_script = extracted_spoken

    plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=False) if plugin_id else None
    display_text = (custom_title or topic or (custom_script or "")[:45])[:40]
    if plugin:
        job_label = f"{plugin['icon']} {plugin['name']} : {display_text}"
    elif custom_script:
        job_label = f"✍️ Mon script : {display_text}"
    else:
        job_label = f"⚡ Short : {display_text}"

    is_3d_job = bool(use_blender_3d or (plugin and (plugin.get("render_mode") == "blender3d" or (plugin.get("production") or {}).get("visual_style"))))
    eng_norm = engine if engine in ("claude", "antigravity") else "claude"
    est_total_sec = estimate_job_seconds(eng_norm, "blender3d" if is_3d_job else "motion", target_duration_sec)
    params = {
        "topic": topic,
        "custom_script": custom_script,
        "custom_title": custom_title,
        "plugin_id": plugin_id,
        "target_duration_sec": target_duration_sec,
        "style": style,
        "background_video": bg_video,
        "theme": theme,
        "subtitle_style": subtitle_style,
        "voice": voice,
        "use_blender_3d": is_3d_job,
        "retention_boost": retention_boost,
        "enable_music": enable_music,
        "enable_sfx": enable_sfx,
        "template_shots": template_shots,
        "engine": eng_norm,
        "engine_model": engine_model,
        "engine_choice": engine_choice,
        "est_total_sec": est_total_sec,
    }
    job_id = _create_job("make", job_label, params=params)
    _launch_pipeline_job(job_id)
    return jsonify({"job_id": job_id})


@app.route("/api/make-like", methods=["POST"])
def api_make_like():
    """Ton script / ton idée + le lien d'une vidéo d'exemple : l'agent reproduit le STYLE de l'exemple."""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    topic = (data.get("topic") or "").strip()
    custom_script = (data.get("custom_script") or "").strip() or None
    if not url:
        return jsonify({"error": "Colle le lien de la vidéo d'exemple (YouTube, Short, Reel, TikTok)."}), 400
    if not topic and not custom_script:
        return jsonify({"error": "Écris ton idée ou colle ton script."}), 400
    try:
        url = validate_public_http_url(url)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    template_shots = []
    custom_title = (data.get("custom_title") or "").strip() or None
    if custom_script and "## 3." in custom_script and "|" in custom_script:
        template_shots = extract_shots_from_template(custom_script)
        spoken = extract_spoken_script_from_template(custom_script)
        if spoken:
            custom_title = custom_title or extract_title_from_template(custom_script, fallback=topic or "Mon Short")
            custom_script = spoken
    engine = (data.get("engine") or "claude").strip().lower()
    engine = engine if engine in ("claude", "antigravity") else "claude"
    try:
        target_duration_sec = max(15, min(180, int(data.get("target_duration_sec") or 60)))
    except (TypeError, ValueError):
        target_duration_sec = 60
    params = {
        "url": url,
        "topic": topic or (custom_title or (custom_script or "")[:60]),
        "custom_script": custom_script,
        "custom_title": custom_title,
        "plugin_id": None,
        "target_duration_sec": target_duration_sec,
        "voice": data.get("voice") or None,
        "theme": DEFAULT_THEME,
        "subtitle_style": DEFAULT_SUBTITLE_STYLE,
        "use_blender_3d": True,
        "retention_boost": True,
        "enable_music": bool(data.get("enable_music", True)),
        "enable_sfx": bool(data.get("enable_sfx", True)),
        "template_shots": template_shots,
        "engine": engine,
        "engine_choice": engine,
        "engine_model": (data.get("engine_model") or "").strip() or None,
        "est_total_sec": estimate_job_seconds(engine, "blender3d", target_duration_sec) + 120,
    }
    label = (custom_title or topic or (custom_script or "")[:40])[:38]
    job_id = _create_job("style_ref", f"🎞️ Même style que l'exemple : {label}", params=params)
    _launch_pipeline_job(job_id)
    return jsonify({"job_id": job_id})


@app.route("/api/plugins/from-reference", methods=["POST"])
def api_plugin_from_reference():
    """Crée seulement un style (plugin) à partir d'une vidéo d'exemple."""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Colle le lien de la vidéo d'exemple."}), 400
    try:
        url = validate_public_http_url(url)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    engine = (data.get("engine") or "claude").strip().lower()
    params = {"url": url, "engine": engine if engine in ("claude", "antigravity") else "claude",
              "engine_choice": engine, "engine_model": (data.get("engine_model") or "").strip() or None}
    job_id = _create_job("style_only", "🎨 Nouveau style depuis une vidéo", params=params)
    _launch_pipeline_job(job_id)
    return jsonify({"job_id": job_id})


@app.route("/api/clone", methods=["POST"])
def api_clone():
    data = request.json or {}
    url = (data.get("url") or "").strip()
    topic = (data.get("topic") or "").strip()
    if not url or not topic:
        return jsonify({"error": "Paramètres manquants (url ou topic)"}), 400
    try:
        url = validate_public_http_url(url)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    params = {
        "url": url,
        "topic": topic,
        "theme": data.get("theme", DEFAULT_THEME),
        "subtitle_style": data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
        "voice": data.get("voice") or None,
        "cookies": data.get("cookies") or None,
    }
    job_id = _create_job("clone", f"🎯 Clonage : {topic[:45]}", params=params)
    _launch_pipeline_job(job_id)
    return jsonify({"job_id": job_id})


@app.route("/api/cut", methods=["POST"])
def api_cut():
    try:
        if request.content_type and "multipart/form-data" in request.content_type:
            uploaded = request.files.get("video")
            source = (request.form.get("source") or "").strip()
            num_clips = int(request.form.get("num_clips", 3))
            crop_mode = request.form.get("crop_mode", "center")
            subtitle_style = request.form.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
            remove_silences = request.form.get("remove_silences", "false").lower() in ("1", "true", "yes", "on")
            if uploaded and uploaded.filename:
                safe_vid = secure_filename(uploaded.filename) or "source.mp4"
                if Path(safe_vid).suffix.lower() not in ALLOWED_MEDIA_EXTENSIONS:
                    return jsonify({"error": "Format vidéo non autorisé."}), 400
                fname = f"{int(time.time())}_{safe_vid}"
                save_path = VIDEOS_DIR / fname
                uploaded.save(str(save_path))
                source = str(save_path)
        else:
            data = request.json or {}
            source = (data.get("source") or "").strip()
            num_clips = int(data.get("num_clips", 3))
            crop_mode = data.get("crop_mode", "center")
            subtitle_style = data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE)
            remove_silences = bool(data.get("remove_silences", False))

        if not source:
            return jsonify({"error": "Importe une vidéo ou colle un lien YouTube"}), 400
        if source.startswith(("http://", "https://")):
            try:
                source = validate_public_http_url(source)
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
        else:
            try:
                source = str(validate_local_media_path(source, [STORAGE_DIR]))
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
        num_clips = max(1, min(10, num_clips))

        job_id = _create_job("cut", "Découpe vidéo filmée (Le Monteur)")

        def _run():
            try:
                _update_job(job_id, 20, "🎙️ Transcription Whisper + analyse des moments viraux...")
                res = ShortCrewPipeline.cut_long_video(
                    source=source,
                    num_clips=num_clips,
                    crop_mode=crop_mode,
                    subtitle_style=subtitle_style,
                    remove_silences=remove_silences,
                )
                _finish_job(job_id, result=res)
            except ClaudeQuotaExceededError as qe:
                _pause_job_quota(job_id, str(qe))
            except Exception as e:
                _finish_job(job_id, error=str(e))

        if not _run_with_job_guard(job_id, _run):
            return jsonify({"error": "Trop de tâches lourdes en cours, patiente quelques instants.", "job_id": job_id}), 429
        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/revise", methods=["POST"])
def api_revise():
    data = request.json or {}
    session_id = (data.get("session_id") or "").strip()
    feedback = (data.get("feedback") or "").strip()
    if not session_id or not feedback:
        return jsonify({"error": "session_id ou feedback manquant"}), 400
    if not _is_safe_id(session_id):
        return jsonify({"error": "session_id invalide"}), 400

    job_id = _create_job("revise", f"Retouche : {feedback[:40]}")

    def _run():
        try:
            _update_job(job_id, 25, "🔄 Claude applique ta retouche ciblée...")
            res = ShortCrewPipeline.revise_short(session_id=session_id, feedback=feedback)
            _finish_job(job_id, result=res)
        except ClaudeQuotaExceededError as qe:
            _pause_job_quota(job_id, str(qe))
        except Exception as e:
            _finish_job(job_id, error=str(e))

    if not _run_with_job_guard(job_id, _run):
        return jsonify({"error": "Trop de tâches lourdes en cours, patiente quelques instants.", "job_id": job_id}), 429
    return jsonify({"job_id": job_id})


@app.route("/api/build")
def api_build():
    return jsonify({"build": APP_BUILD})


def _recent_video_titles(limit: int = 12):
    """Titres des dernières vidéos + jobs, pour éviter que l'IA ressorte toujours la même histoire."""
    titles = []
    try:
        for r in _load_renders()[:limit]:
            t = str((r.get("script") or {}).get("title") or "").strip()
            if t and t not in titles:
                titles.append(t)
    except Exception:
        pass
    try:
        for j in sorted(list(JOBS.values()), key=lambda x: x.get("created_at", 0), reverse=True):
            t = str((j.get("params") or {}).get("custom_title") or (j.get("params") or {}).get("topic") or "").strip()
            if t and t not in titles:
                titles.append(t[:90])
            if len(titles) >= limit:
                break
    except Exception:
        pass
    return titles[:limit]


def _claude_family(model):
    """« claude-opus-5-5-medium » -> « opus » pour le Claude CLI ; None = modèle réglé dans Connexions."""
    m = (model or "").lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return None


@app.route("/api/fabrique/generate-script", methods=["POST"])
def api_fabrique_generate_script():
    """
    Étape 1 de la Fabrique : génère un script complet au format Template (6 sections :
    Fiche projet, Personnages, Le script plan par plan, Musiques à créer, Effets sonores)
    avec Claude Opus 5.5 (Medium) ou Antigravity Gemini 4 Neon (Medium).
    """
    data = request.json or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Décris ton idée avant de générer le script."}), 400
    plugin_id = (data.get("plugin_id") or "").strip() or None
    template_id = (data.get("template_id") or "default").strip() or "default"
    engine = (data.get("engine") or "claude").strip().lower()
    model = (data.get("model") or "").strip() or None
    try:
        target_dur = max(15, min(180, int(data.get("target_duration_sec") or 60)))
    except (TypeError, ValueError):
        target_dur = 60

    da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=False) if plugin_id else ""
    sys_prompt, user_prompt = build_script_generation_prompt(
        topic=topic,
        target_duration_sec=target_dur,
        da_context=da_ctx,
        template_id=template_id,
        avoid_titles=_recent_video_titles() or recent_video_titles(),
    )

    t0 = time.time()
    try:
        agy_connected = bool(AntigravityBridge.check_status().get("connected"))
        use_agy = (engine == "antigravity")  # « Claude » choisi = toujours le Claude CLI (jamais le quota Antigravity)
        if use_agy:
            chosen_model = model or "gemini-4-neon-medium"
            raw = AntigravityBridge.query(user_prompt, system_prompt=sys_prompt, model=chosen_model, timeout=300)
            engine_label = chosen_model
            record_actual_timing("antigravity", "script", time.time() - t0, target_dur)
        else:
            raw = ClaudeBridge.query(user_prompt, system_prompt=sys_prompt, action="script_template", model=_claude_family(model))
            engine_label = f"Claude {ClaudeBridge.check_status().get('model', 'opus').capitalize()}"
            record_actual_timing("claude", "script", time.time() - t0, target_dur)

        template_md = (raw or "").strip()
        title = extract_title_from_template(template_md, fallback=topic[:60])
        spoken = extract_spoken_script_from_template(template_md)

        return jsonify({
            "ok": True,
            "title": title,
            "script": template_md,
            "template_script": template_md,
            "spoken_script": spoken,
            "engine_label": engine_label,
        })
    except ClaudeQuotaExceededError as qe:
        return jsonify({"error": f"Quota Claude atteint ({qe}). Bascule sur Antigravity Neon !"}), 429
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fabrique/generate-script/stream", methods=["POST"])
def api_fabrique_generate_script_stream():
    """
    Streaming SSE en temps réel de la génération du script (Étape 1) :
    envoie chaque morceau de texte (`delta`) + pourcentage d'avancement (`pct`) + étape (`stage`).
    """
    data = request.json or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "Décris ton idée avant de générer le script."}), 400
    plugin_id = (data.get("plugin_id") or "").strip() or None
    template_id = (data.get("template_id") or "default").strip() or "default"
    engine = (data.get("engine") or "claude").strip().lower()
    model = (data.get("model") or "").strip() or None
    try:
        target_dur = max(15, min(180, int(data.get("target_duration_sec") or 60)))
    except (TypeError, ValueError):
        target_dur = 60

    da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=False) if plugin_id else ""
    sys_prompt, user_prompt = build_script_generation_prompt(
        topic=topic,
        target_duration_sec=target_dur,
        da_context=da_ctx,
        template_id=template_id,
        avoid_titles=_recent_video_titles() or recent_video_titles(),
    )

    def _sse(ev_name: str, payload: dict) -> str:
        return f"event: {ev_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _compute_progress(acc_text: str) -> tuple:
        if "## 5." in acc_text:
            return 88, "5/5 · Effets sonores (SFX)"
        if "## 4." in acc_text:
            return 74, "4/5 · Musiques à créer"
        if "## 3." in acc_text:
            return min(70, 38 + len(acc_text) // 180), "3/5 · Écriture du script plan par plan"
        if "## 2." in acc_text:
            return 26, "2/5 · Fiches personnages"
        if "## 1." in acc_text:
            return 14, "1/5 · Fiche projet"
        return min(85, 10 + len(acc_text) // 60), "Rédaction en direct…"

    def _generate():
        yield _sse("progress", {"pct": 6, "stage": "Connexion au modèle IA…"})
        t0 = time.time()
        try:
            agy_connected = bool(AntigravityBridge.check_status().get("connected"))
            use_agy = (engine == "antigravity")  # « Claude » choisi = toujours le Claude CLI (jamais le quota Antigravity)
            acc = []
            if use_agy:
                chosen_model = model or "gemini-4-neon-medium"
                engine_label = chosen_model
                for delta in AntigravityBridge.stream_query(user_prompt, system_prompt=sys_prompt, model=chosen_model, timeout=300):
                    acc.append(delta)
                    full_so_far = "".join(acc)
                    pct, stage = _compute_progress(full_so_far)
                    yield _sse("chunk", {"delta": delta, "pct": pct, "stage": stage})
                record_actual_timing("antigravity", "script", time.time() - t0, target_dur)
            else:
                engine_label = f"Claude {ClaudeBridge.check_status().get('model', 'opus').capitalize()}"
                yield _sse("progress", {"pct": 12, "stage": f"{engine_label} rédige en direct…"})
                for delta in ClaudeBridge.stream_query(user_prompt, system_prompt=sys_prompt, action="script_template", model=_claude_family(model), timeout=300):
                    acc.append(delta)
                    full_so_far = "".join(acc)
                    pct, stage = _compute_progress(full_so_far)
                    yield _sse("chunk", {"delta": delta, "pct": pct, "stage": stage})
                record_actual_timing("claude", "script", time.time() - t0, target_dur)

            template_md = "".join(acc).strip()
            title = extract_title_from_template(template_md, fallback=topic[:60])
            spoken = extract_spoken_script_from_template(template_md)
            yield _sse("done", {
                "ok": True,
                "pct": 100,
                "stage": "✓ Script prêt",
                "title": title,
                "script": template_md,
                "template_script": template_md,
                "spoken_script": spoken,
                "engine_label": engine_label,
            })
        except ClaudeQuotaExceededError as qe:
            yield _sse("error", {"error": f"Quota Claude atteint ({qe}). Bascule sur Antigravity Neon !"})
        except Exception as e:
            yield _sse("error", {"error": str(e)})

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/fabrique/refine-script", methods=["POST"])
def api_fabrique_refine_script():
    """
    Permet à l'utilisateur de demander à l'IA de remodifier le script généré
    en conservant strictement le Template de script vidéo.
    """
    data = request.json or {}
    current_script = (data.get("current_script") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    if not current_script:
        return jsonify({"error": "Aucun script à modifier."}), 400
    if not instruction:
        return jsonify({"error": "Écris la modification que tu veux demander à l'IA."}), 400

    plugin_id = (data.get("plugin_id") or "").strip() or None
    template_id = (data.get("template_id") or "default").strip() or "default"
    engine = (data.get("engine") or "claude").strip().lower()
    model = (data.get("model") or "").strip() or None

    da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=False) if plugin_id else ""
    sys_prompt, user_prompt = build_script_refinement_prompt(
        current_script=current_script,
        instruction=instruction,
        da_context=da_ctx,
        template_id=template_id,
    )

    try:
        agy_connected = bool(AntigravityBridge.check_status().get("connected"))
        use_agy = (engine == "antigravity")  # « Claude » choisi = toujours le Claude CLI (jamais le quota Antigravity)
        if use_agy:
            chosen_model = model or "gemini-4-neon-medium"
            raw = AntigravityBridge.query(user_prompt, system_prompt=sys_prompt, model=chosen_model, timeout=180)
            engine_label = chosen_model
        else:
            raw = ClaudeBridge.query(user_prompt, system_prompt=sys_prompt, action="script_template_refine", model=_claude_family(model))
            engine_label = f"Claude {ClaudeBridge.check_status().get('model', 'opus').capitalize()}"

        template_md = (raw or "").strip()
        title = extract_title_from_template(template_md, fallback="Mon Short")
        spoken = extract_spoken_script_from_template(template_md)
        return jsonify({
            "ok": True,
            "title": title,
            "script": template_md,
            "template_script": template_md,
            "spoken_script": spoken,
            "engine_label": engine_label,
        })
    except ClaudeQuotaExceededError as qe:
        return jsonify({"error": f"Quota Claude atteint ({qe}). Bascule sur Antigravity Neon !"}), 429
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/antigravity/status", methods=["GET"])
def api_antigravity_status():
    probe = request.args.get("probe", "0") in ("1", "true", "yes")
    return jsonify(AntigravityBridge.check_status(live_probe=probe))


@app.route("/api/antigravity/login", methods=["POST"])
def api_antigravity_login():
    return jsonify(AntigravityBridge.start_cli_login())


@app.route("/api/antigravity/switch", methods=["POST"])
def api_antigravity_switch():
    return jsonify(AntigravityBridge.switch_account())


@app.route("/api/antigravity/model", methods=["POST"])
def api_antigravity_model():
    data = request.json or {}
    mid = (data.get("model") or "").strip()
    if not mid:
        return jsonify({"error": "Modèle manquant"}), 400
    return jsonify(AntigravityBridge.set_model(mid))


@app.route("/api/timings", methods=["GET"])
def api_timings():
    return jsonify(get_learned_estimates())


@app.route("/api/script-templates", methods=["GET", "POST"])
def api_script_templates():
    if request.method == "GET":
        return jsonify({"templates": list_script_templates()})
    try:
        if request.content_type and "multipart/form-data" in request.content_type:
            up = request.files.get("file")
            name = (request.form.get("name") or (up.filename if up else "") or "Mon template").strip()
            content = up.read().decode("utf-8", errors="replace") if up else ""
        else:
            data = request.json or {}
            name = (data.get("name") or "Mon template").strip()
            content = data.get("content") or ""
        item = save_custom_script_template(name, content)
        return jsonify({"ok": True, "template": item, "templates": list_script_templates()})
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/script-templates/<tid>", methods=["DELETE"])
def api_delete_script_template(tid):
    ok = delete_custom_script_template(tid)
    if not ok:
        return jsonify({"error": "Template introuvable ou protégé"}), 404
    return jsonify({"ok": True, "templates": list_script_templates()})


@app.route("/api/assistant/help", methods=["POST"])
def api_assistant_help():
    """
    Assistant d'aide IA intégré à la barre des tâches Clipoa.
    Utilise le modèle Claude, Antigravity ou Gemini choisi par l'utilisateur s'il est connecté.
    """
    data = request.json or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "Écris ta question pour obtenir de l'aide."}), 400
    if len(message) > 2500:
        message = message[:2500]

    provider_req = (data.get("provider") or "auto").strip().lower()
    model_req = (data.get("model") or "").strip()
    current_view = (data.get("current_view") or "accueil").strip().lower()
    history = data.get("history") if isinstance(data.get("history"), list) else []

    claude_st = ClaudeBridge.check_status()
    gemini_st = GeminiStudio.get_status()
    agy_st = AntigravityBridge.check_status()
    claude_ok = bool(claude_st.get("connected"))
    gemini_ok = bool(gemini_st.get("connected"))
    agy_ok = bool(agy_st.get("connected"))
    conn_map = {"claude": claude_ok, "gemini": gemini_ok, "antigravity": agy_ok}

    # Sélection du fournisseur
    chosen_provider = provider_req
    if chosen_provider == "auto":
        if claude_ok:
            chosen_provider = "claude"
        elif agy_ok:
            chosen_provider = "antigravity"
        elif gemini_ok:
            chosen_provider = "gemini"
        else:
            chosen_provider = "none"

    if chosen_provider == "claude" and not claude_ok:
        return jsonify({
            "ok": False,
            "needs_connection": True,
            "connected_providers": conn_map,
            "reply": "Ton compte Claude n'est pas encore connecté. Clique sur « Connexions » pour brancher Claude (ou choisis Antigravity / Gemini dans le sélecteur).",
        }), 200
    if chosen_provider == "antigravity" and not agy_ok:
        return jsonify({
            "ok": False,
            "needs_connection": True,
            "connected_providers": conn_map,
            "reply": "Antigravity CLI n'est pas encore connecté. Clique sur « Connexions » → « Connecter Antigravity » pour te connecter une seule fois.",
        }), 200
    if chosen_provider == "gemini" and not gemini_ok:
        return jsonify({
            "ok": False,
            "needs_connection": True,
            "connected_providers": conn_map,
            "reply": "Ta clé Gemini n'est pas encore branchée. Clique sur « Connexions » pour coller ta clé gratuite Google AI Studio (ou choisis Claude / Antigravity).",
        }), 200
    if chosen_provider == "none":
        return jsonify({
            "ok": False,
            "needs_connection": True,
            "connected_providers": conn_map,
            "reply": "Connecte Claude, Antigravity ou Gemini dans « Connexions » pour activer l'aide IA en direct sur Clipoa.",
        }), 200

    plugins = StylePluginStore.list_plugins(include_script_body=False)
    styles_str = ", ".join(f"{p['name']} ({p.get('est_time_label', '~1 min')})" for p in plugins) or "aucun"

    system_prompt = (
        "Tu es l'assistant d'aide intégré de Clipoa, une application locale de création de vidéos courtes (Shorts, TikTok, Reels).\n"
        "Réponds en français, de manière claire, concrète, amicale et concise (4 à 8 lignes max, étapes numérotées si utile).\n"
        "Guide l'utilisateur uniquement sur les vraies fonctionnalités de Clipoa :\n"
        "- Accueil : vue rapide, shorts à valider, boîte de création rapide.\n"
        "- Fabrique : créer un short à partir d'une idée OU coller son propre script mot pour mot (« J'ai mon script »), "
        "choisir la durée cible (30s, 45s, 1 min, 1m30, 2 min), choisir un style DA, un moteur (Claude, Antigravity ou Gemini), la 3D Blender, la voix, les sous-titres Submagic, et le Mode Nuit.\n"
        f"- Plugins DA (Styles disponibles : {styles_str}) : chaque style a une image d'aperçu, une Direction Artistique (DA), "
        "une estimation temps + tokens/quota (calibrée sur 1 min et ajustée selon la durée), et on peut créer ses propres plugins avec planches de modèles et scripts.\n"
        "- Montage : découper une vidéo longue (YouTube ou fichier) en shorts 9:16.\n"
        "- Concurrents : coller un lien TikTok/Short ou @compte pour analyser et copier la structure.\n"
        "- Mes vidéos : visionner, valider en 1 clic, retoucher avec ses mots, télécharger MP4.\n"
        "- Publier : programmer et auto-publier sur YouTube, TikTok, Instagram, Facebook.\n"
        "- Connexions : brancher Claude Pro/Max, Antigravity CLI (agy), Gemini gratuit (Google AI Studio), ElevenLabs, Blender 3D et réseaux sociaux.\n"
        "Ne mentionne jamais de fonctions qui n'existent pas. Si l'utilisateur demande comment faire une action, indique le nom exact de l'onglet et du bouton."
    )

    conv_lines = []
    for turn in history[-6:]:
        if not isinstance(turn, dict):
            continue
        role = "Utilisateur" if turn.get("role") == "user" else "Assistant"
        txt = str(turn.get("text") or "").strip()[:500]
        if txt:
            conv_lines.append(f"{role} : {txt}")
    history_block = ("\n".join(conv_lines) + "\n") if conv_lines else ""
    user_prompt = f"Onglet actuel de l'utilisateur : {current_view}\n{history_block}Utilisateur : {message}\nRéponds directement et utilement :"

    try:
        if chosen_provider == "claude":
            c_model = (model_req or claude_st.get("model") or "sonnet").lower()
            if c_model not in ("opus", "sonnet", "haiku"):
                c_model = claude_st.get("model") or "sonnet"
            reply = ClaudeBridge.query(user_prompt, system_prompt=system_prompt, action="help_assistant", model=c_model)
            label = f"Claude {c_model.capitalize()}"
            used_model = c_model
        elif chosen_provider == "antigravity":
            a_model = model_req or agy_st.get("model") or ""
            reply = AntigravityBridge.query(user_prompt, system_prompt=system_prompt, model=a_model or None, timeout=90)
            label = f"Antigravity ({a_model})" if a_model else "Antigravity"
            used_model = a_model
        else:
            g_model = model_req or gemini_st.get("model") or "gemini-3-flash-preview"
            reply = GeminiStudio.chat_text(user_prompt, system_prompt=system_prompt, model=g_model)
            label = next((m["label"].split("(")[0].strip() for m in GEMINI_MODELS if m["id"] == g_model), g_model)
            used_model = g_model

        return jsonify({
            "ok": True,
            "reply": (reply or "").strip(),
            "provider": chosen_provider,
            "model": used_model,
            "model_label": label,
            "connected_providers": conn_map,
        })
    except ClaudeQuotaExceededError as qe:
        return jsonify({
            "ok": False,
            "error": f"Quota Claude atteint ({qe}). Bascule sur Antigravity ou Gemini dans la barre !",
            "connected_providers": conn_map,
        }), 429
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
            "connected_providers": conn_map,
        }), 500


@app.route("/api/system/health", methods=["GET"])
def api_system_health():
    return jsonify({
        "ok": True,
        "storage": get_storage_health(STORAGE_DIR),
        "jobs_guard": JOB_GUARD.stats(),
        "security": {
            "bind_host": CLIPOA_HOST,
            "lan_exposed": CLIPOA_HOST == "0.0.0.0",
            "lan_token_required": bool(_LAN_ACCESS_TOKEN),
            "temp_ttl_days": CLIPOA_TEMP_TTL_DAYS,
        },
    })


@app.route("/api/system/cleanup", methods=["POST"])
def api_system_cleanup():
    data = request.json or {}
    try:
        days = max(1, min(90, int(data.get("max_age_days", CLIPOA_TEMP_TTL_DAYS))))
    except (TypeError, ValueError):
        return jsonify({"error": "max_age_days invalide"}), 400
    res = cleanup_temp_storage(DOWNLOADS_DIR, AUDIO_DIR, max_age_days=days)
    return jsonify({"ok": True, "cleanup": res, "storage": get_storage_health(STORAGE_DIR)})


def run_app(port=8080):
    harden_sensitive_files(STORAGE_DIR)
    cleanup_res = cleanup_temp_storage(DOWNLOADS_DIR, AUDIO_DIR, max_age_days=CLIPOA_TEMP_TTL_DAYS)
    FreeSocialPublisher.start_scheduler()
    NightFactory.start_worker()
    bind_host = CLIPOA_HOST
    print(f"\n🚀 Clipoa démarré (sécurisé · Pulse & Gemini/Veo intégrés) !")
    print(f"   💻 Sur ton Mac       : http://localhost:{port}")
    if bind_host == "0.0.0.0":
        lan_ip = get_lan_ip()
        if _LAN_ACCESS_TOKEN:
            print(f"   📱 Accès LAN sécurisé: http://{lan_ip}:{port}/?token={_LAN_ACCESS_TOKEN}  (même Wi-Fi)")
        else:
            print(f"   📱 Sur ton Téléphone : http://{lan_ip}:{port}  (même Wi-Fi)")
    else:
        print(f"   🔒 Mode local strict : écoute uniquement sur 127.0.0.1 (CLIPOA_ALLOW_LAN=1 pour le Wi-Fi)")
    if cleanup_res.get("removed_items"):
        print(f"   🧹 Nettoyage auto    : {cleanup_res['removed_items']} fichier(s) temp supprimé(s) ({cleanup_res['reclaimed_mb']} Mo libérés)")
    print()
    app.run(host=bind_host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_app()
