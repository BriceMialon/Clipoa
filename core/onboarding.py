"""
Assistant de premier lancement + « prochaine chose à faire » sur l'accueil.

Les étapes sont calculées à partir de l'état réel (outils, Claude, vidéos, réseaux) :
rien n'est coché « à la main ». Seuls le fait d'avoir passé ou fini le guide est
enregistré (storage/onboarding.json), pour ne pas le rouvrir à chaque lancement.
Aucune étape ne parle de Gemini, du mode Ciné ni d'Antigravity (version publique).
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STORAGE_DIR

STATE_FILE = Path(STORAGE_DIR) / "onboarding.json"

# Outils montrés dans le guide (les autres restent visibles dans Connexions).
SHOWN_TOOLS = {
    "ffmpeg": "Montage",
    "whisper": "Sous-titres",
    "voice": "Voix",
    "blender": "Scènes 3D",
}
SOCIAL_ORDER = ("youtube", "tiktok")
VALID_STATUS = ("new", "skipped", "done")


def load_state(path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path or STATE_FILE)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("status") in VALID_STATUS:
            return data
    except Exception:
        pass
    return {"status": "new"}


def save_state(state: Dict[str, Any], path: Optional[Path] = None) -> Dict[str, Any]:
    p = Path(path or STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    clean = {"status": state.get("status") if state.get("status") in VALID_STATUS else "new",
             "video_started": bool(state.get("video_started")),
             "updated_at": int(time.time())}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return clean


def apply_action(action: str, path: Optional[Path] = None) -> Dict[str, Any]:
    state = load_state(path)
    if action == "skip":
        state["status"] = "skipped"
    elif action == "finish":
        state["status"] = "done"
    elif action == "restart":
        state["status"] = "new"
    elif action == "video_started":
        state["video_started"] = True
    else:
        raise ValueError("Action inconnue.")
    return save_state(state, path)


def _tools_step(tools_status: Dict[str, Any]) -> Dict[str, Any]:
    tools = (tools_status or {}).get("tools") or {}
    items: List[Dict[str, Any]] = []
    for key, label in SHOWN_TOOLS.items():
        t = tools.get(key)
        if not t:
            continue
        items.append({
            "id": key,
            "label": label,
            "ok": bool(t.get("ok")),
            "installing": bool(t.get("installing")),
            "can_install": key == "blender" and bool(t.get("auto")) and not t.get("ok"),
        })
    return {"id": "tools", "done": all(i["ok"] for i in items), "items": items}


def _social_step(social_accounts: Dict[str, Any], oauth_apps: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for key in SOCIAL_ORDER:
        acc = (social_accounts or {}).get(key) or {}
        prov = acc.get("oauth_provider") or key
        items.append({
            "id": key,
            "label": acc.get("short_name") or key.capitalize(),
            "connected": bool(acc.get("auto_api")),
            "ready": bool(((oauth_apps or {}).get(prov) or {}).get("configured")),
        })
    return {"id": "social", "done": any(i["connected"] for i in items), "items": items}


def compute(tools_status: Dict[str, Any], claude_connected: bool, renders_count: int,
            unvalidated_count: int, social_accounts: Dict[str, Any], oauth_apps: Dict[str, Any],
            state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Étapes du guide + la prochaine chose à faire (une phrase, un bouton)."""
    state = state or {"status": "new"}
    tools = _tools_step(tools_status)
    claude = {"id": "claude", "done": bool(claude_connected)}
    video = {"id": "video", "done": renders_count > 0 or bool(state.get("video_started"))}
    social = _social_step(social_accounts, oauth_apps)
    steps = [tools, claude, video, social]

    if not tools["done"]:
        nxt = {"text": "Installe les outils de fabrication.", "button": "Vérifier", "action": "guide:tools"}
    elif not claude["done"]:
        nxt = {"text": "Connecte ton compte Claude.", "button": "Connecter", "action": "guide:claude"}
    elif renders_count == 0:
        nxt = {"text": "Fabrique ta première vidéo.", "button": "Commencer", "action": "create"}
    elif unvalidated_count > 0:
        nxt = {"text": ("Ta nouvelle vidéo t'attend." if unvalidated_count == 1
                        else f"{unvalidated_count} vidéos t'attendent."),
               "button": "Regarder", "action": "watch"}
    elif not social["done"] and any(i["ready"] for i in social["items"]):
        first = next(i for i in social["items"] if i["ready"])
        nxt = {"text": f"Connecte {first['label']} pour publier en un clic.", "button": "Connecter",
               "action": "guide:social"}
    else:
        nxt = {"text": "Fabrique ta prochaine vidéo.", "button": "Fabriquer", "action": "create"}

    return {
        "status": state.get("status", "new"),
        "auto_open": state.get("status", "new") == "new",
        "steps": steps,
        "next": nxt,
    }
