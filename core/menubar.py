"""
Icône Clipoa dans la barre de menus macOS (processus séparé, lancé par `run_app`).

Affiche l'état (rendu en cours + %, vidéo prête) et propose « Ouvrir Clipoa » / « Quitter ».
Lit l'état sur `/api/jobs` du serveur local ; se ferme tout seul quand le serveur s'arrête
(donc une seule icône, même après le redémarrage d'une mise à jour).
Optionnel : sans rumps (Windows, Linux, paquet absent) rien n'est lancé. Couper : CLIPOA_MENUBAR=0.
"""

import importlib.util
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ACTIVE_STATUSES = ("running", "queued")
ICON = Path(__file__).resolve().parent.parent / "assets" / "menubar" / "clipoa_template.png"


def available() -> bool:
    return (
        sys.platform == "darwin"
        and os.getenv("CLIPOA_MENUBAR", "1") != "0"
        and importlib.util.find_spec("rumps") is not None
    )


def launch(port: int = 8080):
    """Lance l'icône à côté du serveur. Renvoie le processus, ou None si indisponible."""
    if not available():
        return None
    code = "from core.menubar import main; main()"
    try:
        return subprocess.Popen(
            [sys.executable, "-c", code, "--port", str(port), "--server-pid", str(os.getpid())],
            cwd=str(Path(__file__).resolve().parent.parent),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
    except Exception:
        return None


def summarize(jobs) -> dict:
    """État court à afficher : {'title': texte à côté de l'icône, 'line': ligne du menu, 'busy': bool}."""
    jobs = [j for j in (jobs or []) if isinstance(j, dict)]
    active = [j for j in jobs if j.get("status") in ACTIVE_STATUSES]
    if active:
        j = max(active, key=lambda x: x.get("updated_at") or 0)
        pct = max(0, min(99, int(j.get("progress") or 0)))
        more = f" (+{len(active) - 1})" if len(active) > 1 else ""
        return {"title": f"{pct}%", "line": f"Rendu en cours : {pct}%{more}", "busy": True}
    done = [j for j in jobs if j.get("status") == "done"]
    if done:
        j = max(done, key=lambda x: x.get("updated_at") or 0)
        name = (j.get("video_title") or j.get("label") or "").strip()
        if len(name) > 40:
            name = name[:39].rstrip() + "…"
        return {"title": "", "line": f"Prête : {name}" if name else "Vidéo prête", "busy": False}
    return {"title": "", "line": "Aucun rendu", "busy": False}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _arg(name: str, default: str) -> str:
    argv = sys.argv
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main():
    import rumps  # paquet macOS uniquement

    port = int(_arg("--port", os.getenv("CLIPOA_PORT", "8080")))
    server_pid = int(_arg("--server-pid", "0"))
    url = f"http://127.0.0.1:{port}"

    class ClipoaMenu(rumps.App):
        def __init__(self):
            icon = str(ICON) if ICON.exists() else None
            super().__init__("Clipoa", title=None if icon else "Clipoa", icon=icon, template=True, quit_button=None)
            self.status_item = rumps.MenuItem("Aucun rendu", callback=self.open_app)
            self.busy = False
            self.menu = [self.status_item, None, rumps.MenuItem("Ouvrir Clipoa", callback=self.open_app),
                         None, rumps.MenuItem("Quitter", callback=self.quit_all)]

        def open_app(self, _=None):
            subprocess.Popen(["/usr/bin/open", f"http://localhost:{port}"])

        @rumps.timer(2)
        def refresh(self, _):
            if server_pid and not _pid_alive(server_pid):
                rumps.quit_application()
                return
            try:
                with urllib.request.urlopen(f"{url}/api/jobs", timeout=1.5) as r:
                    jobs = json.loads(r.read().decode("utf-8")).get("jobs") or []
            except Exception:
                return
            s = summarize(jobs)
            self.busy = s["busy"]
            self.status_item.title = s["line"]
            self.title = s["title"] or None

        def quit_all(self, _):
            if self.busy and rumps.alert("Un rendu est en cours.", "Quitter quand même ?", ok="Quitter", cancel="Annuler") != 1:
                return
            if server_pid and _pid_alive(server_pid):
                try:
                    os.kill(server_pid, 15)
                except Exception:
                    pass
            rumps.quit_application()

    try:  # pas d'icône dans le Dock : seulement la barre de menus
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)
    except Exception:
        pass
    ClipoaMenu().run()


if __name__ == "__main__":
    main()
