# -*- coding: utf-8 -*-
"""
Outils de fabrication prêts à l'emploi pour un nouvel utilisateur (aucune commande à taper).

- ffmpeg : celui du système, sinon téléchargé depuis les builds officiels (Windows MSIX, hors GPL)
  ou livré par imageio-ffmpeg (Mac / dev).
- yt-dlp, Whisper, voix Edge : paquets Python installés dans le venv. Le modèle Whisper « base »
  est stocké dans runtime/models/faster-whisper-base (survit aux mises à jour).
- Blender (styles 3D Roblox, 2D × Monde 3D, Explainer…) : téléchargé depuis blender.org
  (vérifié par SHA-256) et rangé dans runtime/ sans droits administrateur.
- Sur Microsoft Store (MSIX) : aucun téléchargement silencieux au démarrage ; l'utilisateur
  valide l'installation des outils dans l'assistant de premier lancement.
"""
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

import config
from config import RUNTIME_DIR, YT_DLP_PATH
from core.platform_win import is_store_app, subprocess_kwargs

# Blender 5 = Mac Apple Silicon & Windows x64 ; Mac Intel prend la dernière 4.5 LTS
BLENDER_CANDIDATES_ARM = [("5.3", "5.3.0"), ("5.2", "5.2.0")]
BLENDER_CANDIDATES_X64 = [("4.5", "4.5.5")]
BLENDER_CANDIDATES_WIN = [("5.3", "5.3.0"), ("5.2", "5.2.0"), ("4.5", "4.5.5")]

# FFmpeg Windows x64 (source officielle gyan.dev — release essentials, HTTPS)
FFMPEG_WIN_URL = os.getenv(
    "CLIPOA_FFMPEG_WIN_URL",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
)
FFMPEG_WIN_SHA256_URL = os.getenv(
    "CLIPOA_FFMPEG_WIN_SHA256_URL",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
)
_ALLOWED_FFMPEG_PREFIXES = (
    "https://www.gyan.dev/ffmpeg/builds/",
    "https://github.com/BtbN/FFmpeg-Builds/releases/",
)

# Modèle Whisper base (révision Hugging Face figée ou surchargée par env)
WHISPER_REPO = "Systran/faster-whisper-base"

_STATE: Dict[str, Dict[str, Any]] = {
    "blender": {"installing": False, "progress": 0, "message": "", "error": ""},
    "ffmpeg": {"installing": False, "progress": 0, "message": "", "error": ""},
    "whisper": {"installing": False, "progress": 0, "message": "", "error": ""},
}
_LOCK = threading.Lock()


def _runs(path: str, *args: str) -> bool:
    try:
        return subprocess.run([path, *args], capture_output=True, timeout=20, **subprocess_kwargs()).returncode == 0
    except Exception:
        return False


