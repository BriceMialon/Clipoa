"""
Édition de ClipRoll : « perso » (défaut, tout est actif) ou « public » (version vendue).

La version publique coupe ce qui n'est pas autorisé ou pas prêt pour des clients :
- Gemini Studio (connexion Google perso) ;
- Mode Nuit / Pilote auto, mode Ciné, moteurs sur mesure écrits par l'IA ;
- radar S'inspirer, copie d'une vidéo de quelqu'un d'autre, scan de concurrents (CGU TikTok/Meta, droit d'auteur) ;
- connexion aux réseaux par cookies du navigateur (seul l'OAuth officiel reste) ;
- Équipe d'agents IA (lance des fabrications) et lecture des profils TikTok publics par yt-dlp (CGU TikTok).

Activer : variable d'environnement CLIPOA_EDITION=public. Le blocage est fait côté serveur
(routes refusées, moteur IA forcé) ; l'interface masque seulement les boutons correspondants.
"""

import os

EDITION = (os.getenv("CLIPOA_EDITION", "perso") or "perso").strip().lower()

PUBLIC_BLOCKED_PREFIXES = (
    "/api/gemini/",
    "/api/night/",
    "/api/cine/",
    "/api/inspiration",
    "/api/make-like",
    "/api/plugins/from-reference",
    "/api/clone",
    "/api/scan",
    "/api/script-lab/from-competitors",
    "/api/analytics/external",
    "/api/social/portal-login/",
    "/api/agent-team/",
    "/api/channel-stats/tiktok-handle",
    "/api/competitors",
)

PUBLIC_DISABLED_ENGINES = ("gemini",)


def is_public() -> bool:
    return EDITION == "public"


def is_blocked_path(path: str) -> bool:
    if not is_public():
        return False
    p = path or "/"
    for pre in PUBLIC_BLOCKED_PREFIXES:
        base = pre.rstrip("/")
        if p == base or p.startswith(base + "/"):
            return True
    return False


def restrict_engine_params(params: dict) -> dict:
    """En version publique, une tâche ne part jamais sur Gemini : elle passe sur Claude."""
    if not is_public():
        return params
    p = dict(params or {})
    if str(p.get("engine") or "").lower() in PUBLIC_DISABLED_ENGINES:
        p["engine"] = "claude"
        p["engine_model"] = None
        p.pop("engine_choice", None)
    return p


def restrict_visual_style(style: str, plugin: dict = None) -> str:
    """En version publique : pas de mode Ciné ni de moteur écrit par l'IA, on prend le moteur intégré."""
    if not is_public():
        return style
    if style == "cine3d":
        return "roblox"
    if style == "custom":
        return (((plugin or {}).get("production") or {}).get("fallback_style")) or "explainer2d"
    return style
