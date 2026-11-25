import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STORAGE_DIR
from core.settings_store import load_settings, save_settings

logger = logging.getLogger("AntigravityBridge")

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
            "message": message,
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

        full_prompt = f"{system_prompt.strip()}\n\n{prompt.strip()}" if system_prompt else prompt.strip()
        chosen_model = (model or load_settings().get("antigravity", {}).get("model") or "").strip()

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

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        combined = (res.stdout + "\n" + res.stderr).strip()
        low = combined.lower()
        if "please sign in" in low or "not logged in" in low:
            cls._cached_connected = False
            raise RuntimeError("Antigravity CLI n'est pas connecté. Ouvre Connexions → Connecter Antigravity.")
        if res.returncode != 0 or not res.stdout.strip():
            raise RuntimeError(f"Erreur Antigravity CLI : {combined[:220]}")

        cls._cached_connected = True
        return res.stdout.strip()

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
        frames: int = 150,
        engine: str = "antigravity",
        model: Optional[str] = None,
    ) -> bool:
        """
        Demande à Antigravity (ou Claude / Gemini) d'écrire un vrai script Python Blender (`bpy`)
        adapté au sujet et à la Direction Artistique choisie (ex. 3D Roblox, 2D×3D, Fête en folie).
        Retourne True si un script valide a été écrit, False sinon (le pipeline utilise alors le fallback).
        """
        sys_prompt = (
            "Tu es un artiste technique Blender 3D expert (bpy Python API, Blender 4.x).\n"
            "Écris UNIQUEMENT un script Python complet et autonome (sans texte autour, dans un bloc ```python```) "
            "qui construit une scène 3D verticale 9:16 animée correspondant au sujet et à la Direction Artistique.\n"
            "Contraintes STRICTES :\n"
            "1. Commence par `import bpy`, `import math` (et `import random` si utile). Aucun import réseau/système (`os`, `subprocess`, `socket`, `requests`).\n"
            "2. Réinitialise la scène avec `bpy.ops.wm.read_factory_settings(use_empty=True)`.\n"
            f"3. Configure le rendu vertical 9:16 H.264 MP4 : resolution_x=1080, resolution_y=1920, resolution_percentage=100, fps=30, frame_start=1, frame_end={int(frames)}, "
            "image_settings.file_format='FFMPEG', ffmpeg.format='MPEG4', ffmpeg.codec='H264', use_file_extension=False, engine='BLENDER_EEVEE_NEXT' (ou fallback 'BLENDER_EEVEE').\n"
            "4. Crée une vraie scène 3D visuelle riche (personnages/objets géométriques stylisés, décor coloré, éclairage soigné, caméra en mouvement fluide avec keyframes de frame 1 à frame_end).\n"
            "5. N'utilise aucun fichier externe (textures/HDRI/meshes externes interdits) : tout doit être procédural en `bpy`."
        )
        da_snippet = (da_context or "")[:2400]
        da_block = f"Direction Artistique à respecter :\n{da_snippet}\n" if da_snippet else ""
        user_prompt = (
            f"Sujet : {topic}\n"
            f"Script parlé (extrait) : {(spoken_script or '')[:600]}\n"
            f"{da_block}"
            f"Durée : {int(frames)} frames à 30 fps.\n"
            "Retourne uniquement le script Python Blender complet."
        )

        try:
            eng = (engine or "antigravity").lower()
            if eng == "antigravity":
                raw = cls.query(user_prompt, system_prompt=sys_prompt, model=model, timeout=150)
            elif eng == "gemini":
                from core.gemini_studio import GeminiStudio
                raw = GeminiStudio.chat_text(user_prompt, system_prompt=sys_prompt, model=model)
            else:
                from core.claude_bridge import ClaudeBridge
                raw = ClaudeBridge.query(user_prompt, system_prompt=sys_prompt, action="blender_3d", model=model)

            code = cls.extract_python_code(raw)
            if not cls.validate_blender_script(code):
                return False

            # Safe EEVEE engine compatibility shim (Blender 4.2+ uses BLENDER_EEVEE_NEXT, 3.x/4.0 uses BLENDER_EEVEE)
            shim = (
                "\n# Clipoa EEVEE compatibility guard\n"
                "try:\n"
                "    import bpy as _cbpy\n"
                "    _cbpy.context.scene.render.image_settings.file_format = 'FFMPEG'\n"
                "    _cbpy.context.scene.render.ffmpeg.format = 'MPEG4'\n"
                "    _cbpy.context.scene.render.ffmpeg.codec = 'H264'\n"
                "    _cbpy.context.scene.render.use_file_extension = False\n"
                "except Exception:\n"
                "    pass\n"
            )
            Path(script_save_path).write_text(code + shim, encoding="utf-8")
            return True
        except Exception as e:
            logger.warning(f"AI Blender script generation failed ({engine}): {e}")
            return False
