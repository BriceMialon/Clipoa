import json
from pathlib import Path
from typing import Dict, Any
from config import STORAGE_DIR

CHECKPOINTS_DIR = STORAGE_DIR / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


def load_checkpoint(session_id: str) -> Dict[str, Any]:
    p = CHECKPOINTS_DIR / f"{session_id}.json"
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_checkpoint(session_id: str, data: Dict[str, Any]) -> None:
    p = CHECKPOINTS_DIR / f"{session_id}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clear_checkpoint(session_id: str) -> None:
    p = CHECKPOINTS_DIR / f"{session_id}.json"
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