def _module_ok(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _refresh_config_paths() -> None:
    """Met à jour config.BLENDER_PATH et config.FFMPEG_PATH après une installation à chaud."""
    config.BLENDER_PATH = config.resolve_blender_path()
    config.FFMPEG_PATH = config.resolve_ffmpeg_path()


def blender_ready() -> bool:
    path = config.resolve_blender_path()
    return bool(path) and os.path.exists(path)


def ffmpeg_ready() -> bool:
    path = config.resolve_ffmpeg_path()
    return _runs(path, "-version")


def whisper_model_dir() -> Path:
    custom = os.getenv("CLIPOA_WHISPER_DIR", "").strip()
    if custom:
        return Path(custom)
    return RUNTIME_DIR / "models" / "faster-whisper-base"


def whisper_ready() -> bool:
    if not _module_ok("faster_whisper"):
        return False
    # En mode Store/MSIX, on vérifie aussi que le modèle local est téléchargé dans runtime/
    if is_store_app():
        return (whisper_model_dir() / "model.bin").exists()
    return True


def status() -> Dict[str, Any]:
    sys_name = platform.system()
    on_win = sys_name == "Windows" or sys.platform == "win32"
    on_mac = sys_name == "Darwin" or sys.platform == "darwin"
    store = is_store_app()
    tools = {
        "ffmpeg": {
            "label": "Montage vidéo (ffmpeg)",
            "ok": ffmpeg_ready(),
            "auto": on_win,
            "source": "gyan.dev (builds officiels FFmpeg)",
            **_STATE["ffmpeg"],
        },
        "yt_dlp": {"label": "Lecture des vidéos d'exemple (yt-dlp)", "ok": _runs(YT_DLP_PATH, "--version"), "auto": True},
        "whisper": {
            "label": "Sous-titres synchronisés (Whisper)",
            "ok": whisper_ready(),
            "auto": store or on_win,
            "source": "Hugging Face (Systran/faster-whisper-base)",
            **_STATE["whisper"],
        },
        "voice": {"label": "Voix gratuite (Edge)", "ok": _module_ok("edge_tts"), "auto": True},
        "blender": {
            "label": "Scènes 3D (Blender)",
            "ok": blender_ready(),
            "auto": on_mac or on_win,
            "source": "download.blender.org",
            **_STATE["blender"],
        },
    }
    try:
        from core import cine_setup
        tools["cine"] = {"label": "Moteur Ciné haute qualité", "ok": bool(cine_setup.is_ready()), "auto": False, "optional": True}
    except Exception:
        pass
    return {
        "tools": tools,
        "all_ok": all(t["ok"] for k, t in tools.items() if not t.get("optional")),
        "store_app": store,
    }


def _fetch_blender_sha256(major: str, full: str, filename: str) -> str:
    """Récupère l'empreinte SHA-256 officielle sur download.blender.org."""
    sha_url = f"https://download.blender.org/release/Blender{major}/blender-{full}.sha256"
    r = requests.get(sha_url, timeout=15)
    r.raise_for_status()
    for line in r.text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    raise RuntimeError(f"Empreinte SHA-256 introuvable pour {filename} sur blender.org.")


def _blender_download_spec() -> Tuple[str, str, str, str]:
    """Renvoie (url, filename, version_full, expected_sha256) pour la plateforme courante."""
    if sys.platform == "win32" or platform.system() == "Windows":
        for major, full in BLENDER_CANDIDATES_WIN:
            filename = f"blender-{full}-windows-x64.zip"
            url = f"https://download.blender.org/release/Blender{major}/{filename}"
            try:
                if requests.head(url, timeout=10, allow_redirects=True).status_code == 200:
                    sha = _fetch_blender_sha256(major, full, filename)
                    return url, filename, full, sha
            except Exception:
                continue
        raise RuntimeError("Impossible de trouver Blender Windows sur blender.org.")

    cands = BLENDER_CANDIDATES_ARM if platform.machine() == "arm64" else BLENDER_CANDIDATES_X64
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    for major, full in cands:
        filename = f"blender-{full}-macos-{arch}.dmg"
        url = f"https://download.blender.org/release/Blender{major}/{filename}"
        try:
            if requests.head(url, timeout=10, allow_redirects=True).status_code == 200:
                sha = _fetch_blender_sha256(major, full, filename)
                return url, filename, full, sha
        except Exception:
            continue
    raise RuntimeError("Impossible de trouver le téléchargement de Blender sur blender.org.")


def _blender_url() -> str:
    """Compatibilité ascendante : renvoie l'URL Blender de la plateforme."""
    url, _, _, _ = _blender_download_spec()
    return url


def _download_verified(url: str, dest: Path, expected_sha: str, st: Dict[str, Any], label: str) -> None:
    """Télécharge en HTTPS et vérifie strictement le SHA-256."""
    if not url.startswith("https://"):
        raise RuntimeError("Téléchargement refusé : HTTPS obligatoire.")
    h = hashlib.sha256()
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    st["progress"] = max(1, min(90, int(90 * done / total)))
                    st["message"] = f"Téléchargement de {label}… {done >> 20} / {total >> 20} Mo"
    if expected_sha and h.hexdigest().lower() != expected_sha.lower():
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"{label} téléchargé est corrompu (empreinte SHA-256 différente).")


