import subprocess
import os
import json
import logging
import re
import threading
from typing import Optional, Dict, Any
from config import CLAUDE_CLI_PATH, ANTHROPIC_API_KEY, USE_CLAUDE_CLI
from core.settings_store import load_settings, record_claude_usage, get_claude_quota_summary, reset_claude_quota_counter, save_live_claude_quota

logger = logging.getLogger("ClaudeBridge")


class ClaudeQuotaExceededError(RuntimeError):
    """Raised when the active Claude account hits its 5h/rate limit so jobs can pause & resume cleanly."""
    pass


QUOTA_KEYWORDS = ("rate limit", "usage limit", "hit your limit", "quota", "429", "limit reached", "too many requests")


class ClaudeBridge:
    """
    Bridge allowing the app to communicate with Claude using either:
    1. Claude Code CLI (authenticated with Claude Pro/Max subscription, 0 extra API cost)
    2. Anthropic API Key (if provided)
    3. Autonomous local fallback so the app always remains testable

    Also tracks live 5h quota usage and supports 1-click Claude account switching from the UI.
    """

    _last_mode: str = "unknown"
    _cached_cli_auth: Optional[bool] = None
    _login_state: Dict[str, Any] = {"running": False, "url": "", "output": "", "done": False}

    @classmethod
    def check_status(cls, live_probe: bool = False) -> Dict[str, Any]:
        cli_exists = os.path.exists(CLAUDE_CLI_PATH)
        cli_version = ""
        cli_authenticated = False
        auth_email = ""
        message = ""

        if cli_exists:
            try:
                v_res = subprocess.run([CLAUDE_CLI_PATH, "--version"], capture_output=True, text=True, timeout=5)
                cli_version = v_res.stdout.strip()
            except Exception:
                cli_version = "inconnu"

            # Fast auth check via `claude auth status` (< 1s)
            if live_probe or cls._cached_cli_auth is None:
                try:
                    st_res = subprocess.run(
                        [CLAUDE_CLI_PATH, "auth", "status"],
                        capture_output=True,
                        text=True,
                        timeout=8,
                    )
                    m = re.search(r"\{[\s\S]*\}", st_res.stdout)
                    if m:
                        parsed = json.loads(m.group(0))
                        cli_authenticated = bool(parsed.get("loggedIn"))
                        auth_email = parsed.get("email") or parsed.get("accountEmail") or ""
                    else:
                        cli_authenticated = False
                except Exception:
                    cli_authenticated = False

                cls._cached_cli_auth = cli_authenticated
                if cli_authenticated:
                    message = f"Connecté à ton compte Claude Pro/Max{f' ({auth_email})' if auth_email else ''}"
                else:
                    message = "Claude Code non connecté — clique sur « Connecter un compte Claude »"
            else:
                cli_authenticated = bool(cls._cached_cli_auth)
                message = (
                    "Connecté à ton compte Claude Pro/Max"
                    if cli_authenticated
                    else "Claude Code non connecté — clique sur « Connecter un compte Claude »"
                )

        has_api_key = bool(ANTHROPIC_API_KEY)
        if USE_CLAUDE_CLI and cli_exists and cli_authenticated:
            mode = "claude_cli"
        elif has_api_key:
            mode = "anthropic_api"
            message = "Connecté via clé API Anthropic"
        else:
            mode = "fallback"
            if not message:
                message = "Mode démo autonome"

        return {
            "mode": mode,
            "connected": mode in ("claude_cli", "anthropic_api"),
            "model": load_settings().get("claude", {}).get("model", "opus"),
            "effort": load_settings().get("claude", {}).get("effort", "medium"),
            "cli_exists": cli_exists,
            "cli_path": CLAUDE_CLI_PATH,
            "cli_version": cli_version,
            "cli_authenticated": cli_authenticated,
            "email": auth_email,
            "has_api_key": has_api_key,
            "message": message,
            "quota": get_claude_quota_summary(),
            "login_flow": dict(cls._login_state),
        }

    @classmethod
    def logout_cli(cls) -> Dict[str, Any]:
        """Disconnects current Claude CLI account so user can switch to another Claude Pro/Max account."""
        if not os.path.exists(CLAUDE_CLI_PATH):
            return {"ok": False, "message": "Claude CLI introuvable"}
        subprocess.run([CLAUDE_CLI_PATH, "auth", "logout"], capture_output=True, text=True, timeout=15)
        cls._cached_cli_auth = False
        reset_claude_quota_counter()
        return {"ok": True, "message": "Compte Claude déconnecté et compteur de quota réinitialisé."}

    @classmethod
    def start_login_cli(cls) -> Dict[str, Any]:
        """
        Triggers `claude auth login` in the background (opens the Mac browser for OAuth)
        and captures any authorization URL printed to stdout/stderr.
        """
        if not os.path.exists(CLAUDE_CLI_PATH):
            return {"ok": False, "message": "Claude CLI introuvable"}

        cls._login_state = {"running": True, "url": "", "output": "Ouverture de la page de connexion Anthropic...", "done": False}

        def _worker():
            try:
                proc = subprocess.Popen(
                    [CLAUDE_CLI_PATH, "auth", "login"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                lines = []
                if proc.stdout:
                    for line in proc.stdout:
                        clean = line.strip()
                        if clean:
                            lines.append(clean)
                            url_m = re.search(r"https://[^\s]+", clean)
                            if url_m:
                                cls._login_state["url"] = url_m.group(0)
                            cls._login_state["output"] = "\n".join(lines[-5:])
                proc.wait(timeout=180)
                cls._login_state["running"] = False
                cls._login_state["done"] = True
                cls._cached_cli_auth = None
                reset_claude_quota_counter()
            except Exception as e:
                cls._login_state["running"] = False
                cls._login_state["output"] = f"Erreur login : {e}"

        threading.Thread(target=_worker, daemon=True).start()
        return {"ok": True, "message": "Connexion Claude lancée — valide dans ton navigateur !", "login_flow": cls._login_state}

    @classmethod
    def sync_real_quota(cls) -> Dict[str, Any]:
        """
        Queries Claude CLI with --output-format stream-json --verbose on Haiku (ultra-cheap)
        to capture the REAL server-side Anthropic 5h & 7d utilization (`rate_limit_event`).
        """
        if not os.path.exists(CLAUDE_CLI_PATH):
            return get_claude_quota_summary()
        try:
            res = subprocess.run(
                [CLAUDE_CLI_PATH, "-p", "OK", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--model", "haiku"],
                capture_output=True,
                text=True,
                timeout=25,
            )
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("type") == "rate_limit_event" and ev.get("rate_limit_info"):
                        save_live_claude_quota(ev["rate_limit_info"])
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"sync_real_quota error: {e}")
        return get_claude_quota_summary()

    @classmethod
    def query(
        cls,
        prompt: str,
        system_prompt: Optional[str] = None,
        action: str = "agent_query",
        model: Optional[str] = None,
    ) -> str:
        total_in = len(prompt) + len(system_prompt or "")

        # 1. Try Claude CLI first if enabled
        if USE_CLAUDE_CLI and os.path.exists(CLAUDE_CLI_PATH):
            try:
                c_cfg = load_settings().get("claude", {})
                chosen_model = (model or c_cfg.get("model", "opus")).strip().lower()
                if chosen_model not in ("opus", "sonnet", "haiku"):
                    chosen_model = c_cfg.get("model", "opus")
                chosen_effort = c_cfg.get("effort", "medium")
                cmd = [
                    CLAUDE_CLI_PATH, "-p", prompt,
                    "--output-format", "stream-json",
                    "--verbose",
                    "--no-session-persistence",
                    "--model", chosen_model,
                    "--effort", chosen_effort,
                ]
                if system_prompt:
                    cmd.extend(["--system-prompt", system_prompt])

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
                combined_err = (result.stderr + "\n" + result.stdout).strip()
                if result.returncode == 0 and result.stdout.strip() and "Not logged in" not in result.stdout:
                    cls._last_mode = "claude_cli"
                    cls._cached_cli_auth = True
                    out_txt = ""
                    real_cost = 0.0
                    in_tok = 0
                    out_tok = 0
                    cache_tok = 0
                    canon_model = chosen_model

                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if not line.startswith("{"):
                            continue
                        try:
                            ev = json.loads(line)
                            if ev.get("type") == "rate_limit_event" and ev.get("rate_limit_info"):
                                save_live_claude_quota(ev["rate_limit_info"])
                            elif ev.get("type") == "result" and "result" in ev:
                                out_txt = str(ev.get("result") or "").strip()
                                real_cost = float(ev.get("total_cost_usd") or 0.0)
                                u = ev.get("usage") or {}
                                in_tok = int(u.get("input_tokens") or 0)
                                out_tok = int(u.get("output_tokens") or 0)
                                cache_tok = int(u.get("cache_creation_input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
                                mu = ev.get("modelUsage") or {}
                                if mu:
                                    canon_model = next(iter(mu.keys()), chosen_model)
                        except Exception:
                            continue

                    if not out_txt:
                        out_txt = result.stdout.strip()

                    record_claude_usage(
                        total_in,
                        len(out_txt),
                        mode="claude_cli",
                        action=action,
                        cost_usd=real_cost,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cache_tokens=cache_tok,
                        canonical_model=canon_model,
                    )
                    return out_txt
                else:
                    low_err = combined_err.lower()
                    if any(k in low_err for k in QUOTA_KEYWORDS):
                        raise ClaudeQuotaExceededError(f"Quota Claude atteint : {combined_err[:180]}")
                    if "not logged in" in low_err or "please run /login" in low_err:
                        cls._cached_cli_auth = False
                        logger.warning("Claude CLI non connecté.")
                    else:
                        logger.warning(f"Claude CLI error: {combined_err[:200]}")
            except ClaudeQuotaExceededError:
                raise
            except Exception as e:
                logger.warning(f"Claude CLI execution failed: {e}")

        # 2. Try Anthropic API if key provided
        if ANTHROPIC_API_KEY:
            try:
                import requests
                headers = {
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload: Dict[str, Any] = {
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system_prompt:
                    payload["system"] = system_prompt

                res = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
                if res.status_code == 200:
                    data = res.json()
                    content = "".join([b.get("text", "") for b in data.get("content", [])])
                    cls._last_mode = "anthropic_api"
                    record_claude_usage(total_in, len(content), mode="anthropic_api", action=action)
                    return content
                else:
                    logger.error(f"Anthropic API error: {res.status_code} {res.text}")
            except Exception as e:
                logger.error(f"Anthropic API request failed: {e}")

        # 3. Graceful intelligent fallback
        cls._last_mode = "fallback"
        logger.warning("Mode démo autonome actif.")
        return cls._generate_fallback(prompt, system_prompt or "")

    @classmethod
    def _generate_fallback(cls, prompt: str, system_prompt: str = "") -> str:
        sys_head = system_prompt.strip().lower()[:140]
        p_low = prompt.lower()

        if "tu es le monteur" in sys_head or "moments viraux" in p_low:
            matches = re.findall(r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]", prompt)
            max_t = float(matches[-1][1]) if matches else 60.0
            clip_len = min(40.0, max(15.0, max_t / 3.0))
            clips = []
            for idx in range(3):
                start = round(idx * clip_len, 2)
                if start >= max_t - 5:
                    break
                end = round(min(max_t, start + clip_len), 2)
                clips.append({
                    "start_sec": start,
                    "end_sec": end,
                    "title": f"Extrait viral #{idx + 1}",
                    "hook_screen_text": f"LE SECRET #{idx + 1}",
                    "viral_score": round(9.1 - idx * 0.3, 1),
                    "reason": "Passage autonome à fort potentiel de rétention."
                })
            return json.dumps({"clips": clips}, ensure_ascii=False)

        if "tu es le stratège" in sys_head or "lundi au vendredi" in p_low:
            niche = "ta thématique"
            for line in prompt.splitlines():
                if "niche" in line.lower() or "thématique" in line.lower():
                    niche = line.split(":", 1)[-1].strip() or niche
                    break
            plan = {
                "semaine": [
                    {"jour": "Lundi", "angle": "Le choc", "titre": f"L'erreur n°1 en {niche} que 90% font encore", "promesse": "Éviter le piège le plus coûteux"},
                    {"jour": "Mardi", "angle": "Histoire", "titre": f"Comment un déclic en {niche} a tout changé en 30 jours", "promesse": "Preuve concrète et émotion"},
                    {"jour": "Mercredi", "angle": "Guide pratique", "titre": f"La méthode en 3 étapes pour maîtriser {niche}", "promesse": "Plan actionnable à sauvegarder"},
                    {"jour": "Jeudi", "angle": "Mythe démonté", "titre": f"Non, tu n'as pas besoin de ça pour réussir en {niche}", "promesse": "Créer le débat en commentaires"},
                    {"jour": "Vendredi", "angle": "Vision", "titre": f"Ce qui va exploser en {niche} dans les 6 prochains mois", "promesse": "Prendre de l'avance sur la tendance"},
                ]
            }
            return json.dumps(plan, ensure_ascii=False)

        if "tu es le contrôle" in sys_head or "évalue ce script" in p_low:
            return json.dumps({
                "score_global": "9.0/10",
                "decision": "VALIDE",
                "points_forts": ["Accroche directe avec arrêt du scroll", "Rythme oral court et percutant"],
                "points_faibles": ["Vérifier le rythme sur les 3 premières secondes"]
            }, ensure_ascii=False)

        if "tu es le cloneur" in sys_head or "recette de ce short" in p_low:
            return json.dumps({
                "hook_formula": "Arrête tout : [ERREUR_COMMUNE] te coûte [CONSÉQUENCE]",
                "narrative_arc": ["Choc initial (0-3s)", "Révélation du piège (3-18s)", "Solution en 1 règle (18-40s)", "Appel à l'action (40-50s)"],
                "visual_cues": ["Texte hook centré", "Sous-titres mot-par-mot contrastés", "Rythme rapide"],
                "ending_technique": "Question ouverte pour déclencher les commentaires",
                "reusable_template": "Hook choc -> Constat -> Règle clé -> CTA commentaire"
            }, ensure_ascii=False)

        sujet = "ce sujet"
        for line in prompt.splitlines():
            if "sujet" in line.lower() or "topic" in line.lower():
                sujet = line.split(":", 1)[-1].strip() or sujet
                break

        return json.dumps({
            "title": f"Le secret derrière {sujet[:42]}",
            "hook_spoken": f"Tu ne vas pas croire ce qui se cache vraiment derrière {sujet[:40]}.",
            "hook_screen_text": "LE VRAI SECRET...",
            "full_spoken_script": (
                f"Presque tout le monde passe à côté de ce détail sur {sujet}. "
                "En surface, tout semble normal, mais un mécanisme caché change complètement la donne. "
                "Dès que tu comprends cette règle simple, tu ne regardes plus jamais le sujet de la même façon. "
                "Garde cette vidéo sous la main et abonne-toi pour ne pas rater le prochain épisode."
            ),
            "social_caption": f"Ce que presque personne ne remarque sur {sujet} #shorts #storytelling #createur #video"
        }, ensure_ascii=False)
