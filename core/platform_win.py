# -*- coding: utf-8 -*-
"""
Utilitaires spécifiques à Windows (isolés du code macOS).

Ce module est importable sans erreur sur macOS/Linux (tous les appels Win32 sont
gardés derrière `sys.platform == "win32"`), ce qui permet de le tester sur Mac
en simulant la plateforme et d'éviter toute régression côté macOS.
"""

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

# Flag Win32 pour lancer un sous-processus sans flash de fenêtre console
CREATE_NO_WINDOW = 0x08000000


def is_windows() -> bool:
    return sys.platform == "win32"


def is_store_app(base_dir: Optional[Path] = None) -> bool:
    """True si Clipoa tourne dans un paquet MSIX (Microsoft Store).

    Détection :
    1. Variable explicite `CLIPOA_STORE_APP=1` (posée par le lanceur MSIX).
    2. Chemin contenant `\\WindowsApps\\` (dossier système des apps MSIX).
    3. Sur Windows réel : appel Win32 `GetCurrentPackageFullName` (retourne 0 si packagé MSIX).
    """
    env = os.getenv("CLIPOA_STORE_APP", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    if not is_windows():
        return False

    candidates = [str(base_dir or ""), sys.executable or ""]
    for c in candidates:
        if "windowsapps" in c.lower().replace("/", "\\").split("\\"):
            return True

    try:
        import ctypes
        length = ctypes.c_uint32(0)
        # APPMODEL_ERROR_NO_PACKAGE = 15700 ; ERROR_INSUFFICIENT_BUFFER = 122 -> packagé !
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return rc in (0, 122)
    except Exception:
        return False


def default_data_dir() -> Path:
    """Dossier persistant par utilisateur sur Windows (%LOCALAPPDATA%\\Clipoa).

    Survive aux mises à jour du Microsoft Store (le dossier MSIX est en lecture seule).
    """
    local = os.getenv("LOCALAPPDATA")
    if local:
        return Path(local) / "Clipoa"
    return Path.home() / "AppData" / "Local" / "Clipoa"


def find_system_blender() -> Optional[str]:
    """Détecte un Blender déjà installé sur Windows (PATH, Program Files ou Microsoft Store)."""
    found = shutil.which("blender")
    if found:
        return found
    if not is_windows():
        return None

    # 1. Installation classique : C:\Program Files\Blender Foundation\Blender X.Y\blender.exe
    pf_roots = [os.getenv("ProgramFiles", r"C:\Program Files"), os.getenv("ProgramW6432", "")]
    candidates = []
    for root in pf_roots:
        if not root:
            continue
        bf = Path(root) / "Blender Foundation"
        if bf.is_dir():
            for exe in bf.glob("Blender*/blender.exe"):
                if exe.is_file():
                    candidates.append(exe)
    if candidates:
        # Prend la version la plus récente par nom de dossier
        candidates.sort(key=lambda p: p.parent.name, reverse=True)
        return str(candidates[0])

    # 2. Blender installé depuis le Microsoft Store (alias WindowsApps)
    local = os.getenv("LOCALAPPDATA")
    if local:
        store_alias = Path(local) / "Microsoft" / "WindowsApps" / "blender.exe"
        if store_alias.exists():
            return str(store_alias)
    return None


def find_system_ffmpeg() -> Optional[str]:
    """Détecte un ffmpeg déjà installé sur le PATH système."""
    return shutil.which("ffmpeg")


def open_url(url: str) -> bool:
    """Ouvre une URL dans le navigateur par défaut sans fenêtre console."""
    try:
        if is_windows() and hasattr(os, "startfile"):
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        return bool(webbrowser.open(url))
    except Exception:
        return False


def subprocess_kwargs() -> dict:
    """Arguments subprocess pour éviter tout flash de fenêtre console sur Windows."""
    if is_windows():
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


def pid_alive(pid: int) -> bool:
    """Vérifie si un processus tourne encore (compatible Windows sans `os.kill(pid, 0)`)."""
    if pid <= 0:
        return False
    if not is_windows():
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def terminate_pid(pid: int) -> bool:
    """Arrête proprement un processus serveur par son PID (Windows & POSIX)."""
    if pid <= 0:
        return False
    if not is_windows():
        try:
            os.kill(pid, 15)
            return True
        except Exception:
            return False
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **subprocess_kwargs(),
        )
        return True
    except Exception:
        return False
