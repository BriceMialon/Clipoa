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
AGY_WINDOW_BUDGET_TOKENS = 1_500_000  # estimation 5h (un appel agy coute ~25k tokens d'entree)
AGY_WEEKLY_BUDGET_TOKENS = AGY_WINDOW_BUDGET_TOKENS * 6
AGY_QUOTA_STATE_FILE = STORAGE_DIR / "antigravity_quota_state.json"
AGY_LOG_DIRS = [
    Path.home() / ".gemini" / "antigravity",
    Path.home() / ".gemini" / "antigravity-cli",
]
_RESET_RE = re.compile(r"Resets? in\s+((?:\d+\s*[dhms]\s*)+)", re.I)
_GLOG_RE = re.compile(r"^[EWI](\d{2})(\d{2}) (\d{2}):(\d{2}):(\d{2})")


def parse_reset_seconds(text: str) -> Optional[int]:
    """'Resets in 2h44m31s' -> 9871 ; None si absent."""
    m = _RESET_RE.search(text or "")
    if not m:
        return None
    total = 0
    for val, unit in re.findall(r"(\d+)\s*([dhms])", m.group(1)):
        total += int(val) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit.lower()]
    return total


def is_quota_error(text: str) -> bool:
    low = (text or "").lower()
    return "resource_exhausted" in low or "quota reached" in low or "individual quota" in low


def _glog_ts(line: str, now: Optional[float] = None) -> Optional[float]:
    m = _GLOG_RE.match(line or "")
    if not m:
        return None
    now = now or time.time()
    lt = time.localtime(now)
    mo, day, hh, mi, ss = (int(x) for x in m.groups())
    for year in (lt.tm_year, lt.tm_year - 1):
        try:
            ts = time.mktime((year, mo, day, hh, mi, ss, 0, 0, -1))
        except (OverflowError, ValueError):
            continue
        if ts <= now + 60:
            return ts
    return None


