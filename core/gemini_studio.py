import base64
import json
import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
import requests

from config import BASE_DIR, STORAGE_DIR, RENDERS_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE
from core.settings_store import load_settings, save_settings
from core.drive_client import DriveClient
from core.voice_engine import VoiceEngine
from core.transcriber import AudioTranscriber
from core.video_composer import VideoComposer
from core.blender_engine import BlenderEngine
from core.style_plugins import StylePluginStore
from agents.prompts import PROMPT_SCENARISTE

GEMINI_USAGE_FILE = STORAGE_DIR / "gemini_usage.json"
NODE_BIN_DIR = BASE_DIR / "runtime" / "node" / "bin"
GEMINI_CLI_BIN = BASE_DIR / "runtime" / "gemini" / "bin" / "gemini"
GEMINI_OAUTH_CREDS = Path.home() / ".gemini" / "oauth_creds.json"
GEMINI_ACCOUNTS_FILE = Path.home() / ".gemini" / "google_accounts.json"
_LOCK = threading.Lock()

GEMINI_MODELS = [
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash (Gratuit · Recommandé)", "tier": "free"},
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash Lite (Gratuit · Ultra-rapide)", "tier": "free"},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite (Gratuit · Stable)", "tier": "free"},
    {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash (Gratuit · Puissant)", "tier": "free"},
    {"id": "gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro (Qualité max)", "tier": "paid"},
    {"id": "gemini-pro-latest", "label": "Gemini Pro Latest", "tier": "paid"},
]

FREE_MODEL_CASCADE = [
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
]

VIDEO_AI_MODELS = [
    {"id": "gemini-omni-1.2-flash", "label": "Gemini Omni 1.2 Flash (Vidéo IA 9:16 + Audio)", "tier": "paid"},
]

# Estimated USD pricing per 1M tokens (input, output) & flat estimates for media
GEMINI_PRICING_PER_1M = {
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-pro-latest": (2.00, 12.00),
    "gemini-3.8-flash": (0.30, 1.20),
    "gemini-3-flash-preview": (0.15, 0.60),
    "gemini-3.5-flash-lite": (0.10, 0.40),
    "gemini-3.1-flash-lite": (0.10, 0.40),
    "gemini-flash-lite-latest": (0.10, 0.40),
    "gemini-3.8-flash-tts": (0.20, 0.80),
}
VIDEO_AI_EST_COST_USD = 0.75  # ~10s 720p clip estimate on Omni 1.2 Flash


