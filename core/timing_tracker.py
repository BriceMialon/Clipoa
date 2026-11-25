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


# ---------------------------------------------------------------- benchmark par style
# Valeurs de départ pour une vidéo de 60 s (secondes de fabrication, % de la fenêtre 5 h de Claude),
# remplacées au fil des vraies fabrications (temps réel + coût Claude réel lu dans l'historique d'usage).
# "_copy" = style copié depuis une vidéo d'exemple (analyse de la vidéo en plus) ; "_motion" = fond animé simple.
STYLE_DEFAULTS_60S: Dict[str, Dict[str, float]] = {
    "roblox_3d":     {"sec": 340.0, "pct": 4.5},
    "2d_monde_3d":   {"sec": 320.0, "pct": 4.2},
    "explainer_2d":  {"sec": 260.0, "pct": 3.6},
    "fete_en_folie": {"sec": 250.0, "pct": 3.5},
    "roblox_cine":   {"sec": 2400.0, "pct": 16.0},
    "_copy":         {"sec": 900.0, "pct": 12.0},   # analyse + moteur sur mesure écrit par l'IA
    "_motion":       {"sec": 90.0, "pct": 2.5},
}
AGY_TIME_FACTOR = 0.85      # Antigravity un peu plus rapide
AGY_QUOTA_FACTOR = 0.35     # et sa fenêtre de quota est plus large


def _scale(target_duration_sec: int) -> float:
    return max(0.4, min(3.0, float(target_duration_sec or 60) / 60.0))


def style_key(plugin_id: str = "", copied: bool = False) -> str:
    if copied:
        return "_copy"
    return plugin_id if plugin_id in STYLE_DEFAULTS_60S else ("_copy" if plugin_id else "_motion")


def claude_cost_between(t0: float, t1: float) -> float:
    """Coût Claude réel (USD) des appels faits entre t0 et t1 (historique tenu par settings_store)."""
    try:
        from core.settings_store import CLAUDE_USAGE_FILE
        hist = json.loads(CLAUDE_USAGE_FILE.read_text(encoding="utf-8"))
        return round(sum(float(h.get("cost_usd") or 0) for h in hist
                         if t0 <= float(h.get("ts") or 0) <= t1 and h.get("mode") != "fallback"), 5)
    except Exception:
        return 0.0


def _claude_budget_usd() -> float:
    try:
        from core.settings_store import load_settings, CLAUDE_PLAN_BUDGETS
        plan = (load_settings().get("claude") or {}).get("plan") or "pro"
        return float(CLAUDE_PLAN_BUDGETS.get(plan, CLAUDE_PLAN_BUDGETS["pro"])["budget_5h_usd"])
    except Exception:
        return 0.0


def record_style_run(style: str, engine: str, elapsed_sec: float, target_duration_sec: int, t_start: float) -> None:
    """Mesure réelle d'une fabrication pour CE style : temps total et part de la fenêtre 5 h de Claude consommée."""
    if elapsed_sec <= 5.0 or elapsed_sec > 4 * 3600:
        return
    eng = "antigravity" if (engine or "").lower() == "antigravity" else "claude"
    sc = _scale(target_duration_sec)
    entry = {
        "ts": time.time(),
        "key": f"style:{style}:{eng}",
        "elapsed_sec": round(float(elapsed_sec), 1),
        "normalized_60s": round(float(elapsed_sec) / (0.45 + 0.55 * sc), 1),
        "target_duration_sec": int(target_duration_sec or 60),
    }
    if eng == "claude":
        cost = claude_cost_between(t_start, time.time())
        budget = _claude_budget_usd()
        if cost > 0 and budget > 0:
            entry["claude_cost_usd"] = cost
            entry["pct_60s"] = round(100.0 * cost / budget / (0.5 + 0.5 * sc), 2)
    with _LOCK:
        items = _load_unlocked()
        items.append(entry)
        items = items[-400:]
        try:
            TIMING_FILE.parent.mkdir(parents=True, exist_ok=True)
            TIMING_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")
        except Exception:
            pass


def _blend(default: float, values: List[float]) -> float:
    if not values:
        return default
    recent = values[-8:]
    weight = min(0.9, len(recent) / (len(recent) + 1.5))
    return round((1.0 - weight) * default + weight * (sum(recent) / len(recent)), 2)


def style_estimates(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for st, d in STYLE_DEFAULTS_60S.items():
        out[st] = {}
        for eng in ("claude", "antigravity"):
            rows = [x for x in items if x.get("key") == f"style:{st}:{eng}"]
            secs = [float(x["normalized_60s"]) for x in rows if x.get("normalized_60s")]
            pcts = [float(x["pct_60s"]) for x in rows if x.get("pct_60s")]
            d_sec = d["sec"] * (AGY_TIME_FACTOR if eng == "antigravity" else 1.0)
            d_pct = d["pct"] * (AGY_QUOTA_FACTOR if eng == "antigravity" else 1.0)
            out[st][eng] = {"sec_60s": _blend(d_sec, secs), "pct_60s": _blend(d_pct, pcts),
                            "samples": len(rows), "measured": bool(rows)}
    return out


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
        "styles": style_estimates(items),
    }


def estimate_job_seconds(engine: str, render_mode: str, target_duration_sec: int = 60) -> int:
    eng = "antigravity" if (engine or "").lower() == "antigravity" else "claude"
    rm = "blender3d" if render_mode == "blender3d" else "motion"
    est = get_learned_estimates()["baselines_60s"].get(f"{eng}:{rm}", 75.0)
    scale = max(0.4, min(3.0, float(target_duration_sec or 60) / 60.0))
    return max(15, int(round(est * (0.45 + 0.55 * scale))))