def scan_quota_errors(lines, now: Optional[float] = None) -> Optional[float]:
    """Renvoie l'horodatage de reset le plus tardif trouve dans des lignes de log agy."""
    best = None
    for line in lines:
        if not is_quota_error(line):
            continue
        secs = parse_reset_seconds(line)
        ts = _glog_ts(line, now)
        if secs is None or ts is None:
            continue
        reset_at = ts + secs
        if best is None or reset_at > best:
            best = reset_at
    return best

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

        if connected:
            cls.probe_quota_async(force=live_probe)
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
    def _record_usage(cls, model: str, input_chars: int, output_chars: int, usage: Optional[Dict[str, Any]] = None) -> None:
        in_tok = max(1, int(round(input_chars / 3.8)))
        out_tok = max(1, int(round(output_chars / 3.8)))
        if usage:
            try:
                in_tok = int(usage.get("input_tokens") or in_tok)
                out_tok = int(usage.get("output_tokens") or 0) + int(usage.get("thinking_tokens") or 0) or out_tok
            except Exception:
                pass
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

    _log_scan_cache: Dict[str, Any] = {}

    @classmethod
    def _load_quota_state(cls) -> Dict[str, Any]:
        try:
            if AGY_QUOTA_STATE_FILE.exists():
                d = json.loads(AGY_QUOTA_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
        return {}

    @classmethod
    def _save_quota_state(cls, state: Dict[str, Any]) -> None:
        try:
            AGY_QUOTA_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            AGY_QUOTA_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except Exception:
            pass

    _probe_lock = threading.Lock()
    PROBE_EVERY_SEC = 15 * 60

    @classmethod
    def probe_quota(cls, force: bool = False) -> Dict[str, Any]:
        """
        Vérification RÉELLE du quota : Antigravity ne donne aucun % restant, et le quota est partagé avec
        l'app Antigravity (utilisée hors de Clipoa). On envoie donc une mini-requête (« ok ») au modèle choisi :
        « Individual quota reached. Resets in … » => 0 % jusqu'au reset ; réponse normale => quota disponible.
        Au plus une fois toutes les 15 min (sauf force=True), en arrière-plan.
        """
        st = cls._load_quota_state()
        now = time.time()
        if not force and now - float(st.get("probe_at") or 0) < cls.PROBE_EVERY_SEC:
            return {"skipped": True}
        cli = cls.find_cli()
        if not cli or not cls._probe_lock.acquire(blocking=False):
            return {"skipped": True}
        try:
            model = load_settings().get("antigravity", {}).get("model") or "gemini-4-neon-medium"
            sandbox = STORAGE_DIR / "_agy_sandbox"
            sandbox.mkdir(parents=True, exist_ok=True)
            try:
                res = subprocess.run([cli, "-p", "Réponds uniquement : ok", "--model", model, "--print-timeout", "60s"],
                                     capture_output=True, text=True, timeout=90, cwd=str(sandbox))
                out = (res.stdout or "") + "\n" + (res.stderr or "")
                code = res.returncode
            except Exception as e:
                out, code = str(e), -1
            st = cls._load_quota_state()
            st["probe_at"] = time.time()
            if is_quota_error(out):
                cls._save_quota_state(st)
                cls.note_quota_error(out)
                return {"ok": False, "exhausted": True}
            if code == 0 and out.strip():
                # Antigravity répond : le quota n'est pas épuisé (on efface un ancien blocage dépassé ou levé)
                st["exhausted_until"] = 0
                st["ignore_log_reset"] = cls._scan_logs_reset_at() or st.get("ignore_log_reset")
                st["probe_ok_at"] = time.time()
            cls._save_quota_state(st)
            return {"ok": code == 0, "exhausted": False}
        finally:
            cls._probe_lock.release()

    @classmethod
    def probe_quota_async(cls, force: bool = False) -> None:
        import sys
        if "unittest" in sys.modules or os.getenv("CLIPOA_NO_AGY_PROBE"):
            return  # jamais d'appel réel pendant les tests
        threading.Thread(target=cls.probe_quota, kwargs={"force": force}, daemon=True).start()

    @classmethod
    def note_quota_error(cls, text: str) -> None:
        """Memorise un 'Individual quota reached. Resets in …' renvoye par agy."""
        if not is_quota_error(text):
            return
        secs = parse_reset_seconds(text)
        now = time.time()
        reset_at = now + (secs if secs is not None else 3600)
        st = cls._load_quota_state()
        if reset_at > float(st.get("exhausted_until") or 0):
            st["exhausted_until"] = reset_at
            st["exhausted_seen_at"] = now
            cls._save_quota_state(st)

    @classmethod
    def _scan_logs_reset_at(cls) -> Optional[float]:
        """Lit la fin des logs d'Antigravity (app + CLI) : le quota est partage, meme hors Clipoa."""
        files: List[Path] = []
        for d in AGY_LOG_DIRS:
            if (d / "cli.log").exists():
                files.append(d / "cli.log")
            logs = sorted((d / "log").glob("cli-*.log")) if (d / "log").is_dir() else []
            files.extend(logs[-1:])
        best = None
        for f in files:
            try:
                stt = f.stat()
                key = str(f)
                cached = cls._log_scan_cache.get(key)
                if cached and cached[0] == stt.st_mtime and cached[1] == stt.st_size:
                    found = cached[2]
                else:
                    with open(f, "rb") as fh:
                        fh.seek(max(0, stt.st_size - 600_000))
                        chunk = fh.read().decode("utf-8", errors="ignore")
                    found = scan_quota_errors(chunk.splitlines())
                    cls._log_scan_cache[key] = (stt.st_mtime, stt.st_size, found)
                if found and (best is None or found > best):
                    best = found
            except Exception:
                continue
        return best

    @classmethod
    def set_manual_quota(cls, rem_5h: Optional[float], rem_7d: Optional[float]) -> Dict[str, Any]:
        """L'utilisateur recopie les % restants affiches par l'app Antigravity (calibrage)."""
        st = cls._load_quota_state()
        tok5, tok7 = cls._tokens_windows()
        man = st.get("manual") or {}
        now = time.time()
        if rem_5h is not None:
            man["rem_5h"] = max(0.0, min(100.0, float(rem_5h)))
            man["at_5h"] = now
            man["tok_at_5h"] = tok5
        if rem_7d is not None:
            man["rem_7d"] = max(0.0, min(100.0, float(rem_7d)))
            man["at_7d"] = now
            man["tok_at_7d"] = tok7
        st["manual"] = man
        if (rem_5h or 0) > 0 and float(st.get("exhausted_until") or 0) > now:
            st["exhausted_until"] = 0
            st["ignore_log_reset"] = cls._scan_logs_reset_at()
        cls._save_quota_state(st)
        return cls.get_quota_summary()

    @classmethod
    def _tokens_windows(cls):
        now = time.time()
        history: List[Dict[str, Any]] = []
        with _AGY_LOCK:
            if AGY_USAGE_FILE.exists():
                try:
                    history = json.loads(AGY_USAGE_FILE.read_text(encoding="utf-8"))
                    if not isinstance(history, list):
                        history = []
                except Exception:
                    history = []
        t5 = sum(int(h.get("total_tokens", 0)) for h in history if h.get("ts", 0) >= now - 5 * 3600)
        t7 = sum(int(h.get("total_tokens", 0)) for h in history if h.get("ts", 0) >= now - 7 * 86400)
        return t5, t7

    @classmethod
    def get_quota_summary(cls) -> Dict[str, Any]:
        """Pourcentages RESTANTS (5h et hebdo), comme l'app Antigravity.

        Sources, par ordre de fiabilite :
        1. erreur reelle « Individual quota reached. Resets in … » (Clipoa ou logs agy) -> 0 % jusqu'au reset
        2. calibrage manuel (% recopies depuis l'app Antigravity), decremente par la conso Clipoa
        3. estimation a partir des tokens consommes par Clipoa
        """
        now = time.time()
        st = cls._load_quota_state()
        t5, t7 = cls._tokens_windows()

        est_5h = max(0.0, 100.0 - (t5 / AGY_WINDOW_BUDGET_TOKENS) * 100.0)
        est_7d = max(0.0, 100.0 - (t7 / AGY_WEEKLY_BUDGET_TOKENS) * 100.0)
        source = "estimation"
        man = st.get("manual") or {}
        rem_5h, rem_7d = est_5h, est_7d
        if man.get("rem_7d") is not None and now - float(man.get("at_7d") or 0) < 7 * 86400:
            spent = max(0, t7 - int(man.get("tok_at_7d") or 0))
            rem_7d = max(0.0, float(man["rem_7d"]) - spent / AGY_WEEKLY_BUDGET_TOKENS * 100.0)
            source = "calibré"
        if man.get("rem_5h") is not None and now - float(man.get("at_5h") or 0) < 5 * 3600:
            spent = max(0, t5 - int(man.get("tok_at_5h") or 0))
            rem_5h = max(0.0, float(man["rem_5h"]) - spent / AGY_WINDOW_BUDGET_TOKENS * 100.0)
            source = "calibré"
        rem_5h = min(rem_5h, rem_7d)

        exhausted_until = float(st.get("exhausted_until") or 0)
        log_reset = cls._scan_logs_reset_at()
        ign = st.get("ignore_log_reset")
        if log_reset and not (ign and abs(float(ign) - log_reset) < 1):
            exhausted_until = max(exhausted_until, log_reset)
        exhausted = exhausted_until > now
        reset_in = int(exhausted_until - now) if exhausted else 0
        if exhausted:
            rem_5h = 0.0
            source = "réel"
            if reset_in > 5 * 3600:  # reset au-dela de 5h => c'est la limite hebdo qui bloque
                rem_7d = 0.0

        def _fmt(secs: int) -> str:
            d, r = divmod(secs, 86400)
            h, r = divmod(r, 3600)
            m = r // 60
            if d:
                return f"{d}j {h}h"
            return f"{h}h{m:02d}" if h else f"{m} min"

        rem_5h = round(rem_5h, 1)
        rem_7d = round(rem_7d, 1)
        tokens_left = int(AGY_WINDOW_BUDGET_TOKENS * rem_5h / 100.0)
        return {
            "calls_5h": cls._calls_5h(),
            "tokens_used_5h": t5,
            "tokens_left_5h": tokens_left,
            "budget_tokens_5h": AGY_WINDOW_BUDGET_TOKENS,
            "used_pct": round(100.0 - rem_5h, 1),
            "remaining_pct": rem_5h,
            "used_pct_7d": round(100.0 - rem_7d, 1),
            "remaining_pct_7d": rem_7d,
            "exhausted": exhausted,
            "resets_at": time.strftime("%H:%M", time.localtime(exhausted_until)) if exhausted else None,
            "resets_in": _fmt(reset_in) if exhausted else None,
            "source": source,
            "verified_at": time.strftime("%H:%M", time.localtime(float(st.get("probe_at") or 0))) if st.get("probe_at") else None,
            "est_videos_left": max(0, tokens_left // 60000),
        }

    @classmethod
    def _calls_5h(cls) -> int:
        try:
            history = json.loads(AGY_USAGE_FILE.read_text(encoding="utf-8")) if AGY_USAGE_FILE.exists() else []
            return len([h for h in history if h.get("ts", 0) >= time.time() - 5 * 3600])
        except Exception:
            return 0

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
        out_txt = "".join(cls.stream_query(prompt, system_prompt=system_prompt, model=model, timeout=timeout)).strip()
        if not out_txt:
            raise RuntimeError("Erreur Antigravity CLI : réponse vide")
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
        last_usage: Optional[Dict[str, Any]] = None
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
                    if isinstance(res_obj.get("usage"), dict):
                        last_usage = res_obj["usage"]
                    if not full_chunks and res_obj.get("response"):
                        resp_txt = str(res_obj["response"])
                        full_chunks.append(resp_txt)
                        yield resp_txt
            proc.wait(timeout=15)
            if proc.returncode != 0 and not full_chunks:
                err_full = proc.stderr.read() if proc.stderr else ""
                err_txt = err_full[:220]
                if is_quota_error(err_full):
                    cls.note_quota_error(err_full)
                    secs = parse_reset_seconds(err_full)
                    wait = (" Reset dans " + str(secs // 3600) + "h" + str((secs % 3600) // 60).zfill(2) + ".") if secs else ""
                    raise RuntimeError("Quota Antigravity épuisé (0 % restant)." + wait + " Choisis Claude ou attends le reset.")
                if "please sign in" in err_txt.lower() or "not logged in" in err_txt.lower():
                    cls._cached_connected = False
                    raise RuntimeError("Antigravity CLI n'est pas connecté.")
                raise RuntimeError(f"Erreur Antigravity CLI : {err_txt or 'code ' + str(proc.returncode)}")
            cls._cached_connected = True
            cls._record_usage(chosen_model, len(full_prompt), sum(len(c) for c in full_chunks), last_usage)
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
