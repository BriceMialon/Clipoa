# -*- coding: utf-8 -*-
"""
Point d'entrée Windows (MSIX & lanceur autonome).

Rôle :
1. Configure l'environnement persistant dans %LOCALAPPDATA%\\Clipoa (le dossier MSIX
   WindowsApps étant en lecture seule, storage/ et runtime/ survivent aux MAJ du Store).
2. Si Clipoa tourne déjà sur http://127.0.0.1:<port>, ouvre simplement le navigateur et quitte.
3. Sinon, démarre le serveur Flask (clipoa_app.run_app), l'icône de zone de notification
   (tray) et ouvre http://localhost:<port> dès que le serveur répond.
"""

import os
import sys
import threading
import time
import urllib.request
from pathlib import Path


def _server_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/update/status", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def _setup_environment() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    data_dir = Path(os.getenv("CLIPOA_DATA_DIR") or (Path(local_app_data) / "Clipoa"))
    runtime_dir = data_dir / "runtime"
    logs_dir = data_dir / "logs"
    for d in (data_dir, runtime_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    os.environ["CLIPOA_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("CLIPOA_STORE_APP", "1")
    os.environ.setdefault("CLIPOA_EDITION", "public")
    os.environ.setdefault("CLIPOA_APP_ID", "Clipoa")
    os.environ.setdefault("HF_HOME", str(runtime_dir / "huggingface"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(runtime_dir / "ms-playwright"))
    os.environ.setdefault("CLIPOA_WHISPER_DIR", str(runtime_dir / "models" / "faster-whisper-base"))
    return logs_dir


def _redirect_logs(logs_dir: Path) -> None:
    """En mode fenêtre masquée (--windows-console-mode=disable), redirige stdout/stderr vers clipoa.log."""
    log_file = logs_dir / "clipoa.log"
    try:
        if log_file.exists() and log_file.stat().st_size > 20_000_000:
            prev = logs_dir / "clipoa.log.1"
            if prev.exists():
                prev.unlink()
            log_file.rename(prev)
        f = open(log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass


def main() -> None:
    port = int(os.getenv("CLIPOA_PORT", "8080"))
    logs_dir = _setup_environment()

    # Ajoute le dossier de l'app (contenant les .pyd compilés) au sys.path
    app_dir = Path(__file__).resolve().parent
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    os.chdir(str(app_dir))

    from core.platform_win import open_url

    # Si Clipoa tourne déjà : ouvrir l'interface et quitter sans doublon
    if _server_ready(port):
        open_url(f"http://localhost:{port}")
        return

    _redirect_logs(logs_dir)

    # Ouvre le navigateur dès que le serveur écoute
    def _open_when_ready():
        for _ in range(120):
            if _server_ready(port):
                if not os.getenv("CLIPOA_NO_OPEN"):
                    open_url(f"http://localhost:{port}")
                return
            time.sleep(0.5)

    threading.Thread(target=_open_when_ready, daemon=True).start()

    # Import du module compilé Nuitka (clipoa_app) ou fallback dev (app)
    try:
        import clipoa_app as server_mod
    except ImportError:
        import app as server_mod

    server_mod.run_app(port=port)


if __name__ == "__main__":
    main()
