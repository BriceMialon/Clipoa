import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STORAGE_DIR
from core.settings_store import load_settings, save_settings

logger = logging.getLogger("AntigravityBridge")
AGY_USAGE_FILE = STORAGE_DIR / "antigravity_usage.json"
_AGY_LOCK = threading.Lock()
AGY_WINDOW_BUDGET_TOKENS = 250_000  # ~250k tokens / 5h rolling estimate for Antigravity CLI

DEFAULT_AGY_CANDIDATES = [
    "/Applications/Gemini.app/Contents/Helpers/agy",
    "/usr/local/bin/agy",
    str(Path.home() / ".local" / "bin" / "agy"),
]

FALLBACK_AGY_MODELS: List[Dict[str, str]] = [
    {"id": "gemini-4-neon-medium", "label": "Gemini 4 Neon (Medium)"},
    {"id": "gemini-4-neon-high", "label": "Gemini 4 Neon (High)"},
    {"id": "claude-opus-5-5-medium", "label": "Claude Opus 5.5 (Medium)"},
    {"id": "claude-sonnet-5-5-medium", "label": "Claude Sonnet 5.5 (Medium)"},
]

_UNSAFE_BLENDER_TOKENS = (
    "import subprocess",
    "from subprocess",
    "import socket",
    "from socket",
    "import urllib",
    "from urllib",
    "import requests",
    "from requests",
    "os.system(",
    "os.popen(",
    "os.remove(",
    "os.unlink(",
    "shutil.rmtree(",
    "eval(",
    "exec(",
    "__import__(",
)


