import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Any, List
from config import STORAGE_DIR, DEFAULT_TTS_VOICE
from core.vault import encrypt_sensitive_fields, decrypt_sensitive_fields

SETTINGS_FILE = STORAGE_DIR / "settings.json"
CLAUDE_USAGE_FILE = STORAGE_DIR / "claude_usage.json"

_LOCK = threading.Lock()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            os.chmod(tmp_path, 0o600)
        except OSError:
            pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

# Real 5-hour rolling equivalent API-value budgets for Claude subscriptions (USD list-price equivalent)
CLAUDE_PLAN_BUDGETS = {
    "pro": {"label": "Claude Pro", "budget_5h_usd": 6.0, "default_video_usd": 0.48},
    "max_5x": {"label": "Claude Max 5x", "budget_5h_usd": 30.0, "default_video_usd": 0.48},
    "max_20x": {"label": "Claude Max 20x", "budget_5h_usd": 120.0, "default_video_usd": 0.48},
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "claude": {
        "plan": "pro",
        "model": "opus",
        "effort": "medium",
        "account_label": "Compte principal",
        "live_quota": {},
    },
    "gemini": {
        "api_key": "",
        "model": "gemini-3-flash-preview",
        "tier": "free",
        "credit_budget_usd": 10.0,
        "credit_reset_ts": 0.0,
    },
    "elevenlabs": {
        "api_key": "",
        "enabled": True,
        "default_voice_id": "",
        "model_id": "eleven_multilingual_v2",
    },
    "drive": {
        "folder_id": "",
        "folder_name": "Mon dossier créatif",
        "local_sync_dir": str(STORAGE_DIR / "drive_sync" / "workspace"),
        "last_sync": "",
    },
    "voice": {
        "edge_default": DEFAULT_TTS_VOICE,
    },
    "presets": [],
}

BUILTIN_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "fast_free",
        "label": "Rapide · Gratuit",
        "engine": "gemini",
        "render": "motion",
        "plugin_id": "",
        "voice_provider": "free",
        "voice_mode": "auto",
        "theme": "dark_luxury",
        "subtitle_style": "submagic_yellow",
        "retention_boost": True,
        "builtin": True,
    },
    {
        "id": "claude_cinema",
        "label": "Studio · Claude",
        "engine": "claude",
        "render": "motion",
        "plugin_id": "",
        "voice_provider": "free",
        "voice_mode": "auto",
        "theme": "cyber_grid",
        "subtitle_style": "submagic_yellow",
        "retention_boost": True,
        "builtin": True,
    },
    {
        "id": "broll_creator",
        "label": "B-roll Créateur",
        "engine": "claude",
        "render": "broll",
        "plugin_id": "",
        "voice_provider": "free",
        "voice_mode": "auto",
        "theme": "warm_studio",
        "subtitle_style": "shortcrew_red",
        "retention_boost": True,
        "builtin": True,
    },
]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_settings_unlocked() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = decrypt_sensitive_fields(json.load(f))
        return _deep_merge(DEFAULT_SETTINGS, data)
    except Exception:
        return json.loads(json.dumps(DEFAULT_SETTINGS))


def load_settings() -> Dict[str, Any]:
    with _LOCK:
        return _load_settings_unlocked()


def save_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        current = _load_settings_unlocked()
        merged = _deep_merge(current, updates)
        _atomic_write_json(SETTINGS_FILE, encrypt_sensitive_fields(merged))
        return merged


