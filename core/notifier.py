"""
Notifications système : « Vidéo prête », « Publiée sur YouTube »…

- macOS : centre de notifications (osascript, sans dépendance, texte passé en argument et jamais
  interprété comme du code).
- Windows : notification Toast native via WinRT/PowerShell (texte passé par variables d'environnement
  et échappé XML, jamais interpolé comme du code ; fenêtre console masquée).
Inactif tant que le serveur n'a pas démarré (`activate()` dans `run_app`) : les tests n'envoient rien.
Couper : variable d'environnement CLIPOA_NOTIFY=0.
"""

import os
import subprocess
import sys

_ACTIVE = False

_PLATFORM_NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook"}

_OSA = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run"]

# Script PowerShell statique : lit titre et message depuis les variables d'environnement (jamais de code injecté)
_WIN_TOAST_PS = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
    "$t = [System.Security.SecurityElement]::Escape($env:CLIPOA_TOAST_TITLE);"
    "$m = [System.Security.SecurityElement]::Escape($env:CLIPOA_TOAST_MSG);"
    "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument;"
    "$xml.LoadXml(\"<toast><visual><binding template='ToastText02'><text id='1'>$t</text><text id='2'>$m</text></binding></visual></toast>\");"
    "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml);"
    "$appId = if ($env:CLIPOA_APP_ID) { $env:CLIPOA_APP_ID } else { 'ClipRoll' };"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast);"
)


def activate() -> None:
    global _ACTIVE
    _ACTIVE = True


def enabled() -> bool:
    return _ACTIVE and sys.platform in ("darwin", "win32") and os.getenv("CLIPOA_NOTIFY", "1") != "0"


def _short(text, limit: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _notify_windows(title: str, message: str) -> bool:
    from core.platform_win import CREATE_NO_WINDOW
    env = dict(os.environ)
    env["CLIPOA_TOAST_TITLE"] = _short(title, 40)
    env["CLIPOA_TOAST_MSG"] = _short(message, 90)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass",
            "-Command", _WIN_TOAST_PS,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    return True


def notify(message: str, title: str = "ClipRoll") -> bool:
    if not enabled() or not message:
        return False
    try:
        if sys.platform == "win32":
            return _notify_windows(title, message)
        subprocess.Popen(
            ["/usr/bin/osascript", *_OSA, _short(title, 40), _short(message, 90)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def video_message(title: str = "", error: str = None) -> str:
    if error:
        return "Échec du rendu"
    return f"Vidéo prête : {_short(title, 60)}" if title else "Vidéo prête"


def publish_message(status: str, platforms) -> str:
    names = ", ".join(_PLATFORM_NAMES.get(p, str(p).capitalize()) for p in (platforms or []))
    if status == "published":
        return f"Publiée sur {names}" if names else "Publiée"
    if status == "partial":
        return f"Publiée en partie ({names})" if names else "Publiée en partie"
    if status == "failed":
        return "Échec de la publication"
    return ""  # envoi manuel : l'utilisateur est déjà devant l'écran


def video_done(title: str = "", error: str = None) -> bool:
    return notify(video_message(title, error))


def published(status: str, platforms) -> bool:
    return notify(publish_message(status, platforms))
