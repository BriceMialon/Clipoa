import json
import threading
import time
from typing import Any, Dict, List

from config import STORAGE_DIR

TIMING_FILE = STORAGE_DIR / "timing_history.json"
_LOCK = threading.Lock()

# Baselines initiales (en secondes, pour une vidéo de 60s) par moteur + mode de rendu
DEFAULT_BASELINES_SEC: Dict[str, float] = {
    "claude:motion": 55.0,
    "claude:blender3d": 115.0,
    "antigravity:motion": 42.0,
    "antigravity:blender3d": 95.0,
    "claude:script": 24.0,
    "antigravity:script": 16.0,
}

# Coût quota estimé par vidéo 60s (% de fenêtre 5h) par moteur
ENGINE_QUOTA_PCT_60S: Dict[str, float] = {
    "claude": 3.2,
    "antigravity": 1.1,
}


def _load_unlocked() -> List[Dict[str, Any]]:
    if not TIMING_FILE.exists():
        return []
    try:
        data = json.loads(TIMING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def record_actual_timing(
    engine: str,
    render_mode: str,
    elapsed_sec: float,
    target_duration_sec: int = 60,
) -> None:
    """Enregistre la durée réelle d'une génération pour affiner automatiquement les estimations futures."""
    if elapsed_sec <= 1.0 or elapsed_sec > 1800.0:
        return
    eng = "antigravity" if (engine or "").lower() == "antigravity" else "claude"
    rm = render_mode if render_mode in ("motion", "blender3d", "broll", "script") else "motion"
    scale = max(0.4, min(3.0, float(target_duration_sec or 60) / 60.0))
    normalized_60s = round(float(elapsed_sec) / (0.45 + 0.55 * scale), 1)
    entry = {
        "ts": time.time(),
        "key": f"{eng}:{rm}",
        "elapsed_sec": round(float(elapsed_sec), 1),
        "normalized_60s": normalized_60s,
        "target_duration_sec": int(target_duration_sec or 60),
    }
    with _LOCK:
        items = _load_unlocked()
        items.append(entry)
        items = items[-200:]
        try:
            TIMING_FILE.parent.mkdir(parents=True, exist_ok=True)
            TIMING_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")
        except Exception:
            pass


def get_learned_estimates() -> Dict[str, Any]:
    """
    Calcule les estimations apprises (moyenne pondérée récente) pour chaque couple moteur:rendu
    (base 60s), afin que l'UI et les jobs s'améliorent en temps réel au fil des utilisations.
    """
    with _LOCK:
        items = _load_unlocked()

    learned: Dict[str, float] = dict(DEFAULT_BASELINES_SEC)
    counts: Dict[str, int] = {}

    for key, default_val in DEFAULT_BASELINES_SEC.items():
        matching = [float(x["normalized_60s"]) for x in items if x.get("key") == key and x.get("normalized_60s")]
        counts[key] = len(matching)
        if matching:
            recent = matching[-8:]
            # Weighted blend: starts smooth with baseline, converges quickly to real user Mac speed
            avg_real = sum(recent) / len(recent)
            weight = min(0.85, len(recent) / (len(recent) + 2.0))
            learned[key] = round((1.0 - weight) * default_val + weight * avg_real, 1)

    return {
        "baselines_60s": learned,
        "samples_count": counts,
        "quota_pct_60s": dict(ENGINE_QUOTA_PCT_60S),
    }


def estimate_job_seconds(engine: str, render_mode: str, target_duration_sec: int = 60) -> int:
    eng = "antigravity" if (engine or "").lower() == "antigravity" else "claude"
    rm = "blender3d" if render_mode == "blender3d" else "motion"
    est = get_learned_estimates()["baselines_60s"].get(f"{eng}:{rm}", 75.0)
    scale = max(0.4, min(3.0, float(target_duration_sec or 60) / 60.0))
    return max(15, int(round(est * (0.45 + 0.55 * scale))))