class AntigravityBridge:
    """
    Pont vers Google Antigravity CLI (`agy`) pour Clipoa :
    - Utilise la session Antigravity connectée sur le Mac (même principe que ClaudeBridge)
    - Permet de choisir le modèle Antigravity dans la Fabrique, l'Aide IA et la génération 3D Blender
    - Génère des scripts Python Blender (`bpy`) personnalisés adaptés au sujet et à la DA choisie
    """

    _cached_connected: Optional[bool] = None
    _cached_models: Optional[List[Dict[str, str]]] = None

    @classmethod
    def find_cli(cls) -> str:
        env_path = os.environ.get("AGY_CLI_PATH", "").strip()
        if env_path and os.path.exists(env_path):
            return env_path
        found = shutil.which("agy")
        if found:
            return found
        for cand in DEFAULT_AGY_CANDIDATES:
            if os.path.exists(cand):
                return cand
        return ""

    @classmethod
    def _parse_models_output(cls, raw: str) -> List[Dict[str, str]]:
        models: List[Dict[str, str]] = []
        seen = set()
        for line in (raw or "").splitlines():
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if not clean or clean.startswith(("─", "═", "Model", "NAME", "ID", "Available", "Error:")):
                continue
            # Match typical table/bullet lines: e.g. "* gemini-3-pro   Gemini 3 Pro" or "claude-sonnet-4-6"
            clean = re.sub(r"^[\*\-•>✓\s]+", "", clean).strip()
            if not clean:
                continue
            parts = re.split(r"\s{2,}|\t", clean, maxsplit=1)
            mid = parts[0].strip().split()[0]
            if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,80}$", mid):
                continue
            if mid.lower() in ("model", "models", "id", "name", "provider", "status", "default"):
                continue
            if mid in seen:
                continue
            seen.add(mid)
            label = parts[1].strip() if len(parts) > 1 and parts[1].strip() else mid
            models.append({"id": mid, "label": label[:70]})
        return models

    @classmethod
    def check_status(cls, live_probe: bool = False) -> Dict[str, Any]:
        cli_path = cls.find_cli()
        cli_exists = bool(cli_path)
        connected = False
        models: List[Dict[str, str]] = list(FALLBACK_AGY_MODELS)
        message = ""

        if cli_exists:
            if live_probe or cls._cached_connected is None:
                try:
                    res = subprocess.run(
                        [cli_path, "models"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    combined = (res.stdout + "\n" + res.stderr).strip()
                    low = combined.lower()
                    if res.returncode == 0 and "please sign in" not in low and "not logged in" not in low:
                        connected = True
                        parsed = cls._parse_models_output(res.stdout)
                        if parsed:
                            models = parsed
                    else:
                        connected = False
                except Exception as e:
                    logger.warning(f"agy models probe failed: {e}")
                    connected = False
                cls._cached_connected = connected
                cls._cached_models = models
            else:
                connected = bool(cls._cached_connected)
                if cls._cached_models:
                    models = list(cls._cached_models)

            message = (
                "Connecté à Antigravity CLI (agy) · prêt pour scripts & scènes 3D Blender"
                if connected
                else "Antigravity CLI trouvé — clique sur « Connecter Antigravity » pour te connecter une fois"
            )
        else:
            message = "Antigravity CLI (agy) introuvable sur ce Mac"

        saved_model = load_settings().get("antigravity", {}).get("model", "")
        valid_ids = {m["id"] for m in models}
        if saved_model in valid_ids:
            active_model = saved_model
        elif "gemini-4-neon-medium" in valid_ids:
            active_model = "gemini-4-neon-medium"
        else:
            active_model = models[0]["id"] if models else ""

        return {
            "connected": connected,
            "cli_exists": cli_exists,
            "cli_path": cli_path,
            "model": active_model,
            "models": models,
            "quota": cls.get_quota_summary(),
            "message": message,
        }

    @classmethod
    def _record_usage(cls, model: str, input_chars: int, output_chars: int) -> None:
        in_tok = max(1, int(round(input_chars / 3.8)))
        out_tok = max(1, int(round(output_chars / 3.8)))
        entry = {
            "ts": time.time(),
            "model": model or "gemini-4-neon-medium",
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        }
        with _AGY_LOCK:
            history: List[Dict[str, Any]] = []
            if AGY_USAGE_FILE.exists():
                try:
                    history = json.loads(AGY_USAGE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []
            history.append(entry)
            cutoff = time.time() - 7 * 86400
            history = [h for h in history if h.get("ts", 0) >= cutoff][-300:]
            try:
                AGY_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
                AGY_USAGE_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
            except Exception:
                pass

    @classmethod
    def get_quota_summary(cls) -> Dict[str, Any]:
        now = time.time()
        window_5h = now - 5 * 3600
        window_7d = now - 7 * 86400
        history: List[Dict[str, Any]] = []
        with _AGY_LOCK:
            if AGY_USAGE_FILE.exists():
                try:
                    history = json.loads(AGY_USAGE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []
        recent = [h for h in history if h.get("ts", 0) >= window_5h]
        tokens_used = sum(int(h.get("total_tokens", 0)) for h in recent)
        tokens_left = max(0, AGY_WINDOW_BUDGET_TOKENS - tokens_used)
        used_pct = min(100.0, round((tokens_used / max(1, AGY_WINDOW_BUDGET_TOKENS)) * 100.0, 1))
        remaining_pct = max(0.0, round(100.0 - used_pct, 1))

        weekly_budget = AGY_WINDOW_BUDGET_TOKENS * 8
        recent_7d = [h for h in history if h.get("ts", 0) >= window_7d]
        tokens_used_7d = sum(int(h.get("total_tokens", 0)) for h in recent_7d)
        used_pct_7d = min(100.0, round((tokens_used_7d / max(1, weekly_budget)) * 100.0, 1))
        remaining_pct_7d = max(0.0, round(100.0 - used_pct_7d, 1))

        return {
            "calls_5h": len(recent),
            "tokens_used_5h": tokens_used,
            "tokens_left_5h": tokens_left,
            "budget_tokens_5h": AGY_WINDOW_BUDGET_TOKENS,
            "used_pct": used_pct,
            "remaining_pct": remaining_pct,
            "used_pct_7d": used_pct_7d,
            "remaining_pct_7d": remaining_pct_7d,
            "est_videos_left": max(0, tokens_left // 4500),
        }

    @classmethod
    def set_model(cls, model_id: str) -> Dict[str, Any]:
        mid = (model_id or "").strip()[:90]
        save_settings({"antigravity": {"model": mid}})
        return cls.check_status(live_probe=False)

    @classmethod
    def start_cli_login(cls) -> Dict[str, Any]:
        cli_path = cls.find_cli()
        if not cli_path:
            return {"ok": False, "message": "Antigravity CLI (agy) introuvable sur ce Mac."}

        login_cmd = STORAGE_DIR / "antigravity_login.command"
        login_cmd.write_text(
            "#!/usr/bin/env bash\n"
            "clear\n"
            'echo "================================================"\n'
            'echo "  Connexion Antigravity CLI (agy) pour Clipoa"\n'
            'echo "  1. Connecte-toi avec ton compte Google / Antigravity"\n'
            'echo "  2. Une fois connecte, ferme ce Terminal"\n'
            'echo "  3. Clique sur Rafraichir dans Clipoa !"\n'
            'echo "================================================"\n'
            f'exec "{cli_path}"\n',
            encoding="utf-8",
        )
        os.chmod(login_cmd, 0o755)
        subprocess.Popen(["open", "-a", "Terminal", str(login_cmd)])
        cls._cached_connected = None
        return {
            "ok": True,
            "message": "Terminal ouvert : connecte-toi à Antigravity, puis clique sur « Rafraîchir » dans Clipoa !",
        }

    @classmethod
    def switch_account(cls) -> Dict[str, Any]:
        """Efface les identifiants OAuth locaux d'Antigravity CLI et ouvre le Terminal pour choisir un autre compte."""
        for cred_file in (
            Path.home() / ".gemini" / "antigravity-cli" / "oauth_creds.json",
            Path.home() / ".gemini" / "antigravity-cli" / "credentials.json",
            Path.home() / ".gemini" / "oauth_creds.json",
        ):
            try:
                if cred_file.exists():
                    cred_file.unlink()
            except OSError:
                pass
        cls._cached_connected = None
        cls._cached_models = None
        res = cls.start_cli_login()
        res["message"] = "Compte Antigravity réinitialisé — choisis ton nouveau compte Google dans le Terminal puis clique sur ↻ !"
        return res

    @classmethod
    def _empty_cwd(cls) -> str:
        """Dossier vide dédié pour lancer `agy -p` sans charger le repo ni déclencher d'outils."""
        d = STORAGE_DIR / "_agy_sandbox"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    @staticmethod
    def _wrap_no_tools_prompt(prompt: str, system_prompt: Optional[str] = None) -> str:
        guard = (
            "RÈGLE ABSOLUE : N'UTILISE AUCUN OUTIL (aucune lecture/écriture de fichier, aucune commande terminal, aucune recherche). "
            "Réponds directement et uniquement en texte.\n\n"
        )
        if system_prompt:
            return f"{guard}{system_prompt.strip()}\n\n{prompt.strip()}"
        return f"{guard}{prompt.strip()}"

    @classmethod
    def query(
        cls,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 180,
    ) -> str:
        cli_path = cls.find_cli()
        if not cli_path:
            raise RuntimeError("Antigravity CLI (agy) introuvable sur ce Mac.")

        full_prompt = cls._wrap_no_tools_prompt(prompt, system_prompt)
        chosen_model = (model or load_settings().get("antigravity", {}).get("model") or "gemini-4-neon-medium").strip()

        cmd = [
            cli_path,
            "-p",
            full_prompt,
            "--output-format",
            "text",
            "--disable-slash-commands",
        ]
        if chosen_model:
            cmd.extend(["--model", chosen_model])

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cls._empty_cwd())
        combined = (res.stdout + "\n" + res.stderr).strip()
        low = combined.lower()
        if "please sign in" in low or "not logged in" in low:
            cls._cached_connected = False
            raise RuntimeError("Antigravity CLI n'est pas connecté. Ouvre Connexions → Connecter Antigravity.")
        if res.returncode != 0 or not res.stdout.strip():
            raise RuntimeError(f"Erreur Antigravity CLI : {combined[:220]}")

        cls._cached_connected = True
        out_txt = res.stdout.strip()
        cls._record_usage(chosen_model, len(full_prompt), len(out_txt))
        return out_txt

    @classmethod
    def stream_query(
        cls,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 300,
    ):
        """
        Exécute `agy -p ... --output-format stream-json` et yield les morceaux de texte (`text_delta`)
        en temps réel au fur et à mesure de la génération.
        """
        cli_path = cls.find_cli()
        if not cli_path:
            raise RuntimeError("Antigravity CLI (agy) introuvable sur ce Mac.")

        full_prompt = cls._wrap_no_tools_prompt(prompt, system_prompt)
        chosen_model = (model or load_settings().get("antigravity", {}).get("model") or "gemini-4-neon-medium").strip()

        cmd = [
            cli_path,
            "-p",
            full_prompt,
            "--output-format",
            "stream-json",
            "--disable-slash-commands",
        ]
        if chosen_model:
            cmd.extend(["--model", chosen_model])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cls._empty_cwd(),
        )
        full_chunks: List[str] = []
        started = time.time()
        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                if time.time() - started > timeout:
                    proc.kill()
                    raise RuntimeError("Délai dépassé pendant la génération du script.")
                line = raw_line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                ev_type = ev.get("event")
                if ev_type == "step_update":
                    su = ev.get("step_update") or {}
                    if su.get("step_type") == "agent_response":
                        delta = su.get("text_delta") or ""
                        if delta:
                            full_chunks.append(delta)
                            yield delta
                elif ev_type == "result":
                    res_obj = ev.get("result") or {}
                    if not full_chunks and res_obj.get("response"):
                        resp_txt = str(res_obj["response"])
                        full_chunks.append(resp_txt)
                        yield resp_txt
            proc.wait(timeout=15)
            if proc.returncode != 0 and not full_chunks:
                err_txt = (proc.stderr.read() if proc.stderr else "")[:220]
                if "please sign in" in err_txt.lower() or "not logged in" in err_txt.lower():
                    cls._cached_connected = False
                    raise RuntimeError("Antigravity CLI n'est pas connecté.")
                raise RuntimeError(f"Erreur Antigravity CLI : {err_txt or 'code ' + str(proc.returncode)}")
            cls._cached_connected = True
            cls._record_usage(chosen_model, len(full_prompt), sum(len(c) for c in full_chunks))
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    @staticmethod
    def extract_python_code(raw: str) -> str:
        txt = (raw or "").strip()
        m = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", txt)
        if m:
            txt = m.group(1).strip()
        return txt

    @staticmethod
    def validate_blender_script(code: str) -> bool:
        if not code or "import bpy" not in code:
            return False
        low = code.lower()
        for bad in _UNSAFE_BLENDER_TOKENS:
            if bad in low:
                logger.warning(f"Rejected generated Blender script containing forbidden token: {bad}")
                return False
        try:
            compile(code, "<blender_generated>", "exec")
        except SyntaxError as e:
            logger.warning(f"Generated Blender script syntax error: {e}")
            return False
        return True

    @classmethod
    def generate_blender_script(
        cls,
        topic: str,
        spoken_script: str,
        script_save_path: str,
        da_context: str = "",
        visual_storyboard: Optional[List[Dict[str, Any]]] = None,
        frames: int = 150,
        engine: str = "antigravity",
        model: Optional[str] = None,
    ) -> bool:
        """
        Demande à Antigravity (ou Claude / Gemini) d'écrire un vrai script Python Blender (`bpy`)
        compatible Blender 5.x, adapté au sujet, au storyboard et à la Direction Artistique choisie
        (ex. 3D Roblox, 2D×Monde 3D).
        Retourne True si un script valide a été écrit, False sinon (le pipeline utilise alors le fallback).
        """
        sys_prompt = (
            "Tu es un artiste technique Blender 3D expert (bpy Python API, compatible Blender 4.x et 5.3).\n"
            "Écris UNIQUEMENT un script Python complet et autonome (sans texte autour, dans un bloc ```python```) "
            "qui construit une vraie scène 3D verticale 9:16 animée correspondant au sujet, au storyboard et à la Direction Artistique.\n"
            "Contraintes STRICTES Blender 5.3 :\n"
            "1. Commence par `import bpy`, `import math` (et `import random` si utile). Aucun import réseau/système (`os`, `subprocess`, `socket`, `requests`).\n"
            "2. Réinitialise la scène avec `bpy.ops.wm.read_factory_settings(use_empty=True)`.\n"
            f"3. Configure le rendu vertical 9:16 H.264 MP4 EXACTEMENT ainsi :\n"
            "   scene = bpy.context.scene\n"
            "   scene.render.engine = 'BLENDER_EEVEE'\n"
            "   scene.render.resolution_x = 1080\n"
            "   scene.render.resolution_y = 1920\n"
            "   scene.render.resolution_percentage = 100\n"
            "   scene.render.fps = 30\n"
            f"   scene.frame_start = 1; scene.frame_end = {int(frames)}\n"
            "   if hasattr(scene.render.image_settings, 'media_type'): scene.render.image_settings.media_type = 'VIDEO'\n"
            "   scene.render.image_settings.file_format = 'FFMPEG'\n"
            "   scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'\n"
            "   scene.render.use_file_extension = False\n"
            "   if hasattr(scene, 'eevee') and hasattr(scene.eevee, 'taa_render_samples'): scene.eevee.taa_render_samples = 16\n"
            "4. Crée une VRAIE scène 3D visuelle fidèle au style (ex : pour 3D Roblox → avatars R6 en blocs + rue/maisons low-poly + ciel bleu ; pour 2D×Monde 3D → village/décor 3D low-poly atmosphérique + personnages stylisés + objet lumineux), avec éclairage soigné et caméra en mouvement fluide (keyframes de frame 1 à frame_end).\n"
            "5. N'utilise aucun fichier externe (textures/HDRI/meshes externes interdits) : tout doit être 100% procédural en `bpy`."
        )
        da_snippet = (da_context or "")[:900]
        da_block = f"Direction Artistique à respecter :\n{da_snippet}\n" if da_snippet else ""
        sb_lines = []
        if isinstance(visual_storyboard, list):
            for s in visual_storyboard[:3]:
                if isinstance(s, dict) and s.get("visual"):
                    sb_lines.append(f"- {s.get('timestamp_approx', '')}: {str(s.get('visual'))[:160]}")
        sb_block = ("Storyboard des plans clés :\n" + "\n".join(sb_lines) + "\n") if sb_lines else ""
        user_prompt = (
            f"Sujet : {topic}\n"
            f"Script parlé (extrait) : {(spoken_script or '')[:400]}\n"
            f"{sb_block}"
            f"{da_block}"
            f"Durée : {int(frames)} frames à 30 fps.\n"
            "Écris un script Python Blender court, propre et rapide (<= 140 lignes)."
        )

        try:
            eng = (engine or "antigravity").lower()
            if eng == "antigravity":
                raw = cls.query(user_prompt, system_prompt=sys_prompt, model=model, timeout=110)
            elif eng == "gemini":
                from core.gemini_studio import GeminiStudio
                raw = GeminiStudio.chat_text(user_prompt, system_prompt=sys_prompt, model=model)
            else:
                from core.claude_bridge import ClaudeBridge
                raw = ClaudeBridge.query(user_prompt, system_prompt=sys_prompt, action="blender_3d", model=model)

            code = cls.extract_python_code(raw)
            if not cls.validate_blender_script(code):
                return False

            # Safe Blender 3/4/5 EEVEE + MP4 compatibility guard
            shim = (
                "\n# Clipoa Blender 5.x compatibility guard\n"
                "try:\n"
                "    import bpy as _cbpy\n"
                "    _sc = _cbpy.context.scene\n"
                "    if hasattr(_sc.render.image_settings, 'media_type'):\n"
                "        _sc.render.image_settings.media_type = 'VIDEO'\n"
                "    _sc.render.image_settings.file_format = 'FFMPEG'\n"
                "    _sc.render.ffmpeg.format = 'MPEG4'\n"
                "    _sc.render.ffmpeg.codec = 'H264'\n"
                "    _sc.render.use_file_extension = False\n"
                "    if hasattr(_sc, 'eevee') and hasattr(_sc.eevee, 'taa_render_samples'):\n"
                "        _sc.eevee.taa_render_samples = min(24, getattr(_sc.eevee, 'taa_render_samples', 16) or 16)\n"
                "except Exception:\n"
                "    pass\n"
            )
            Path(script_save_path).write_text(code + shim, encoding="utf-8")
            return True
        except Exception as e:
            logger.warning(f"AI Blender script generation failed ({engine}): {e}")
            return False