def safe_extract_zip(archive: Path, dest: Path) -> None:
    """Extrait un ZIP sans jamais écrire hors de dest (protection zip-slip)."""
    dest = dest.resolve()
    with zipfile.ZipFile(archive, "r") as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            if target != dest and dest not in target.parents:
                raise RuntimeError(f"Chemin interdit dans l'archive : {info.filename}")
        zf.extractall(dest)


def _install_blender_windows() -> None:
    st = _STATE["blender"]
    st.update(progress=1, message="Recherche de la dernière version de Blender…", error="")
    url, _, full_ver, expected_sha = _blender_download_spec()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    archive = RUNTIME_DIR / "blender_download.zip"
    _download_verified(url, archive, expected_sha, st, f"Blender {full_ver}")

    st.update(progress=92, message="Extraction de Blender…")
    tmp_dir = Path(tempfile.mkdtemp(prefix="clipoa_blender_", dir=str(RUNTIME_DIR)))
    new_dir = RUNTIME_DIR / "blender.new"
    final_dir = RUNTIME_DIR / "blender"
    try:
        safe_extract_zip(archive, tmp_dir)
        # L'archive officielle contient un dossier racine blender-X.Y.Z-windows-x64/
        exe_matches = list(tmp_dir.rglob("blender.exe"))
        if not exe_matches:
            raise RuntimeError("blender.exe introuvable dans l'archive Blender.")
        extracted_root = exe_matches[0].parent
        shutil.rmtree(new_dir, ignore_errors=True)
        shutil.move(str(extracted_root), str(new_dir))
        shutil.rmtree(final_dir, ignore_errors=True)
        new_dir.rename(final_dir)
        (RUNTIME_DIR / "blender_version").write_text(full_ver + "\n", encoding="utf-8")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        archive.unlink(missing_ok=True)
    _refresh_config_paths()
    st.update(progress=100, message="Blender est prêt.")


def _install_blender_macos() -> None:
    st = _STATE["blender"]
    st.update(progress=1, message="Recherche de la dernière version de Blender…", error="")
    url, _, full_ver, expected_sha = _blender_download_spec()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    dmg = RUNTIME_DIR / "blender_download.dmg"
    _download_verified(url, dmg, expected_sha, st, f"Blender {full_ver}")

    st.update(progress=92, message="Installation de Blender…")
    mnt = Path(tempfile.mkdtemp(prefix="clipoa_blender_"))
    try:
        subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-quiet", "-mountpoint", str(mnt)], check=True, timeout=300)
        src = mnt / "Blender.app"
        dest = RUNTIME_DIR / "Blender.app"
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(["cp", "-R", str(src), str(dest)], check=True, timeout=600)
        (RUNTIME_DIR / "blender_version").write_text(full_ver + "\n", encoding="utf-8")
    finally:
        subprocess.run(["hdiutil", "detach", str(mnt), "-quiet", "-force"], timeout=120)
        try:
            dmg.unlink()
        except OSError:
            pass
    _refresh_config_paths()
    st.update(progress=100, message="Blender est prêt.")


def _install_blender() -> None:
    if sys.platform == "win32" or platform.system() == "Windows":
        _install_blender_windows()
    else:
        _install_blender_macos()


