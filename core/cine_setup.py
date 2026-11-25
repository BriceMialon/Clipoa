"""
Moteur « Roblox 3D Ciné » (haute qualité) : installation en un clic, pour n'importe quel utilisateur.

Ce que l'installateur prépare, sans Terminal ni Node.js :
  - three.js 0.187.0 (téléchargé depuis le registre npm, seuls build/ et examples/jsm/ sont gardés)
  - les polices des sous-titres et des panneaux (Montserrat Black/ExtraBold, Luckiest Guy)
  - un navigateur pour le rendu : Google Chrome s'il est installé, sinon Chromium via Playwright
Tout va dans storage/cine_runtime/ (ignoré par Git) ; le code du moteur est dans core/cine_engine/.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from config import BASE_DIR, STORAGE_DIR

ENGINE_DIR = BASE_DIR / "core" / "cine_engine"
RUNTIME = Path(os.environ.get("CLIPOA_CINE_RUNTIME", str(STORAGE_DIR / "cine_runtime")))
THREE_DIR = RUNTIME / "three"
FONTS_DIR = RUNTIME / "fonts"
EPISODES_DIR = STORAGE_DIR / "cine_episodes"
STATE_FILE = RUNTIME / "state.json"
LOG_FILE = RUNTIME / "install.log"
THREE_VERSION = "0.187.0"
THREE_URL = f"https://registry.npmjs.org/three/-/three-{THREE_VERSION}.tgz"
FONTS = {
    "LuckiestGuy-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/apache/luckiestguy/LuckiestGuy-Regular.ttf",
    "Montserrat-Black.ttf": "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Black.ttf",
    "Montserrat-ExtraBold.ttf": "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf",
}
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
_LOCK = threading.Lock()


def _state() -> Dict[str, Any]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except Exception:
        return {}


def _save(**kw) -> None:
    with _LOCK:
        st = _state()
        st.update(kw)
        RUNTIME.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")


def find_chrome() -> Optional[str]:
    env = os.environ.get("CLIPOA_CHROME", "").strip()
    if env and os.path.exists(env):
        return env
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return None  # Playwright utilisera son Chromium (installé par l'installateur)


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def is_ready() -> bool:
    return (THREE_DIR / "build" / "three.module.js").exists() and all((FONTS_DIR / f).exists() for f in FONTS) and _playwright_ok() \
        and (find_chrome() is not None or bool(_state().get("chromium")))


def status() -> Dict[str, Any]:
    st = _state()
    return {"ready": is_ready(), "installing": bool(st.get("installing")), "step": st.get("step", ""),
            "error": st.get("error", ""), "browser": find_chrome() or ("chromium" if st.get("chromium") else "")}


def _download(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Clipoa/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _install() -> None:
    try:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as log:
            if not _playwright_ok():
                _save(step="Installation du pilote de navigateur (Playwright)…")
                if subprocess.call([sys.executable, "-m", "pip", "install", "-q", "playwright"], stdout=log, stderr=subprocess.STDOUT) != 0:
                    raise RuntimeError("Installation de Playwright impossible")
            if not find_chrome():
                _save(step="Téléchargement du navigateur de rendu (Chromium, ≈ 150 Mo)…")
                if subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"], stdout=log, stderr=subprocess.STDOUT) != 0:
                    raise RuntimeError("Téléchargement de Chromium impossible")
                _save(chromium=True)
            if not (THREE_DIR / "build" / "three.module.js").exists():
                _save(step=f"Téléchargement du moteur 3D (three.js {THREE_VERSION})…")
                data = _download(THREE_URL)
                tmp = RUNTIME / "_three_tmp"
                shutil.rmtree(tmp, ignore_errors=True)
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
                    keep = [m for m in tf.getmembers() if m.name.startswith(("package/build/", "package/examples/jsm/"))
                            and ".." not in m.name and (m.isfile() or m.isdir())]
                    tf.extractall(tmp, members=keep)
                shutil.rmtree(THREE_DIR, ignore_errors=True)
                shutil.move(str(tmp / "package"), str(THREE_DIR))
                shutil.rmtree(tmp, ignore_errors=True)
            FONTS_DIR.mkdir(parents=True, exist_ok=True)
            for name, url in FONTS.items():
                if not (FONTS_DIR / name).exists():
                    _save(step=f"Téléchargement de la police {name}…")
                    (FONTS_DIR / name).write_bytes(_download(url))
        _save(installing=False, step="Moteur Ciné prêt", error="", installed_at=time.time())
    except Exception as e:
        _save(installing=False, error=str(e)[:300], step="")


def start_install() -> Dict[str, Any]:
    if _state().get("installing"):
        return status()
    _save(installing=True, step="Démarrage…", error="")
    threading.Thread(target=_install, daemon=True).start()
    return status()
