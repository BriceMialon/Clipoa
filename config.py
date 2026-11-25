import os
import shutil
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
DOWNLOADS_DIR = STORAGE_DIR / "downloads"
AUDIO_DIR = STORAGE_DIR / "audio"
VIDEOS_DIR = STORAGE_DIR / "videos"
RENDERS_DIR = STORAGE_DIR / "renders"
TRANSCRIPTS_DIR = STORAGE_DIR / "transcripts"

for p in [DOWNLOADS_DIR, AUDIO_DIR, VIDEOS_DIR, RENDERS_DIR, TRANSCRIPTS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Binaries (portable across machines — never hardcode a single user's home path)
VENV_BIN = BASE_DIR / "venv" / "bin"
RUNTIME_DIR = BASE_DIR / "runtime"


def _bundled_ffmpeg() -> str:
    """ffmpeg livré par le paquet Python imageio-ffmpeg (aucune installation à faire pour un nouvel utilisateur)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG_PATH = str(VENV_BIN / "ffmpeg") if (VENV_BIN / "ffmpeg").exists() else (shutil.which("ffmpeg") or _bundled_ffmpeg())
YT_DLP_PATH = str(VENV_BIN / "yt-dlp") if (VENV_BIN / "yt-dlp").exists() else (shutil.which("yt-dlp") or "yt-dlp")
_DEFAULT_CLAUDE_CLI = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", _DEFAULT_CLAUDE_CLI)
_RUNTIME_BLENDER = RUNTIME_DIR / "Blender.app" / "Contents" / "MacOS" / "Blender"
BLENDER_PATH = os.getenv("BLENDER_PATH") or shutil.which("blender") or (
    "/Applications/Blender.app/Contents/MacOS/Blender" if Path("/Applications/Blender.app/Contents/MacOS/Blender").exists()
    else str(_RUNTIME_BLENDER)  # Blender installé automatiquement par Clipoa (core/tools_setup.py)
)

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