def _install_ffmpeg_windows() -> None:
    """Télécharge ffmpeg.exe (+ ffprobe.exe) depuis les builds officiels et vérifie le SHA-256."""
    st = _STATE["ffmpeg"]
    st.update(progress=1, message="Recherche de FFmpeg…", error="")
    url = FFMPEG_WIN_URL
    if not any(url.startswith(p) for p in _ALLOWED_FFMPEG_PREFIXES):
        raise RuntimeError("Adresse de FFmpeg non autorisée.")

    expected_sha = ""
    if FFMPEG_WIN_SHA256_URL:
        r = requests.get(FFMPEG_WIN_SHA256_URL, timeout=15)
        r.raise_for_status()
        tokens = r.text.strip().split()
        if not tokens or len(tokens[0]) != 64:
            raise RuntimeError("Empreinte SHA-256 de FFmpeg invalide.")
        expected_sha = tokens[0].lower()

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    archive = RUNTIME_DIR / "ffmpeg_download.zip"
    _download_verified(url, archive, expected_sha, st, "FFmpeg")

    st.update(progress=92, message="Extraction de FFmpeg…")
    tmp_dir = Path(tempfile.mkdtemp(prefix="clipoa_ffmpeg_", dir=str(RUNTIME_DIR)))
    target_dir = RUNTIME_DIR / "ffmpeg"
    try:
        safe_extract_zip(archive, tmp_dir)
        ff_matches = list(tmp_dir.rglob("ffmpeg.exe"))
        if not ff_matches:
            raise RuntimeError("ffmpeg.exe introuvable dans l'archive FFmpeg.")
        bin_dir = ff_matches[0].parent
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            src = bin_dir / name
            if src.exists():
                shutil.copy2(str(src), str(target_dir / name))
        (RUNTIME_DIR / "ffmpeg_version").write_text(expected_sha[:16] + "\n", encoding="utf-8")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        archive.unlink(missing_ok=True)
    _refresh_config_paths()
    st.update(progress=100, message="FFmpeg est prêt.")


def _install_whisper_model() -> None:
    """Télécharge le modèle faster-whisper-base dans runtime/models/ (survit aux MAJ Store)."""
    st = _STATE["whisper"]
    st.update(progress=5, message="Téléchargement du modèle Whisper…", error="")
    dest = whisper_model_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download
    rev = os.getenv("CLIPOA_WHISPER_REVISION", "").strip() or None
    snapshot_download(WHISPER_REPO, revision=rev, local_dir=str(dest))
    if not (dest / "model.bin").exists():
        raise RuntimeError("Modèle Whisper incomplet (model.bin manquant).")
    os.environ["CLIPOA_WHISPER_DIR"] = str(dest)
    st.update(progress=100, message="Whisper est prêt.")


def _start_bg(key: str, fn, err_prefix: str) -> bool:
    with _LOCK:
        if _STATE[key]["installing"]:
            return False
        _STATE[key]["installing"] = True
        _STATE[key]["error"] = ""

    def _run():
        try:
            fn()
        except Exception as e:
            _STATE[key]["error"] = f"{err_prefix} : {str(e)[:160]}"
        finally:
            _STATE[key]["installing"] = False

    threading.Thread(target=_run, daemon=True).start()
    return True


def start_blender_install() -> bool:
    supported = platform.system() in ("Darwin", "Windows") or sys.platform in ("darwin", "win32")
    if not supported or blender_ready():
        return False
    return _start_bg("blender", _install_blender, "Installation de Blender impossible")


def start_ffmpeg_install() -> bool:
    on_win = platform.system() == "Windows" or sys.platform == "win32"
    if not on_win or ffmpeg_ready():
        return False
    return _start_bg("ffmpeg", _install_ffmpeg_windows, "Installation de FFmpeg impossible")


def start_whisper_install() -> bool:
    if whisper_ready() or not _module_ok("faster_whisper"):
        return False
    return _start_bg("whisper", _install_whisper_model, "Téléchargement de Whisper impossible")


def start_tool_install(tool_id: str) -> bool:
    """Lance l'installation d'un outil ('blender', 'ffmpeg', 'whisper') ou de tous ('all')."""
    if tool_id == "blender":
        return start_blender_install()
    if tool_id == "ffmpeg":
        return start_ffmpeg_install()
    if tool_id == "whisper":
        return start_whisper_install()
    if tool_id == "all":
        started = False
        for fn in (start_ffmpeg_install, start_whisper_install, start_blender_install):
            started = fn() or started
        return started
    return False


def auto_setup_on_launch() -> None:
    """Premier lancement : installe les outils manquants en arrière-plan (hors Microsoft Store).

    En mode Microsoft Store (MSIX), aucun exécutable tiers n'est téléchargé sans
    validation explicite de l'utilisateur dans l'assistant de premier lancement.
    """
    if os.getenv("CLIPOA_NO_AUTO_TOOLS") or is_store_app():
        return
    time.sleep(3)
    if not blender_ready():
        start_blender_install()
