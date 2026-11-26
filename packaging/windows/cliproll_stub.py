# -*- coding: utf-8 -*-
"""ClipRoll.exe (MSIX) : lance l'app avec le Python embarqué du paquet, sans fenêtre console.

Disposition du paquet :
  ClipRoll.exe (+ ses fichiers Nuitka)   <- ce lanceur, compilé seul (bibliothèque standard)
  python\\pythonw.exe                   <- CPython 3.9 + toutes les dépendances (site-packages)
  app\\launcher.py, app\\*.pyd, ...       <- code ClipRoll (core/agents/app compilés en .pyd)

Les dépendances (Flask, yt_dlp, faster_whisper, playwright…) ne sont pas recompilées :
les compiler avec Nuitka prenait plus de 2 h et échouait sur la CI.
"""
import os
import subprocess
import sys


def main() -> int:
    base = os.path.dirname(os.path.abspath(sys.argv[0]))
    pyw = os.path.join(base, "python", "pythonw.exe")
    app_dir = os.path.join(base, "app")
    launcher = os.path.join(app_dir, "launcher.py")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([pyw, launcher, *sys.argv[1:]], cwd=app_dir, creationflags=flags)
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
