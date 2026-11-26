# -*- coding: utf-8 -*-
"""
Icône Clipoa dans la zone de notification Windows (system tray).

Processus séparé lancé par `core.menubar.launch(port)` sur Windows :
- Affiche l'état du rendu (en cours + %, vidéo prête, aucun rendu) dans le menu et l'infobulle.
- Propose « Ouvrir Clipoa » (aussi action par défaut au double-clic) et « Quitter »
  (avec confirmation Win32 si un rendu est en cours).
- Lit l'état sur `/api/jobs` toutes les 2 s et se ferme tout seul quand le serveur s'arrête.
- Dépendances Windows uniquement : `pystray` et `Pillow` (optionnelles, zéro impact sur macOS).
"""

import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

from core.menubar import ICON, _arg, summarize
from core.platform_win import open_url, pid_alive, terminate_pid


def _load_icon_image():
    """Charge l'icône Clipoa (PIL.Image) ou dessine un badge minimaliste en secours."""
    from PIL import Image, ImageDraw

    if ICON.exists():
        try:
            img = Image.open(ICON).convert("RGBA")
            return img.resize((64, 64))
        except Exception:
            pass
    img = Image.new("RGBA", (64, 64), (24, 24, 32, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((10, 10, 54, 54), fill=(255, 107, 107, 255))
    return img


def _confirm_quit_busy() -> bool:
    """Boîte de dialogue native Win32 avant de quitter pendant un rendu."""
    try:
        import ctypes
        MB_YESNO = 0x04
        MB_ICONWARNING = 0x30
        IDYES = 6
        res = ctypes.windll.user32.MessageBoxW(
            0,
            "Un rendu est en cours.\nQuitter quand même ?",
            "Clipoa",
            MB_YESNO | MB_ICONWARNING,
        )
        return res == IDYES
    except Exception:
        return True


def main() -> None:
    import pystray

    port = int(_arg("--port", os.getenv("CLIPOA_PORT", "8080")))
    server_pid = int(_arg("--server-pid", "0"))
    api_url = f"http://127.0.0.1:{port}"
    web_url = f"http://localhost:{port}"

    state = {"line": "Aucun rendu", "title": "", "busy": False}
    stop_event = threading.Event()

    def on_open(icon, _item=None):
        open_url(web_url)

    def on_quit(icon, _item=None):
        if state["busy"] and not _confirm_quit_busy():
            return
        stop_event.set()
        if server_pid and pid_alive(server_pid):
            terminate_pid(server_pid)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _item: state["line"], on_open),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Ouvrir Clipoa", on_open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", on_quit),
    )
    tray = pystray.Icon("Clipoa", _load_icon_image(), "Clipoa", menu)

    def poll_loop():
        while not stop_event.is_set():
            if server_pid and not pid_alive(server_pid):
                tray.stop()
                return
            try:
                with urllib.request.urlopen(f"{api_url}/api/jobs", timeout=1.5) as r:
                    jobs = json.loads(r.read().decode("utf-8")).get("jobs") or []
                s = summarize(jobs)
                state["line"] = s["line"]
                state["title"] = s["title"]
                state["busy"] = s["busy"]
                tray.title = f"Clipoa — {s['title']}" if s["title"] else "Clipoa"
                tray.update_menu()
            except Exception:
                pass
            stop_event.wait(2.0)

    def setup(icon):
        icon.visible = True
        threading.Thread(target=poll_loop, daemon=True).start()

    tray.run(setup=setup)


if __name__ == "__main__":
    main()
