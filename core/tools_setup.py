# -*- coding: utf-8 -*-
"""
Outils de fabrication prêts à l'emploi pour un nouvel utilisateur (aucune commande à taper).

- ffmpeg : celui du système, sinon celui livré par le paquet Python imageio-ffmpeg (config.FFMPEG_PATH).
- yt-dlp, Whisper, voix Edge : paquets Python installés par start.sh (requirements.txt).
- Blender (styles 3D Roblox, 2D × Monde 3D, Explainer…) : téléchargé depuis blender.org et rangé dans
  runtime/Blender.app au premier lancement, en arrière-plan, sans droits administrateur.
- Moteur Ciné et voix HD : installation en un clic déjà gérée par core/cine_setup.py et core/local_tts.py.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict

import requests

from config import BLENDER_PATH, FFMPEG_PATH, RUNTIME_DIR, YT_DLP_PATH

# Blender 5 = Mac Apple Silicon ; les Mac Intel prennent la dernière version 4.5 LTS
BLENDER_CANDIDATES_ARM = [("5.3", "5.3.0"), ("5.2", "5.2.0")]
BLENDER_CANDIDATES_X64 = [("4.5", "4.5.5")]
_STATE: Dict[str, Any] = {"blender": {"installing": False, "progress": 0, "message": "", "error": ""}}
_LOCK = threading.Lock()


def _runs(path: str, *args: str) -> bool:
    try:
        return subprocess.run([path, *args], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def _module_ok(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def blender_ready() -> bool:
    return bool(BLENDER_PATH) and os.path.exists(BLENDER_PATH)


def status() -> Dict[str, Any]:
    tools = {
        "ffmpeg": {"label": "Montage vidéo (ffmpeg)", "ok": _runs(FFMPEG_PATH, "-version"), "auto": True},
        "yt_dlp": {"label": "Lecture des vidéos d'exemple (yt-dlp)", "ok": _runs(YT_DLP_PATH, "--version"), "auto": True},
        "whisper": {"label": "Sous-titres synchronisés (Whisper)", "ok": _module_ok("faster_whisper"), "auto": True},
        "voice": {"label": "Voix gratuite (Edge)", "ok": _module_ok("edge_tts"), "auto": True},
        "blender": {"label": "Scènes 3D (Blender)", "ok": blender_ready(), "auto": platform.system() == "Darwin",
                    **_STATE["blender"]},
    }
    try:
        from core import cine_setup
        tools["cine"] = {"label": "Moteur Ciné haute qualité", "ok": bool(cine_setup.is_ready()), "auto": False, "optional": True}
    except Exception:
        pass
    return {"tools": tools, "all_ok": all(t["ok"] for k, t in tools.items() if not t.get("optional"))}


def _blender_url() -> str:
    cands = BLENDER_CANDIDATES_ARM if platform.machine() == "arm64" else BLENDER_CANDIDATES_X64
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    for major, full in cands:
        url = f"https://download.blender.org/release/Blender{major}/blender-{full}-macos-{arch}.dmg"
        try:
            if requests.head(url, timeout=10, allow_redirects=True).status_code == 200:
                return url
        except Exception:
            continue
    raise RuntimeError("Impossible de trouver le téléchargement de Blender sur blender.org.")


def _install_blender() -> None:
    st = _STATE["blender"]
    st.update(progress=1, message="Recherche de la dernière version de Blender…", error="")
    url = _blender_url()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    dmg = RUNTIME_DIR / "blender_download.dmg"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(dmg, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    st["progress"] = max(1, min(90, int(90 * done / total)))
                    st["message"] = f"Téléchargement de Blender… {done >> 20} / {total >> 20} Mo"
    st.update(progress=92, message="Installation de Blender…")
    mnt = Path(tempfile.mkdtemp(prefix="clipoa_blender_"))
    try:
        subprocess.run(["hdiutil", "attach", str(dmg), "-nobrowse", "-quiet", "-mountpoint", str(mnt)], check=True, timeout=300)
        src = mnt / "Blender.app"
        dest = RUNTIME_DIR / "Blender.app"
        if dest.exists():
            shutil.rmtree(dest)
        subprocess.run(["cp", "-R", str(src), str(dest)], check=True, timeout=600)
    finally:
        subprocess.run(["hdiutil", "detach", str(mnt), "-quiet", "-force"], timeout=120)
        try:
            dmg.unlink()
        except OSError:
            pass
    st.update(progress=100, message="Blender est prêt.")


def start_blender_install() -> bool:
    if platform.system() != "Darwin" or blender_ready():
        return False
    with _LOCK:
        if _STATE["blender"]["installing"]:
            return False
        _STATE["blender"]["installing"] = True

    def _run():
        try:
            _install_blender()
        except Exception as e:
            _STATE["blender"]["error"] = f"Installation de Blender impossible : {str(e)[:160]}"
        finally:
            _STATE["blender"]["installing"] = False

    threading.Thread(target=_run, daemon=True).start()
    return True


def auto_setup_on_launch() -> None:
    """Premier lancement : installe tout seul ce qui manque et qui peut l'être (Blender pour les styles 3D)."""
    if os.getenv("CLIPOA_NO_AUTO_TOOLS"):
        return
    time.sleep(3)
    if not blender_ready():
        start_blender_install()
