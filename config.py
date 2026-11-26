import os
import shutil
import sys
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent


def _resolve_data_dir() -> Path:
    """Dossier de données persistant (storage/, runtime/).

    - Sur Mac / copie de dev : identique à BASE_DIR (aucun changement).
    - Si CLIPOA_DATA_DIR est défini (installateur Windows ou MSIX) : utilise ce dossier.
    - Sur Windows MSIX (WindowsApps en lecture seule) : %LOCALAPPDATA%\\Clipoa.
    """
    env_dir = os.getenv("CLIPOA_DATA_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    if sys.platform == "win32":
        from core.platform_win import default_data_dir, is_store_app
        if is_store_app(BASE_DIR):
            return default_data_dir()
    return BASE_DIR


DATA_DIR = _resolve_data_dir()
STORAGE_DIR = DATA_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
AUDIO_DIR = STORAGE_DIR / "audio"
VIDEOS_DIR = STORAGE_DIR / "videos"
RENDERS_DIR = STORAGE_DIR / "renders"
TRANSCRIPTS_DIR = STORAGE_DIR / "transcripts"

for p in [DOWNLOADS_DIR, AUDIO_DIR, VIDEOS_DIR, RENDERS_DIR, TRANSCRIPTS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Binaries (portable across machines — never hardcode a single user's home path)
_IS_WIN = sys.platform == "win32"
VENV_BIN = BASE_DIR / "venv" / ("Scripts" if _IS_WIN else "bin")
RUNTIME_DIR = DATA_DIR / "runtime"


def _bundled_ffmpeg() -> str:
    """ffmpeg livré par le paquet Python imageio-ffmpeg (absent du MSIX Windows pour la GPL)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def resolve_ffmpeg_path() -> str:
    """Chemin de ffmpeg : runtime ClipRoll → venv → PATH → imageio-ffmpeg (si présent)."""
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    runtime_ff = RUNTIME_DIR / "ffmpeg" / exe_name
    if runtime_ff.exists():
        return str(runtime_ff)
    venv_ff = VENV_BIN / exe_name
    if venv_ff.exists():
        return str(venv_ff)
    return shutil.which("ffmpeg") or _bundled_ffmpeg()


def resolve_blender_path() -> str:
    """Chemin de Blender : env → runtime ClipRoll → système (Mac / Windows)."""
    env_bl = os.getenv("BLENDER_PATH")
    if env_bl:
        return env_bl
    if sys.platform == "win32":
        rt = RUNTIME_DIR / "blender" / "blender.exe"
        if rt.exists():
            return str(rt)
        from core.platform_win import find_system_blender
        return find_system_blender() or str(rt)
    rt = RUNTIME_DIR / "Blender.app" / "Contents" / "MacOS" / "Blender"
    if rt.exists():
        return str(rt)
    found = shutil.which("blender")
    if found:
        return found
    mac_app = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if mac_app.exists():
        return str(mac_app)
    return str(rt)  # Blender installé automatiquement par ClipRoll (core/tools_setup.py)


FFMPEG_PATH = resolve_ffmpeg_path()
_YT_DLP_EXE = "yt-dlp.exe" if _IS_WIN else "yt-dlp"
YT_DLP_PATH = str(VENV_BIN / _YT_DLP_EXE) if (VENV_BIN / _YT_DLP_EXE).exists() else (shutil.which("yt-dlp") or "yt-dlp")
_DEFAULT_CLAUDE_CLI = shutil.which("claude") or str(Path.home() / ".local" / "bin" / ("claude.exe" if _IS_WIN else "claude"))
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", _DEFAULT_CLAUDE_CLI)
_RUNTIME_BLENDER = (RUNTIME_DIR / "blender" / "blender.exe") if _IS_WIN else (RUNTIME_DIR / "Blender.app" / "Contents" / "MacOS" / "Blender")
BLENDER_PATH = resolve_blender_path()

# Security, Network & Resource Guardrails
CLIPOA_ALLOW_LAN = os.getenv("CLIPOA_ALLOW_LAN", "false").lower() in ("1", "true", "yes")
CLIPOA_HOST = os.getenv("CLIPOA_HOST", "0.0.0.0" if CLIPOA_ALLOW_LAN else "127.0.0.1")
CLIPOA_ACCESS_TOKEN = os.getenv("CLIPOA_ACCESS_TOKEN", "").strip()
CLIPOA_MAX_CONCURRENT_JOBS = max(1, int(os.getenv("CLIPOA_MAX_CONCURRENT_JOBS", "2")))
CLIPOA_MAX_ACTIVE_JOBS = max(CLIPOA_MAX_CONCURRENT_JOBS, int(os.getenv("CLIPOA_MAX_ACTIVE_JOBS", "6")))
CLIPOA_MAX_DOWNLOAD_SIZE = os.getenv("CLIPOA_MAX_DOWNLOAD_SIZE", "750M")
CLIPOA_TEMP_TTL_DAYS = max(1, int(os.getenv("CLIPOA_TEMP_TTL_DAYS", "7")))

# Claude Engine
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
USE_CLAUDE_CLI = os.getenv("USE_CLAUDE_CLI", "true").lower() in ("1", "true", "yes")

# TTS Defaults (Free local Neural TTS via edge-tts)
DEFAULT_TTS_VOICE = os.getenv("DEFAULT_TTS_VOICE", "fr-FR-VivienneMultilingualNeural")
# Alternatives: "fr-FR-DeniseNeural", "fr-FR-HenriNeural", "fr-FR-EloiseNeural"

# External APIs (Optional)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
POSTIZ_API_URL = os.getenv("POSTIZ_API_URL", "http://localhost:5000/api/v1")
POSTIZ_API_KEY = os.getenv("POSTIZ_API_KEY", "")

# Outlier Detection & Scraper Defaults
OUTLIER_THRESHOLD = float(os.getenv("OUTLIER_THRESHOLD", "2.0"))  # >= 2x account median/average views
YT_DLP_COOKIES_BROWSER = os.getenv("YT_DLP_COOKIES_BROWSER", "")  # e.g. "chrome", "safari", "firefox"

# Video Composition Defaults
DEFAULT_THEME = os.getenv("DEFAULT_THEME", "dark_luxury")
DEFAULT_SUBTITLE_STYLE = os.getenv("DEFAULT_SUBTITLE_STYLE", "submagic_yellow")