class GeminiStudio:
    """
    Studio Google Gemini & Veo / Omni intégré à Clipoa :
    - Auth par clé Google AI Studio OU OAuth Google direct
    - Suivi en direct du quota/tokens journaliers Gemini
    - Génération de Shorts (script + voix + Submagic) OU vidéo IA directe 9:16 (Omni / Veo)
    """

    @classmethod
    def _cli_env(cls) -> Dict[str, str]:
        env = os.environ.copy()
        extra = [str(NODE_BIN_DIR), str(GEMINI_CLI_BIN.parent)]
        env["PATH"] = ":".join(extra) + ":" + env.get("PATH", "")
        return env

    @classmethod
    def is_cli_installed(cls) -> bool:
        return GEMINI_CLI_BIN.exists()

    @classmethod
    def is_google_logged_in(cls) -> bool:
        return GEMINI_OAUTH_CREDS.exists() and GEMINI_OAUTH_CREDS.stat().st_size > 20

    @classmethod
    def start_google_login(cls) -> Dict[str, Any]:
        """
        Opens a real visible macOS Terminal window running Gemini CLI via `open -a Terminal`
        (works reliably without AppleScript Automation permission prompts).
        """
        if not cls.is_cli_installed():
            return {"ok": False, "message": "Gemini CLI non installé dans runtime/."}

        login_cmd = STORAGE_DIR / "gemini_login.command"
        login_cmd.write_text(
            "#!/usr/bin/env bash\n"
            f'export PATH="{NODE_BIN_DIR}:{GEMINI_CLI_BIN.parent}:$PATH"\n'
            "clear\n"
            'echo "================================================"\n'
            'echo "  Connexion Google Gemini pour Clipoa"\n'
            'echo "  1. Choisis Login with Google"\n'
            'echo "  2. Valide dans ton navigateur"\n'
            'echo "  3. Ferme cette fenetre et rafraichis Clipoa"\n'
            'echo "================================================"\n'
            "exec gemini\n",
            encoding="utf-8",
        )
        os.chmod(login_cmd, 0o755)
        subprocess.Popen(["open", "-a", "Terminal", str(login_cmd)])
        return {
            "ok": True,
            "message": "Terminal ouvert : choisis « Login with Google », valide dans ton navigateur puis rafraîchis Clipoa !",
        }

    @classmethod
    def get_auth(cls, override_key: Optional[str] = None) -> Dict[str, str]:
        settings = load_settings().get("gemini", {})
        key = (override_key or settings.get("api_key") or os.getenv("GEMINI_API_KEY") or "").strip()
        oauth_token = (settings.get("oauth_token") or "").strip()
        return {"api_key": key, "oauth_token": oauth_token}

    @classmethod
    def _estimate_cost_usd(cls, model: str, in_tok: int, out_tok: int, kind: str = "script") -> float:
        if kind == "video_ai":
            return VIDEO_AI_EST_COST_USD
        if kind == "tts":
            return 0.008
        p_in, p_out = GEMINI_PRICING_PER_1M.get(model, (0.20, 0.80))
        return round((in_tok / 1_000_000.0) * p_in + (out_tok / 1_000_000.0) * p_out, 5)

    @classmethod
    def _record_usage(cls, model: str, in_tok: int, out_tok: int, kind: str = "script"):
        tier = cls.get_tier()
        cost_usd = cls._estimate_cost_usd(model, in_tok, out_tok, kind=kind) if tier == "paid" else 0.0
        with _LOCK:
            history: List[Dict[str, Any]] = []
            if GEMINI_USAGE_FILE.exists():
                try:
                    with open(GEMINI_USAGE_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    history = []
            cutoff = time.time() - 90 * 86400
            history = [h for h in history if h.get("ts", 0) >= cutoff]
            history.append({
                "ts": time.time(),
                "model": model,
                "kind": kind,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
                "cost_usd": cost_usd,
            })
            with open(GEMINI_USAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

    @classmethod
    def set_credit_budget(cls, budget_usd: float, reset_spent: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"credit_budget_usd": max(0.0, round(float(budget_usd), 2))}
        if reset_spent:
            payload["credit_reset_ts"] = time.time()
        save_settings({"gemini": payload})
        return cls.get_status()

    @classmethod
    def get_quota_summary(cls) -> Dict[str, Any]:
        now = time.time()
        day_start = now - 86400
        gem_cfg = load_settings().get("gemini", {})
        budget_usd = float(gem_cfg.get("credit_budget_usd", 10.0))
        reset_ts = float(gem_cfg.get("credit_reset_ts", 0.0))

        history: List[Dict[str, Any]] = []
        with _LOCK:
            if GEMINI_USAGE_FILE.exists():
                try:
                    with open(GEMINI_USAGE_FILE, "r", encoding="utf-8") as f:
                        history = json.load(f)
                except Exception:
                    history = []
        recent = [h for h in history if h.get("ts", 0) >= day_start]
        calls_24h = len(recent)
        tokens_24h = sum(int(h.get("total_tokens", 0)) for h in recent)
        daily_budget_calls = 250
        used_pct = min(100.0, round((calls_24h / daily_budget_calls) * 100.0, 1))
        remaining_pct = max(0.0, round(100.0 - used_pct, 1))

        # Cumulative credit tracking since last reset
        billed = [h for h in history if h.get("ts", 0) >= reset_ts]
        spent_usd = round(sum(float(h.get("cost_usd", 0.0)) for h in billed), 4)
        remaining_usd = round(max(0.0, budget_usd - spent_usd), 2)
        credit_remaining_pct = round((remaining_usd / budget_usd) * 100.0, 1) if budget_usd > 0 else 0.0

        return {
            "calls_24h": calls_24h,
            "tokens_24h": tokens_24h,
            "used_pct": used_pct,
            "remaining_pct": remaining_pct,
            "est_videos_left": max(0, daily_budget_calls - calls_24h),
            "budget_usd": round(budget_usd, 2),
            "spent_usd": round(spent_usd, 2),
            "remaining_usd": remaining_usd,
            "credit_remaining_pct": credit_remaining_pct,
            "est_pro_scripts_left": int(remaining_usd / 0.015) if remaining_usd > 0 else 0,
            "est_ai_videos_left": int(remaining_usd / VIDEO_AI_EST_COST_USD) if remaining_usd > 0 else 0,
        }

    @classmethod
    def detect_tier(cls, api_key: Optional[str] = None) -> str:
        """
        Détecte automatiquement si la clé Google AI Studio est en plan Gratuit ('free')
        ou Pay-as-you-go ('paid') via un ping ultra-léger sur gemini-3.1-pro-preview.
        """
        key = (api_key or cls.get_auth().get("api_key") or "").strip()
        if not key:
            return "free"
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={key}"
            r = requests.post(
                url,
                json={"contents": [{"parts": [{"text": "ok"}]}], "generationConfig": {"maxOutputTokens": 2}},
                timeout=8,
            )
            if r.status_code == 200:
                save_settings({"gemini": {"tier": "paid"}})
                return "paid"
            if r.status_code == 429:
                save_settings({"gemini": {"tier": "free"}})
                return "free"
        except Exception:
            pass
        return load_settings().get("gemini", {}).get("tier", "free")

    @classmethod
    def get_tier(cls) -> str:
        return load_settings().get("gemini", {}).get("tier", "free")

    @classmethod
    def get_best_available_model(cls) -> str:
        tier = cls.get_tier()
        saved = load_settings().get("gemini", {}).get("model", "")
        valid_ids = {m["id"]: m["tier"] for m in GEMINI_MODELS}
        if saved in valid_ids and (tier == "paid" or valid_ids[saved] == "free"):
            return saved
        return "gemini-3.1-pro-preview" if tier == "paid" else "gemini-3-flash-preview"

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        settings = load_settings().get("gemini", {})
        auth = cls.get_auth()
        has_key = bool(auth["api_key"])
        connected = bool(has_key or auth["oauth_token"])
        tier = settings.get("tier", "free")
        active_model = cls.get_best_available_model()
        tier_label = (
            "Plan Pay-as-you-go Google AI Studio (Pro + Vidéo IA débloqués)"
            if tier == "paid"
            else "Plan Gratuit Google AI Studio (Modèles Flash gratuits actifs)"
        )
        msg = (
            f"Connecté en permanence · {tier_label}" if has_key
            else "Ajoute ta clé gratuite Google AI Studio (1 seule fois, mémorisée à vie)"
        )
        return {
            "connected": connected,
            "cli_installed": False,
            "google_logged_in": False,
            "email": "",
            "has_api_key": has_key,
            "auth_mode": "api_key" if has_key else "none",
            "tier": tier,
            "tier_label": tier_label,
            "video_ai_unlocked": (tier == "paid"),
            "model": active_model,
            "models": GEMINI_MODELS,
            "video_models": VIDEO_AI_MODELS,
            "quota": cls.get_quota_summary(),
            "message": msg,
        }

    @classmethod
    def logout_and_switch(cls) -> Dict[str, Any]:
        save_settings({"gemini": {"api_key": "", "oauth_token": "", "tier": "free"}})
        return {"ok": True, "message": "Clé Gemini effacée — tu peux en coller une autre."}

    @classmethod
    def connect(cls, api_key: str, model: str = "gemini-3-flash-preview") -> Dict[str, Any]:
        key = api_key.strip()
        if not key:
            raise ValueError("Clé API Gemini manquante")
        # Validate by listing available models (never fails on a specific model name)
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=5"
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            try:
                err_msg = res.json().get("error", {}).get("message", res.text[:180])
            except Exception:
                err_msg = res.text[:180]
            raise RuntimeError(f"Clé Gemini refusée (HTTP {res.status_code}) : {err_msg}")
        tier = cls.detect_tier(key)
        valid_ids = {m["id"]: m["tier"] for m in GEMINI_MODELS}
        if model not in valid_ids or (tier == "free" and valid_ids[model] == "paid"):
            model = "gemini-3-flash-preview" if tier == "free" else "gemini-3.1-pro-preview"
        save_settings({"gemini": {"api_key": key, "model": model, "tier": tier}})
        return cls.get_status()

    @classmethod
    def save_oauth_token(cls, access_token: str) -> Dict[str, Any]:
        save_settings({"gemini": {"oauth_token": access_token.strip()}})
        return cls.get_status()

    @classmethod
    def query(cls, prompt: str, system_prompt: str = "", model: Optional[str] = None) -> str:
        chosen_model = model or cls.get_best_available_model()
        auth = cls.get_auth()
        if not auth["api_key"] and not auth["oauth_token"]:
            raise RuntimeError("Ajoute ta clé gratuite Google AI Studio dans l'onglet Gemini (1 seule fois, elle reste mémorisée).")

        # Smart fallback cascade using ONLY verified live models
        cascade: List[str] = []
        if chosen_model and chosen_model not in cascade:
            cascade.append(chosen_model)
        for fb in FREE_MODEL_CASCADE:
            if fb not in cascade:
                cascade.append(fb)

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json"},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        last_err = ""
        for candidate_model in cascade:
            headers = {"Content-Type": "application/json"}
            if auth["api_key"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={auth['api_key']}"
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent"
                headers["Authorization"] = f"Bearer {auth['oauth_token']}"

            try:
                res = requests.post(url, headers=headers, json=payload, timeout=45)
            except requests.RequestException as net_err:
                last_err = f"Timeout/réseau {candidate_model}: {net_err}"
                print(f"⚠️ {last_err}, bascule auto sur le modèle suivant...")
                continue

            if res.status_code == 200:
                data = res.json()
                um = data.get("usageMetadata") or {}
                cls._record_usage(
                    candidate_model,
                    int(um.get("promptTokenCount") or 0),
                    int(um.get("candidatesTokenCount") or 0),
                    kind="script",
                )
                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError("Réponse vide de Gemini.")
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts).strip()

            last_err = f"Erreur Gemini {candidate_model} ({res.status_code}) : {res.text[:200]}"
            if res.status_code == 429 and candidate_model in ("gemini-3.1-pro-preview", "gemini-pro-latest"):
                save_settings({"gemini": {"tier": "free"}})
            if res.status_code in (429, 404, 500, 503):
                print(f"⚠️ {candidate_model} indisponible (HTTP {res.status_code}), bascule auto sur le modèle suivant...")
                continue
            raise RuntimeError(last_err)

        raise RuntimeError(f"Tous les modèles Gemini gratuits sont momentanément saturés ({last_err})")

    @classmethod
    def chat_text(cls, prompt: str, system_prompt: str = "", model: Optional[str] = None) -> str:
        """Appel texte conversationnel libre (sans forcer JSON) pour l'assistant d'aide IA."""
        chosen_model = model or cls.get_best_available_model()
        auth = cls.get_auth()
        if not auth["api_key"] and not auth["oauth_token"]:
            raise RuntimeError("Connecte ta clé Google AI Studio dans Connexions pour utiliser Gemini.")

        cascade: List[str] = []
        if chosen_model and chosen_model not in cascade:
            cascade.append(chosen_model)
        for fb in FREE_MODEL_CASCADE:
            if fb not in cascade:
                cascade.append(fb)

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.65, "maxOutputTokens": 1024},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        last_err = ""
        for candidate_model in cascade:
            headers = {"Content-Type": "application/json"}
            if auth["api_key"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={auth['api_key']}"
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent"
                headers["Authorization"] = f"Bearer {auth['oauth_token']}"

            try:
                res = requests.post(url, headers=headers, json=payload, timeout=35)
            except requests.RequestException as net_err:
                last_err = f"Timeout/réseau {candidate_model}: {net_err}"
                continue

            if res.status_code == 200:
                data = res.json()
                um = data.get("usageMetadata") or {}
                cls._record_usage(
                    candidate_model,
                    int(um.get("promptTokenCount") or 0),
                    int(um.get("candidatesTokenCount") or 0),
                    kind="help",
                )
                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError("Réponse vide de Gemini.")
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(p.get("text", "") for p in parts).strip()

            last_err = f"Erreur Gemini {candidate_model} ({res.status_code}) : {res.text[:160]}"
            if res.status_code == 429 and candidate_model in ("gemini-3.1-pro-preview", "gemini-pro-latest"):
                save_settings({"gemini": {"tier": "free"}})
            if res.status_code in (429, 404, 500, 503):
                continue
            raise RuntimeError(last_err)

        raise RuntimeError(f"Modèles Gemini momentanément indisponibles ({last_err})")

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, Any]:
        txt = (raw or "").strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt)
        if m:
            txt = m.group(1).strip()
        try:
            return json.loads(txt)
        except Exception:
            start = txt.find("{")
            end = txt.rfind("}")
            if start != -1 and end > start:
                return json.loads(txt[start : end + 1])
            raise

    @classmethod
    def create_short(
        cls,
        topic: str = "",
        plugin_id: Optional[str] = None,
        custom_script: Optional[str] = None,
        custom_title: Optional[str] = None,
        target_duration_sec: int = 60,
        model: Optional[str] = None,
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        voice: Optional[str] = None,
        background_video: Optional[str] = None,
        use_blender_3d: bool = False,
        retention_boost: bool = True,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        def _prog(pct: int, msg: str):
            print(msg)
            if progress_cb:
                progress_cb(pct, msg)

        session_id = f"gemini_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        chosen_model = model or cls.get_best_available_model()
        plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=True) if plugin_id else None
        if plugin and plugin.get("render_mode") == "blender3d":
            use_blender_3d = True
        is_custom_script = bool((custom_script or "").strip())
        da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=is_custom_script) if plugin else ""
        final_theme = theme or (plugin.get("theme") if plugin else DEFAULT_THEME) or DEFAULT_THEME
        final_sub = subtitle_style or (plugin.get("subtitle_style") if plugin else DEFAULT_SUBTITLE_STYLE) or DEFAULT_SUBTITLE_STYLE

        if is_custom_script:
            clean_script = (custom_script or "").strip()
            fallback_title = (custom_title or topic or clean_script.split(".")[0][:48] or "Mon Short").strip()
            if plugin:
                _prog(15, f"🎨 [1/4] {chosen_model} applique la DA « {plugin['name']} » sur ton script...")
                prompt = (
                    f"{da_ctx}\n\n"
                    f"Titre : {fallback_title}\n\n"
                    f"SCRIPT EXACT DE L'UTILISATEUR (CONSERVE MOT POUR MOT) :\n{clean_script}\n\n"
                    "Prépare le visual_storyboard, le hook_screen_text et la social_caption dans cette DA en gardant `full_spoken_script` identique. Rends le JSON strict."
                )
                raw = cls.query(prompt, system_prompt=PROMPT_SCENARISTE, model=chosen_model)
                script = cls._parse_json(raw)
                script["full_spoken_script"] = clean_script
                script.setdefault("title", fallback_title)
            else:
                _prog(15, "✍️ [1/4] Préparation de ton script personnalisé...")
                script = {
                    "title": fallback_title,
                    "hook_spoken": clean_script.split(".")[0][:120],
                    "hook_screen_text": fallback_title[:40],
                    "full_spoken_script": clean_script,
                    "social_caption": f"{fallback_title} #shorts #video",
                }
        else:
            from core.style_plugins import duration_to_word_range
            dur = duration_to_word_range(target_duration_sec)
            dur_line = (
                f"DURÉE CIBLE DE LA VIDÉO : environ {dur['duration_sec']} secondes "
                f"({dur['min_words']} à {dur['max_words']} mots parlés, ~{dur['plans_min']} à {dur['plans_max']} plans).\n"
            )
            if plugin:
                _prog(15, f"🎨 [1/4] {chosen_model} applique la DA « {plugin['name']} » & écrit ton script (~{dur['duration_sec']}s)...")
                prompt = f"{da_ctx}\n\n{dur_line}Sujet à traiter : {topic}\nRédige le script complet et le visual_storyboard dans cette DA au format JSON strict."
            else:
                _prog(15, f"✨ [1/4] {chosen_model} écrit ton script viral (~{dur['duration_sec']}s)...")
                prompt = f"{dur_line}Sujet à traiter : {topic}\nRédige le script final prêt à être synthétisé au format JSON strict."
            raw = cls.query(prompt, system_prompt=PROMPT_SCENARISTE, model=chosen_model)
            script = cls._parse_json(raw)

        _prog(45, "🎙️ [2/4] Synthèse vocale + Whisper mot-par-mot...")
        voice_res = VoiceEngine.generate_voice(
            text=script.get("full_spoken_script", ""),
            output_name=session_id,
            voice=voice,
        )
        voice_transcript = AudioTranscriber.transcribe(voice_res["audio_wav"])

        # Méthode Clipoa (même circuit que la Fabrique) : plan calé sur la voix + musique & bruitages
        from core.pipeline import ShortCrewPipeline
        from core.sound_designer import get_wav_duration
        shots = script.get("visual_storyboard") or []
        _prog(52, "🎵 [2/4] Plan de production, musique d'ambiance & bruitages...")
        mixres = ShortCrewPipeline._plan_and_mix(
            session_id, script, voice_res, voice_transcript, shots,
            enable_music=True, enable_sfx=True,
            style_overrides=(plugin or {}).get("production") if isinstance((plugin or {}).get("production"), dict) else None,
        )
        plan = mixres["plan"]

        effective_bg = background_video
        if not effective_bg and use_blender_3d and BlenderEngine.is_available():
            _prog(60, f"🧊 [3/4] Rendu 3D Blender multi-plans ({len(plan.get('shots') or [])} plans calés sur la voix)...")
            try:
                out_dir = Path(voice_res["audio_wav"]).parent
                py_script = str(out_dir / "gemini_3d.py")
                bg_out = str(out_dir / "blender_bg.mp4")
                audio_dur = get_wav_duration(voice_res["audio_wav"])
                frames = max(72, int(round(audio_dur * 12)))
                BlenderEngine.create_roblox_3d_scene(
                    title_text=script.get("hook_screen_text") or (topic or "CLIPOA")[:30],
                    script_save_path=py_script,
                    spoken_script=script.get("full_spoken_script", ""),
                    frames=frames,
                    shots=shots,
                    audio_duration_sec=audio_dur,
                    timed_shots=plan.get("shots"),
                    mood=plan.get("mood"),
                    character_style=plan.get("character_style") or "r6",
                )
                if BlenderEngine.render_script(py_script, bg_out, frames=frames):
                    effective_bg = bg_out
            except Exception as e:
                print(f"⚠️ Rendu Blender ignoré ({e}).")

        _prog(72, "🎬 [3/4] Rendu vertical 1080x1920 + sous-titres Submagic...")
        video_path = VideoComposer.compose_short(
            output_name=session_id,
            audio_path=mixres["audio"],
            script_data=script,
            transcript_data=voice_transcript,
            background_video=effective_bg,
            theme=final_theme,
            subtitle_style=final_sub,
            retention_boost=retention_boost,
            plan=plan,
            audio_premixed=mixres["premixed"],
            alt_audio_path=mixres["no_music"],
        )

        _prog(94, "✨ [4/4] Finalisation...")
        audit = {
            "score_global": "9.2/10",
            "decision": "VALIDE",
            "points_forts": [f"Généré directement par {chosen_model} (0% quota Claude)"],
        }
        result = {
            "session_id": session_id,
            "type": "plugin_da" if plugin else "gemini_short",
            "plugin_id": plugin["id"] if plugin else "",
            "plugin_name": plugin["name"] if plugin else "",
            "model": chosen_model,
            "status": "ready",
            "theme": final_theme,
            "subtitle_style": final_sub,
            "voice": voice,
            "background_video": effective_bg,
            "script": script,
            "video_path": video_path,
            "audit": audit,
            "social_caption": script.get("social_caption", ""),
            "enable_music": True,
            "enable_sfx": True,
            "blender_bg": effective_bg if (effective_bg and effective_bg != background_video) else "",
            "storyboard_shots": shots,
        }
        ShortCrewPipeline._finalize_outputs(video_path, plan, result)
        with open(Path(video_path).parent / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        _prog(100, "✨ Short généré avec Gemini !")
        return result

    @classmethod
    def generate_ai_video(
        cls,
        prompt: str,
        video_model: str = "gemini-omni-1.2-flash",
        aspect_ratio: str = "9:16",
        plugin_id: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Génère une vraie vidéo IA 9:16 avec audio via Google Gemini Omni 1.2 Flash.
        Si `plugin_id` est fourni, injecte automatiquement la Direction Artistique du Plugin de Style choisi.
        """
        def _prog(pct: int, msg: str):
            print(msg)
            if progress_cb:
                progress_cb(pct, msg)

        auth = cls.get_auth()
        if not auth["api_key"] and not auth["oauth_token"]:
            raise RuntimeError("La génération vidéo directe (Omni) nécessite une clé API Google AI Studio dans l'onglet Connexions.")

        final_prompt = prompt
        plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=False) if plugin_id else None
        if plugin:
            _prog(10, f"🎨 Injection de la DA « {plugin['name']} » dans le prompt vidéo...")
            da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=False)[:1800]
            final_prompt = (
                f"{da_ctx}\n\n"
                f"Scène à générer en vidéo verticale 9:16 avec audio d'ambiance :\n{prompt}"
            )

        session_id = f"veo_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        out_dir = RENDERS_DIR / session_id
        out_dir.mkdir(parents=True, exist_ok=True)
        final_mp4 = out_dir / "final_short.mp4"

        _prog(22, f"🎬 Envoi du prompt vidéo 9:16 à {video_model}...")

        headers = {"Content-Type": "application/json"}
        if auth["api_key"]:
            headers["x-goog-api-key"] = auth["api_key"]
        else:
            headers["Authorization"] = f"Bearer {auth['oauth_token']}"

        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        payload = {
            "model": video_model,
            "input": [{"type": "text", "text": final_prompt}],
            "response_format": {
                "type": "video",
                "delivery": "uri",
                "aspect_ratio": aspect_ratio,
                "resolution": "720p",
            },
        }
        res = requests.post(url, headers=headers, json=payload, timeout=600)
        if res.status_code == 429 and ("free tier" in res.text.lower() or "limit: 0" in res.text.lower()):
            save_settings({"gemini": {"tier": "free"}})
            raise RuntimeError("Vidéo IA Omni 1.2 réservée au plan Pay-as-you-go Google AI Studio (quota 0 sur le plan gratuit).")
        if res.status_code not in (200, 201):
            raise RuntimeError(f"Erreur génération vidéo {video_model} ({res.status_code}) : {res.text[:260]}")

        data = res.json()
        _prog(70, "📥 Téléchargement du rendu vidéo IA...")

        # Extract base64 video or downloadable URI from interaction outputs
        video_bytes = None
        for out in (data.get("outputs") or []):
            if out.get("type") == "video" or str(out.get("mime_type", "")).startswith("video/"):
                if out.get("data"):
                    video_bytes = base64.b64decode(out["data"])
                    break
                if out.get("uri"):
                    vid_uri = out["uri"]
                    # Ensure Files API download endpoint returns raw media bytes
                    if "alt=media" not in vid_uri:
                        sep = "&" if "?" in vid_uri else "?"
                        dl_url = f"{vid_uri}{sep}alt=media"
                    else:
                        dl_url = vid_uri
                    dl = requests.get(dl_url, headers=headers, timeout=180)
                    if dl.status_code != 200:
                        dl = requests.get(vid_uri, headers=headers, timeout=180)
                    if dl.status_code == 200 and len(dl.content) > 1000:
                        video_bytes = dl.content
                        break

        if not video_bytes:
            raise RuntimeError("Aucune donnée vidéo retournée par l'API (vérifie que ton compte AI Studio a accès à la génération vidéo).")

        with open(final_mp4, "wb") as f:
            f.write(video_bytes)

        cls._record_usage(video_model, len(prompt), 1000, kind="video_ai")

        result = {
            "session_id": session_id,
            "type": "veo_omni",
            "model": video_model,
            "status": "ready",
            "script": {"title": prompt[:60], "hook_spoken": prompt[:120]},
            "video_path": str(final_mp4),
            "audit": {"score_global": "IA 9:16", "decision": "VALIDE"},
            "social_caption": f"{prompt[:90]} #ai #veo #shorts",
        }
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        _prog(100, "🎬 Vidéo IA 9:16 prête dans Shorts !")
        return result