def record_claude_usage(
    prompt_chars: int,
    response_chars: int,
    mode: str = "claude_cli",
    action: str = "query",
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_tokens: int = 0,
    canonical_model: str = "",
) -> Dict[str, Any]:
    """
    Logs real Claude Code usage (exact total_cost_usd & tokens from --output-format json)
    for live 5h rolling quota & per-video tracking.
    """
    in_tok = input_tokens or max(1, int(prompt_chars / 3.8))
    out_tok = output_tokens or max(1, int(response_chars / 3.8))
    # Fallback USD estimate only if CLI didn't report total_cost_usd
    real_cost = float(cost_usd) if cost_usd and cost_usd > 0 else round((in_tok * 15 + out_tok * 75) / 1_000_000, 5)
    entry = {
        "ts": time.time(),
        "mode": mode,
        "action": action,
        "canonical_model": canonical_model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_tokens": cache_tokens,
        "total_tokens": in_tok + out_tok + cache_tokens,
        "cost_usd": round(real_cost, 6),
    }
    with _LOCK:
        history: List[Dict[str, Any]] = []
        if CLAUDE_USAGE_FILE.exists():
            try:
                with open(CLAUDE_USAGE_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        cutoff = time.time() - 7 * 86400
        history = [h for h in history if h.get("ts", 0) >= cutoff]
        history.append(entry)
        _atomic_write_json(CLAUDE_USAGE_FILE, history)
    return entry


def save_live_claude_quota(rate_limit_info: Dict[str, Any]) -> Dict[str, Any]:
    """Saves exact server-side Anthropic 5h & 7d utilization from Claude CLI rate_limit_event."""
    if not isinstance(rate_limit_info, dict):
        return {}
    unified = rate_limit_info.get("unifiedWindows") or {}
    w5 = unified.get("five_hour") or {}
    w7 = unified.get("seven_day") or {}
    util_5h = w5.get("utilization")
    if util_5h is None:
        util_5h = rate_limit_info.get("utilization")
    resets_5h = w5.get("resetsAt") or rate_limit_info.get("resetsAt") or 0
    util_7d = w7.get("utilization")
    resets_7d = w7.get("resetsAt") or 0

    live = {
        "synced_at": time.time(),
        "status": rate_limit_info.get("status", "allowed"),
        "util_5h": float(util_5h) if util_5h is not None else None,
        "resets_5h": int(resets_5h) if resets_5h else 0,
        "util_7d": float(util_7d) if util_7d is not None else None,
        "resets_7d": int(resets_7d) if resets_7d else 0,
    }
    save_settings({"claude": {"live_quota": live}})
    return live


def get_claude_quota_summary() -> Dict[str, Any]:
    settings = load_settings()
    claude_cfg = settings.get("claude", {})
    plan_key = claude_cfg.get("plan", "pro")
    plan = CLAUDE_PLAN_BUDGETS.get(plan_key, CLAUDE_PLAN_BUDGETS["pro"])
    live = claude_cfg.get("live_quota") or {}

    now = time.time()
    window_5h = now - 5 * 3600

    history: List[Dict[str, Any]] = []
    with _LOCK:
        if CLAUDE_USAGE_FILE.exists():
            try:
                with open(CLAUDE_USAGE_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

    recent = [h for h in history if h.get("ts", 0) >= window_5h and h.get("mode") != "fallback"]
    cost_5h = sum(float(h.get("cost_usd", 0.0)) for h in recent)
    tokens_5h = sum(int(h.get("total_tokens", 0)) for h in recent)
    calls_5h = len(recent)

    if calls_5h >= 2:
        est_video_usd = max(0.05, (cost_5h / calls_5h) * 2.0)
    else:
        est_video_usd = plan["default_video_usd"]

    budget_usd = float(plan["budget_5h_usd"])
    est_pct_per_video = min(100.0, round((est_video_usd / budget_usd) * 100.0, 1))

    # Prefer REAL server-side Anthropic utilization if synced and not past reset
    live_valid = (
        live.get("util_5h") is not None
        and (not live.get("resets_5h") or live.get("resets_5h", 0) > now)
    )
    if live_valid:
        used_pct = min(100.0, round(float(live["util_5h"]) * 100.0, 1))
        remaining_pct = max(0.0, round(100.0 - used_pct, 1))
        source = "anthropic_live"
    else:
        used_pct = min(100.0, round((cost_5h / budget_usd) * 100.0, 1))
        remaining_pct = max(0.0, round(100.0 - used_pct, 1))
        source = "local_estimate"

    est_videos_left = max(0, int(remaining_pct // max(1.0, est_pct_per_video)))
    resets_str = ""
    if live.get("resets_5h") and live["resets_5h"] > now:
        resets_str = time.strftime("%H:%M", time.localtime(live["resets_5h"]))

    util_7d_pct = round(float(live["util_7d"]) * 100.0, 1) if live.get("util_7d") is not None else None
    rem_7d_pct = max(0.0, round(100.0 - util_7d_pct, 1)) if util_7d_pct is not None else None

    return {
        "source": source,
        "plan": plan_key,
        "plan_label": plan["label"],
        "cost_5h_usd": round(cost_5h, 3),
        "budget_5h_usd": budget_usd,
        "tokens_5h": tokens_5h,
        "calls_5h": calls_5h,
        "used_pct": used_pct,
        "remaining_pct": remaining_pct,
        "seven_day_remaining_pct": rem_7d_pct,
        "resets_at": resets_str,
        "est_pct_per_video": est_pct_per_video,
        "est_videos_left": est_videos_left,
        "last_model": recent[-1].get("canonical_model", "") if recent else "",
    }


def reset_claude_quota_counter():
    """Called when switching to a fresh Claude account so both local meter and cached live quota reset."""
    with _LOCK:
        _atomic_write_json(CLAUDE_USAGE_FILE, [])
        current = _load_settings_unlocked()
        current.setdefault("claude", {})["live_quota"] = {}
        _atomic_write_json(SETTINGS_FILE, current)


def list_presets() -> List[Dict[str, Any]]:
    custom = load_settings().get("presets") or []
    return list(BUILTIN_PRESETS) + [p for p in custom if isinstance(p, dict) and p.get("id")]


def save_custom_preset(preset: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(preset.get("id") or f"preset_{int(time.time())}")
    clean = {
        "id": pid,
        "label": str(preset.get("label") or "Mon Preset")[:40],
        "engine": "gemini" if preset.get("engine") == "gemini" else "claude",
        "render": preset.get("render") if preset.get("render") in ("motion", "broll", "ai_video", "blender3d") else "motion",
        "plugin_id": str(preset.get("plugin_id") or "")[:64],
        "voice_provider": "el" if preset.get("voice_provider") == "el" else "free",
        "voice_mode": "manual" if preset.get("voice_mode") == "manual" else "auto",
        "theme": str(preset.get("theme") or "dark_luxury"),
        "subtitle_style": str(preset.get("subtitle_style") or "submagic_yellow"),
        "retention_boost": bool(preset.get("retention_boost", True)),
        "builtin": False,
    }
    with _LOCK:
        current = _load_settings_unlocked()
        presets = [p for p in (current.get("presets") or []) if isinstance(p, dict) and p.get("id") != pid]
        presets.append(clean)
        current["presets"] = presets[:12]
        _atomic_write_json(SETTINGS_FILE, current)
    return clean


def delete_custom_preset(preset_id: str) -> bool:
    with _LOCK:
        current = _load_settings_unlocked()
        presets = current.get("presets") or []
        new_presets = [p for p in presets if isinstance(p, dict) and p.get("id") != preset_id]
        if len(new_presets) == len(presets):
            return False
        current["presets"] = new_presets
        _atomic_write_json(SETTINGS_FILE, current)
    return True
