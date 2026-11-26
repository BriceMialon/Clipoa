# -*- coding: utf-8 -*-
"""
Équipe d'agents IA ClipRoll (Orchestrateur inspiré du protocole J.A.R.V.I.S. @profpicsou + @jeffar_ai).

5 spécialistes coordonnés par l'Orchestrateur depuis la barre IA en haut de ClipRoll :
  - Orchestrateur : comprend la demande, choisit le plan d'action et coordonne les agents.
  - Stratège Rétention : audite la chaîne active (12 derniers Shorts), détecte les 3 fuites de rétention, conçoit les hooks 1.5s.
  - Scénariste : structure et élague les scripts 9:16 (hook 1.5s, <8 mots/phrase, boucle >100 %).
  - Producteur : exécute réellement les actions dans ClipRoll (planifier & lancer la semaine de 5 vidéos, fabriquer 1 vidéo, refaire la pire vidéo, synchroniser les stats).
  - Vérificateur (Avocat du diable) : contrôle les risques et garantit la règle d'or — aucune publication ni suppression sans validation humaine.
"""
import re
from typing import Any, Dict, List, Optional


TEAM_ROSTER = [
    {"id": "orchestrateur", "name": "Orchestrateur", "role": "Découpe la mission et coordonne l'équipe"},
    {"id": "stratege", "name": "Stratège Rétention", "role": "Audit chaîne (12 Shorts) & hooks 1.5s"},
    {"id": "scenariste", "name": "Scénariste", "role": "Scripts 9:16, élagage & boucle >100 %"},
    {"id": "producteur", "name": "Producteur", "role": "Lance la semaine (5 vidéos) et les fabrications"},
    {"id": "verificateur", "name": "Vérificateur", "role": "Avocat du diable · zéro publication sans accord"},
]


def _classify_mission(message: str) -> Dict[str, Any]:
    """
    Détecte l'intention actionnable (rapide par règles sûres, puis fallback LLM JSON si ambigu).
    """
    low = (message or "").lower().strip()

    # Guardrail strict : jamais publier / supprimer sans validation humaine
    if any(k in low for k in ("publie automatiquement", "publie tout", "supprime toutes", "efface mes vidéos")):
        return {"action": "blocked_safety", "params": {}}

    # 1. Générer / planifier la semaine (5 vidéos)
    if re.search(r"\b(semaine|5\s*vid[ée]os|5\s*shorts|batch|planning\s*de\s*la\s*semaine)\b", low):
        niche = re.sub(
            r"(?i)^(g[ée]n[èe]re|cr[ée]e|fais|pr[ée]pare|lance|planifie)\s+(moi\s+)?(mes\s+|les\s+|une\s+|ma\s+)?"
            r"(5\s*)?(vid[ée]os?|shorts?)?\s*(pour\s+la\s+|de\s+la\s+)?semaine\s*(sur|de|autour\s+de|:|-)?\s*",
            "",
            message.strip(),
        ).strip(" .!?")
        auto_enqueue = any(k in low for k in ("génère", "genere", "fabrique", "lance", "fais", "crée", "cree"))
        return {"action": "generate_week", "params": {"niche": niche, "auto_enqueue": auto_enqueue}}

    # 2. Auditer la chaîne (12 derniers Shorts)
    if re.search(r"\b(audit|audite|analyse\s+ma\s+cha[îi]ne|fuites?\s+de\s+r[ée]tention|12\s*shorts|bilan\s+de\s+ma\s+cha[îi]ne)\b", low):
        return {"action": "audit_channel", "params": {}}

    # 3. Synchroniser / mettre à jour les statistiques
    if re.search(r"\b(mets?\s+[àa]\s+jour\s+.*stats|sync.*stats|actualise\s+.*statistiques)\b", low):
        return {"action": "sync_stats", "params": {}}

    # 4. Refaire la pire vidéo / vidéo à améliorer
    if re.search(r"\b(refais|am[ée]liore)\s+(ma\s+|la\s+)?(pire|moins\s+bonne|derni[èe]re)\s+vid[ée]o\b", low):
        return {"action": "remake_worst", "params": {}}

    # 5. Hooks 1.5s
    if re.search(r"\b(hooks?|accroches?)\b", low):
        topic = re.sub(r"(?i)^.*?\b(hooks?|accroches?)\s*(1[.,]5\s*s)?\s*(sur|pour|:|-)?\s*", "", message.strip()).strip(" .!?")
        return {"action": "hooks_1_5s", "params": {"topic": topic or message.strip()}}

    # 6. Fabriquer une vidéo unique
    if re.search(r"^(fabrique|cr[ée]e|g[ée]n[èe]re|lance|fais)\s+(moi\s+)?(une\s+|un\s+)?(vid[ée]o|short)\b", low):
        topic = re.sub(
            r"(?i)^(fabrique|cr[ée]e|g[ée]n[èe]re|lance|fais)\s+(moi\s+)?(une\s+|un\s+)?(vid[ée]o|short)\s*(sur|de|à\s+propos\s+de|:|-)?\s*",
            "",
            message.strip(),
        ).strip(" .!?")
        return {"action": "make_video", "params": {"topic": topic or message.strip()}}

    return {"action": "advise", "params": {}}


