"""
Voix HD gratuite et locale (Qwen3-TTS, licence Apache 2.0) pour Clipoa.

Pensée pour tout utilisateur : un clic sur « Installer la voix HD » dans la Fabrique crée un Python isolé
(`venv_tts`, Python 3.11 fourni par `uv`, aucune installation système), installe Qwen3-TTS puis télécharge
le modèle. Ensuite la voix HD devient la voix gratuite par défaut ; Edge-TTS reste le secours automatique.
Le worker tourne dans son propre processus : un plantage ou un manque de mémoire ne fait jamais tomber Clipoa.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import BASE_DIR, STORAGE_DIR

TTS_VENV = Path(os.environ.get("CLIPOA_TTS_VENV", str(BASE_DIR / "venv_tts")))
TTS_PY = TTS_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
WORKER = BASE_DIR / "core" / "tts_worker" / "qwen_worker.py"
STATE_FILE = STORAGE_DIR / "local_tts_state.json"
INSTALL_LOG = STORAGE_DIR / "tts_install.log"
_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None  # une installation ne survit pas à un redémarrage du serveur

# Voix prêtes à l'emploi (le modèle parle français avec chacune ; « instruct » règle le ton)
LOCAL_VOICES: List[Dict[str, str]] = [
    {"id": "qwen:Ryan", "label": "Ryan · Voix HD masculine rythmée (gratuite)"},
    {"id": "qwen:Aiden", "label": "Aiden · Voix HD masculine claire (gratuite)"},
    {"id": "qwen:Uncle_Fu", "label": "Fu · Voix HD grave et posée (gratuite)"},
    {"id": "qwen:Serena", "label": "Serena · Voix HD féminine douce (gratuite)"},
    {"id": "qwen:Vivian", "label": "Vivian · Voix HD féminine vive (gratuite)"},
    {"id": "qwen:Sohee", "label": "Sohee · Voix HD féminine émue (gratuite)"},
]
DEFAULT_LOCAL_VOICE = "qwen:Ryan"


def _load_state() -> Dict[str, Any]:
    try:
        if STATE_FILE.exists():
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _save_state(**kw) -> None:
    with _LOCK:
        st = _load_state()
        st.update(kw)
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(st, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def use_by_default() -> bool:
    """La voix HD remplace la voix gratuite en mode Auto seulement si l'utilisateur l'a demandé (elle est plus lente)."""
    return is_ready() and bool(_load_state().get("auto_default"))


def set_auto_default(on: bool) -> Dict[str, Any]:
    _save_state(auto_default=bool(on))
    return status()


def is_ready() -> bool:
    return TTS_PY.exists() and bool(_load_state().get("ready"))


def status() -> Dict[str, Any]:
    st = _load_state()
    tail = ""
    try:
        if INSTALL_LOG.exists():
            tail = INSTALL_LOG.read_text(encoding="utf-8", errors="ignore")[-400:]
    except Exception:
        pass
    return {
        "ready": is_ready(),
        "installing": bool((st.get("installing") and _THREAD is not None and _THREAD.is_alive())),
        "step": st.get("step", ""),
        "error": st.get("error", ""),
        "voices": LOCAL_VOICES,
        "default_voice": st.get("default_voice") or DEFAULT_LOCAL_VOICE,
        "auto_default": bool(st.get("auto_default")),
        "speed_note": "plus long",
        "log_tail": tail if (st.get("installing") and _THREAD is not None and _THREAD.is_alive()) or st.get("error") else "",
    }


def _run(cmd: List[str], log) -> int:
    log.write("\n$ " + " ".join(cmd) + "\n")
    log.flush()
    return subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(BASE_DIR))


def _install_worker() -> None:
    try:
        with open(INSTALL_LOG, "w", encoding="utf-8") as log:
            steps = [
                ("Préparation de l'installateur…", [sys.executable, "-m", "pip", "install", "-q", "uv"]),
                ("Création d'un Python isolé (3.11)…", [sys.executable, "-m", "uv", "venv", "--allow-existing", "--python", "3.11", str(TTS_VENV)]),
                ("Installation du moteur de voix (≈ 2 Go)…", [sys.executable, "-m", "uv", "pip", "install", "--python", str(TTS_PY), "qwen-tts", "soundfile", "numpy"]),
                ("Téléchargement du modèle de voix (≈ 2 Go)…", [str(TTS_PY), str(WORKER), "--warmup"]),
            ]
            for label, cmd in steps:
                _save_state(installing=True, step=label, error="")
                if _run(cmd, log) != 0:
                    raise RuntimeError(label.rstrip("…") + " a échoué (détails dans storage/tts_install.log)")
        _save_state(installing=False, ready=True, step="Voix HD prête", error="", installed_at=time.time())
    except Exception as e:
        _save_state(installing=False, ready=False, error=str(e)[:300], step="")


def start_install() -> Dict[str, Any]:
    global _THREAD
    st = _load_state()
    if (st.get("installing") and _THREAD is not None and _THREAD.is_alive()):
        return status()
    _save_state(installing=True, step="Démarrage…", error="")
    _THREAD = threading.Thread(target=_install_worker, daemon=True)
    _THREAD.start()
    return status()


def set_default_voice(voice_id: str) -> Dict[str, Any]:
    if any(v["id"] == voice_id for v in LOCAL_VOICES):
        _save_state(default_voice=voice_id)
    return status()


def tone_for_text(text: str) -> str:
    low = (text or "").lower()
    if any(w in low for w in ("peur", "nuit", "mort", "sombre", "secret", "disparu", "silence", "jamais")):
        return "Parle en français, voix posée et intime de conteur, un peu mystérieuse, avec des pauses naturelles."
    if any(w in low for w in ("argent", "million", "incroyable", "erreur", "vérité", "choquant")):
        return "Parle en français, ton énergique et accrocheur de créateur TikTok, rythme soutenu."
    return "Parle en français, ton naturel et expressif de créateur vidéo, rythme fluide."


def synthesize(text: str, out_wav: Path, voice: Optional[str] = None, instruct: Optional[str] = None,
               ref_audio: Optional[str] = None, ref_text: Optional[str] = None) -> Dict[str, Any]:
    """Génère `out_wav`. Lève une exception si la voix HD n'est pas prête ou échoue (l'appelant bascule sur Edge)."""
    if not is_ready():
        raise RuntimeError("Voix HD non installée")
    speaker = (voice or status()["default_voice"]).split(":", 1)[-1]
    job = {
        "text": text, "out": str(out_wav), "speaker": speaker, "language": "French",
        "instruct": instruct if instruct is not None else tone_for_text(text),
        "ref_audio": ref_audio, "ref_text": ref_text,
    }
    fd, job_path = tempfile.mkstemp(prefix="tts_job_", suffix=".json", dir=str(STORAGE_DIR))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False)
    try:
        # pas de délai fixe global : ~1 min de calcul par 30 s de voix sur un Mac M1 ; garde-fou large
        timeout = max(600, int(len(text) * 1.5))
        res = subprocess.run([str(TTS_PY), str(WORKER), job_path], capture_output=True, text=True, timeout=timeout,
                             cwd=str(BASE_DIR))
        if res.returncode != 0 or not Path(out_wav).exists():
            raise RuntimeError("Voix HD : " + (res.stderr or res.stdout or "échec")[-300:])
        last = [ln for ln in res.stdout.splitlines() if ln.startswith("{")]
        return json.loads(last[-1]) if last else {"ok": True}
    finally:
        try:
            os.unlink(job_path)
        except OSError:
            pass