def _infer_channel_niche() -> str:
    """Déduit automatiquement la niche de la chaîne active depuis ses vidéos récentes."""
    try:
        from core import channel_stats, workspace
        data = channel_stats.load()
        titles = [v.get("title", "") for v in (data.get("videos") or [])[:5] if v.get("title")]
        ch_name = ((data.get("channel") or {}).get("name") or (workspace.current() or {}).get("name") or "").strip()
        if titles:
            return f"Chaîne « {ch_name} » — dans le style de : " + " | ".join(titles[:3])
        if ch_name:
            return ch_name
    except Exception:
        pass
    return "histoires courtes captivantes 9:16"


def run_mission(
    message: str,
    engine: str = "claude",
    plugin_id: str = "",
    duration_sec: int = 60,
    voice: Optional[str] = None,
    enqueue_week_fn=None,
    make_video_fn=None,
    remake_video_fn=None,
    confirmed: bool = False,
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Exécute une mission complète via l'équipe d'agents IA ClipRoll et retourne :
    - reply : synthèse concise en français
    - steps : trace des agents mobilisés [{agent, status, detail}]
    - actions : boutons rapides côté UI [{label, view, ...}]
    - data : données structurées éventuelles (plan semaine, audit, hooks…)

    Règle : aucune fabrication n'est lancée sans `confirmed=True`. Sans confirmation, la mission
    renvoie `needs_confirmation` avec un bouton « confirm » que l'interface renvoie tel quel.
    """
    mission = _classify_mission(message)
    action = mission["action"]
    params = mission["params"]
    steps: List[Dict[str, str]] = []
    actions: List[Dict[str, Any]] = []

    if action == "blocked_safety":
        steps = [
            {"agent": "Orchestrateur", "status": "done", "detail": "Demande d'action irréversible détectée."},
            {"agent": "Vérificateur", "status": "blocked", "detail": "Règle de sécurité : aucune publication ni suppression sans ta validation explicite."},
        ]
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": (
                "Par sécurité, l'équipe d'agents ne publie ni ne supprime jamais de vidéo à ta place sans ton accord. "
                "Je peux en revanche préparer toute ta semaine de vidéos dans « Mes vidéos » pour que tu les valides en 1 clic."
            ),
            "actions": [{"label": "Ouvrir Mes vidéos", "view": "videos"}, {"label": "Ouvrir Publier", "view": "auto"}],
        }

    if action == "generate_week":
        from agents.team import LeStratege
        given = [str(t).strip()[:200] for t in (topics or []) if str(t).strip()][:5]
        if confirmed and given:
            # Confirmation de l'utilisateur : on reprend exactement les sujets qu'il a vus.
            plan, topics = [], given
            steps.append({"agent": "Orchestrateur", "status": "done", "detail": "Lancement confirmé par toi."})
        else:
            niche = params.get("niche") or _infer_channel_niche()
            steps.append({"agent": "Orchestrateur", "status": "done", "detail": f"Mission semaine reçue (niche : {niche[:80]})."})
            plan = LeStratege.plan_weekly_shorts(niche, engine=engine) or []
            topics = [str(it.get("titre") or it.get("sujet") or it.get("title") or "").strip() for it in plan if isinstance(it, dict)]
            topics = [t for t in topics if t][:5]
            steps.append({"agent": "Stratège Rétention", "status": "done", "detail": f"{len(topics)} sujets calibrés (Lun → Ven) générés."})

        created = 0
        if topics and params.get("auto_enqueue") and not confirmed:
            steps.append({"agent": "Vérificateur", "status": "blocked", "detail": "Confirmation requise avant de lancer les fabrications."})
            bullet = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
            return {
                "ok": True, "action": "needs_confirmation", "mission": "generate_week", "steps": steps,
                "reply": f"Voici les {len(topics)} sujets proposés pour ta semaine :\n{bullet}\n\nJe lance les {len(topics)} fabrications ?",
                "actions": [{"label": f"Lancer ces {len(topics)} fabrications", "confirm": True, "message": message, "topics": topics},
                            {"label": "Ouvrir Ma semaine", "open_modal": "modal-week"}],
                "data": {"plan": plan, "topics": topics, "created": 0},
            }
        if topics and params.get("auto_enqueue") and callable(enqueue_week_fn):
            created = int(enqueue_week_fn(topics, plugin_id=plugin_id, duration_sec=duration_sec, engine=engine, voice=voice) or 0)
            steps.append({"agent": "Producteur", "status": "done", "detail": f"{created} vidéos mises en file de fabrication automatique."})
            steps.append({"agent": "Vérificateur", "status": "done", "detail": "Elles arriveront dans « Mes vidéos » pour validation avant toute publication."})
            bullet = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
            reply = (
                f"Ta semaine de {created} vidéos est lancée en fabrication automatique :\n{bullet}\n\n"
                "Tu les retrouveras prêtes à valider dans « Mes vidéos » (rien ne sera publié sans ton accord)."
            )
            actions = [{"label": "Voir Mes vidéos", "view": "videos"}]
        else:
            steps.append({"agent": "Producteur", "status": "ready", "detail": "Sujets prêts à lancer dans la file de fabrication."})
            bullet = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
            reply = f"Voici les {len(topics)} sujets préparés pour ta semaine :\n{bullet}"
            actions = [{"label": "Ouvrir Ma semaine", "open_modal": "modal-week"}]

        return {"ok": True, "action": action, "steps": steps, "reply": reply, "actions": actions, "data": {"plan": plan, "created": created}}

    if action == "audit_channel":
        from core import channel_stats, retention_audit
        steps.append({"agent": "Orchestrateur", "status": "done", "detail": "Audit complet des 12 derniers Shorts demandé."})
        stats = channel_stats.load()
        if not (stats.get("videos") or []):
            steps.append({"agent": "Stratège Rétention", "status": "warn", "detail": "Aucune vidéo en cache pour le compte actif."})
            return {
                "ok": True,
                "action": action,
                "steps": steps,
                "reply": "Je n'ai pas encore les vidéos du compte actif en cache. Clique sur « Mettre à jour » dans Statistiques puis relance l'audit.",
                "actions": [{"label": "Ouvrir Statistiques", "view": "perf"}],
            }
        audit = retention_audit.audit_channel(stats)
        sc = audit.get("scorecard") or {}
        leaks = audit.get("retention_leaks") or []
        steps.append({"agent": "Stratège Rétention", "status": "done", "detail": f"Score global {sc.get('overall', '-')}/100 · {len(leaks)} fuites identifiées."})
        steps.append({"agent": "Vérificateur", "status": "done", "detail": "Plan de réparation priorisé prêt dans Statistiques."})
        leak_txt = "\n".join(f"• {l.get('title', '')} : {l.get('fix', '')}" for l in leaks[:3])
        reply = (
            f"Audit de « {audit.get('channel_name', 'ta chaîne')} » ({audit.get('videos_analyzed', 0)} Shorts) — "
            f"Score global : {sc.get('overall', '-')}/100.\n\n"
            f"3 fuites de rétention prioritaires :\n{leak_txt}\n\n"
            f"Nouvelle formule d'accroche 1.5s : {audit.get('hook_formula', '')}"
        )
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": reply,
            "actions": [{"label": "Voir l'audit dans Statistiques", "view": "perf"}],
            "data": {"audit": audit},
        }

    if action == "sync_stats":
        from core import channel_stats
        started = channel_stats.start_sync()
        steps = [
            {"agent": "Orchestrateur", "status": "done", "detail": "Synchronisation des statistiques du compte actif lancée."},
            {"agent": "Producteur", "status": "done", "detail": "Sync démarrée en arrière-plan." if started else "Une synchronisation est déjà en cours."},
        ]
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": "Mise à jour des statistiques du compte actif lancée. Ouvre l'onglet « Statistiques » pour suivre les résultats.",
            "actions": [{"label": "Ouvrir Statistiques", "view": "perf"}],
        }

    if action == "remake_worst":
        from core import channel_stats
        stats = channel_stats.load()
        vids = sorted(stats.get("videos") or [], key=lambda v: v.get("score", 100))
        if not vids:
            return {
                "ok": True,
                "action": action,
                "steps": [{"agent": "Stratège Rétention", "status": "warn", "detail": "Aucune statistique chargée pour ce compte."}],
                "reply": "Aucune vidéo analysée sur ce compte. Va dans « Statistiques » et clique sur « Mettre à jour » d'abord.",
                "actions": [{"label": "Ouvrir Statistiques", "view": "perf"}],
            }
        worst = vids[0]
        steps.append({"agent": "Stratège Rétention", "status": "done", "detail": f"Vidéo ciblée : « {worst.get('title', '')[:50]} » ({worst.get('score', 0)}/100)."})
        if not confirmed:
            steps.append({"agent": "Vérificateur", "status": "blocked", "detail": "Confirmation requise avant de lancer la fabrication."})
            return {
                "ok": True, "action": "needs_confirmation", "mission": "remake_worst", "steps": steps,
                "reply": f"Ta vidéo la moins performante est « {worst.get('title', '')} » ({worst.get('score', 0)}/100). Je lance sa nouvelle version ?",
                "actions": [{"label": "Refaire cette vidéo", "confirm": True, "message": message}],
            }
        if callable(remake_video_fn):
            remake_video_fn(worst["id"], engine=engine, voice=voice)
            steps.append({"agent": "Producteur", "status": "done", "detail": "Nouvelle version optimisée (hook 1.5s + boucle) mise en fabrication."})
            steps.append({"agent": "Vérificateur", "status": "done", "detail": "Prête à valider dans « Mes vidéos » une fois calculée."})
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": (
                f"L'équipe refait ta vidéo « {worst.get('title', '')} » ({worst.get('score', 0)}/100) "
                "avec un hook 1.5s Evidence + Betrayal, un rythme resserré et une boucle finale."
            ),
            "actions": [{"label": "Suivre dans Mes vidéos", "view": "videos"}],
        }

    if action == "hooks_1_5s":
        from core import retention_audit
        topic = params.get("topic") or "mon sujet"
        res = retention_audit.generate_hooks_1_5s(topic)
        hooks = res.get("hooks") or []
        steps = [
            {"agent": "Orchestrateur", "status": "done", "detail": f"Brief accroches 1.5s sur « {topic[:60]} »."},
            {"agent": "Scénariste", "status": "done", "detail": f"{len(hooks)} hooks Evidence + Betrayal rédigés."},
        ]
        lines = "\n".join(
            f"{i + 1}. [{h.get('caption_4w', '')}] « {h.get('spoken_7w', '')} » — Visuel frame 1 : {h.get('frame1_proof', '')}"
            for i, h in enumerate(hooks[:5])
        )
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": f"5 options de hooks 1.5s (Evidence + Betrayal) :\n{lines}",
            "actions": [{"label": "Ouvrir Créer", "view": "creer"}],
            "data": res,
        }

    if action == "make_video":
        topic = params.get("topic") or message.strip()
        if not confirmed:
            return {
                "ok": True, "action": "needs_confirmation", "mission": "make_video",
                "steps": [{"agent": "Orchestrateur", "status": "done", "detail": f"Vidéo demandée : « {topic[:60]} »."},
                          {"agent": "Vérificateur", "status": "blocked", "detail": "Confirmation requise avant de lancer la fabrication."}],
                "reply": f"Je lance la fabrication de la vidéo « {topic} » ?",
                "actions": [{"label": "Lancer la fabrication", "confirm": True, "message": message}],
            }
        steps.append({"agent": "Orchestrateur", "status": "done", "detail": f"Fabrication lancée pour « {topic[:60]} »."})
        if callable(make_video_fn):
            make_video_fn(topic=topic, plugin_id=plugin_id, duration_sec=duration_sec, engine=engine, voice=voice)
            steps.append({"agent": "Producteur", "status": "done", "detail": "Vidéo envoyée dans la Fabrique 9:16."})
            steps.append({"agent": "Vérificateur", "status": "done", "detail": "Validation humaine requise avant publication."})
        return {
            "ok": True,
            "action": action,
            "steps": steps,
            "reply": f"C'est parti ! La vidéo « {topic} » est en cours de fabrication. Tu pourras la valider dans « Mes vidéos ».",
            "actions": [{"label": "Voir Mes vidéos", "view": "videos"}],
        }

    # Fallback : conseil stratégique court multi-agents
    from core.inspiration_radar import _default_ai_query
    sys_p = (
        "Tu es l'Orchestrateur de l'équipe d'agents IA ClipRoll (Stratège Rétention, Scénariste, Producteur, Vérificateur). "
        "Réponds en français en 4 à 6 lignes concrètes. Rappelle si pertinent que l'utilisateur peut demander directement : "
        "« Génère ma semaine de 5 vidéos sur [sujet] », « Audite ma chaîne », « Refais ma pire vidéo » ou « Crée une vidéo sur [sujet] »."
    )
    reply = _default_ai_query(message, sys_p) or "Dis-moi quelle mission lancer : générer ta semaine (5 vidéos), auditer ta chaîne ou créer une vidéo."
    return {
        "ok": True,
        "action": "advise",
        "steps": [
            {"agent": "Orchestrateur", "status": "done", "detail": "Demande analysée par l'équipe ClipRoll."},
        ],
        "reply": reply.strip(),
        "actions": [],
    }
