# -*- coding: utf-8 -*-
"""
Moteur d'audit de chaîne & d'optimisation de rétention ClipRoll.
Implémente les 8 prompts structurés de rétention Shorts/TikTok (@jeffar_ai) :
  1. Channel Audit System (audit global sur les 12 derniers Shorts du compte actif)
  2. 1.5-Second Hook Rewrite (Evidence + Betrayal : caption ≤4 mots, spoken <7 mots, preuve frame 1)
  3. 130-Word Script Pruner (élagage : ~130 mots/30s, phrases <8 mots, payoff <20s)
  4. 2-Column Mobile Storyboard (cuts toutes les 3-4s, safe zones mobiles)
  5. 6-Second Pattern Interrupt Map (zoom/shake/pop + SFX swoosh/pop/bass drop toutes les 6s)
  6. Voice Pacing & Breath Formatter (micro-pauses & emphase ElevenLabs/TTS)
  7. Seamless Loop & Comment Trigger (question binaire 1 mot + boucle grammaticale sans pause)
  8. Pre-Upload Swipe-Away Audit (seconde exacte de risque de swipe + checklist 5 points)
"""
import json
import re
from typing import Any, Dict, List


def _extract_json_value(raw: str) -> Any:
    """Parse de façon robuste un objet JSON ({...}) ou tableau ([...]) renvoyé par Claude/Gemini."""
    if not raw or not isinstance(raw, str):
        return None
    txt = raw.strip()
    # Retirer les blocs ```json ... ```
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, flags=re.IGNORECASE)
    if m:
        txt = m.group(1).strip()
    try:
        return json.loads(txt)
    except Exception:
        pass
    # Extraire l'objet {...} ou tableau [...] le plus externe
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = txt.find(open_c)
        end = txt.rfind(close_c)
        if start != -1 and end > start:
            cand = txt[start:end + 1]
            try:
                return json.loads(cand)
            except Exception:
                # Nettoyage virgules traînantes éventuelles
                cleaned = re.sub(r",\s*([}\]])", r"\1", cand)
                try:
                    return json.loads(cleaned)
                except Exception:
                    pass
    return None


def _query_json(prompt: str, system_prompt: str) -> Any:
    from core.inspiration_radar import _default_ai_query
    raw = _default_ai_query(prompt, system_prompt)
    return _extract_json_value(raw)


def audit_channel(stats_data: Dict[str, Any]) -> Dict[str, Any]:
    """Prompt #1 : Audit complet des 12 derniers Shorts du compte actif (YouTube ou TikTok)."""
    ch = stats_data.get("channel") or {}
    vids = (stats_data.get("videos") or [])[:12]
    if not vids:
        raise ValueError("Aucune vidéo dans les statistiques du compte actif. Clique d'abord sur « Mettre à jour ».")

    med = float(stats_data.get("median_views") or 0)
    plat = str(ch.get("platform") or (stats_data.get("workspace") or {}).get("platform") or "youtube")
    ch_name = str(ch.get("name") or "Ta chaîne")

    lines = "\n".join(
        f"{i + 1}. « {v.get('title', '')} » — {v.get('views', 0)} vues, {v.get('likes', 0)} likes, "
        f"{v.get('comments', 0)} comm., {v.get('engagement', 0)}% eng., {v.get('duration', 0)}s, "
        f"score {v.get('score', 0)}/100, verdict: {v.get('verdict', '')}"
        for i, v in enumerate(vids)
    )

    sys_p = (
        "Tu es un stratège rétention Shorts/TikTok et consultant chaînes faceless. "
        "Réalise un audit complet des derniers Shorts de la chaîne en français. "
        "Réponds UNIQUEMENT par un objet JSON valide avec exactement ces clés :\n"
        "{\n"
        '  "scorecard": {\n'
        '    "overall": 0-100,\n'
        '    "hook_1_5s": 0-100,\n'
        '    "pacing_rhythm": 0-100,\n'
        '    "engagement_comments": 0-100,\n'
        '    "consistency": 0-100\n'
        "  },\n"
        '  "retention_leaks": [\n'
        '    {"title": "Fuite #1", "impact": "critique|fort|moyen", "detail": "explication chiffrée", "fix": "action immédiate"}\n'
        "  ],\n"
        '  "hook_formula": "Formule d\'accroche 1.5s réécrite (Evidence + Betrayal) adaptée à cette chaîne",\n'
        '  "content_mix": "Répartition recommandée des formats/sujets pour les prochaines vidéos",\n'
        '  "repair_plan": [\n'
        '    {"day": "Jour 1", "task": "1 tâche concrète prioritaire"}\n'
        "  ]\n"
        "}\n"
        "Donne exactement 3 retention_leaks et 7 étapes dans repair_plan."
    )
    user_p = (
        f"Plateforme : {plat} | Chaîne : {ch_name} | Abonnés : {ch.get('subscribers', 0)} | "
        f"Médiane : {int(med)} vues\n\nDerniers Shorts ({len(vids)}) :\n{lines}"
    )
    out = _query_json(user_p, sys_p)
    if not isinstance(out, dict):
        raise RuntimeError("L'IA n'a pas renvoyé un audit JSON exploitable. Réessaie.")
    out["channel_name"] = ch_name
    out["platform"] = plat
    out["videos_analyzed"] = len(vids)
    return out


def generate_hooks_1_5s(topic: str, niche: str = "", current_opening: str = "") -> Dict[str, Any]:
    """Prompt #2 : 5 options d'accroche 1.5s (Evidence + Betrayal)."""
    sys_p = (
        "Tu es un copywriter spécialisé en rétention pour créateurs Shorts/TikTok faceless. "
        "Réécris l'ouverture pour accrocher le viewer en moins de 1,5 seconde avec la formule Evidence + Betrayal. "
        "Réponds UNIQUEMENT par un objet JSON valide :\n"
        '{"hooks": [{"caption_4w": "max 4 mots incrustés", "spoken_7w": "phrase parlée max 7 mots", '
        '"frame1_proof": "preuve visuelle exacte image 1", "why": "pourquoi ça bloque le scroll"}]}\n'
        "Donne exactement 5 options en français."
    )
    user_p = f"Sujet : {topic}\nNiche : {niche or 'auto'}\nOuverture actuelle : {current_opening or 'aucune'}"
    out = _query_json(user_p, sys_p)
    if not isinstance(out, dict) or not isinstance(out.get("hooks"), list):
        raise RuntimeError("Impossible de générer les hooks 1.5s.")
    return out


def optimize_script_retention(script_text: str, topic: str = "", duration_sec: int = 30) -> Dict[str, Any]:
    """
    Prompts #2 à #7 combinés en une passe rapide et actionnable :
    - 5 hooks 1.5s (Evidence + Betrayal)
    - Script élagué (~130 mots / 30s, phrases <8 mots, payoff avant 20s) + rythme voix ElevenLabs + boucle sans pause + question binaire
    - Storyboard 2 colonnes (cut toutes les 3-4s, safe zones)
    - Carte de pattern interrupts toutes les 6s (visuel + SFX)
    """
    script_text = (script_text or "").strip()
    if not script_text and not topic:
        raise ValueError("Écris un sujet ou génère d'abord un script.")

    target_words = max(80, min(420, int(round(duration_sec * (130.0 / 30.0)))))
    payoff_sec = max(12, int(round(duration_sec * 0.65)))

    sys_p = (
        "Tu es un directeur rétention & monteur Shorts/TikTok d'élite. "
        "Optimise ce script en français en appliquant strictement ces 6 règles :\n"
        "1. Hook 1.5s (Evidence + Betrayal) : caption incrustée ≤4 mots, phrase parlée <7 mots, preuve visuelle frame 1.\n"
        f"2. Élagage impitoyable : supprime toute intro polie/remplissage, vise ~{target_words} mots pour {duration_sec}s, "
        f"phrases courtes (<8-10 mots), payoff principal avant la seconde {payoff_sec}.\n"
        "3. Rythme voix ElevenLabs : enchaînements naturels, micro-pauses (...), mots de tension mis en relief.\n"
        "4. Boucle parfaite & commentaires : question binaire polarisante à la fin (réponse en 1 mot) + "
        "dernière syllabe qui se raccorde grammaticalement sans pause au premier mot du hook.\n"
        "5. Storyboard 2 colonnes : un cut visuel toutes les 3 à 4s, texte dans les safe zones mobiles.\n"
        "6. Pattern interrupts toutes les 6s : zoom punch / shake / pop graphique + SFX (swoosh, pop, bass drop).\n"
        "Réponds UNIQUEMENT par un objet JSON valide :\n"
        "{\n"
        '  "hooks": [{"caption_4w": "...", "spoken_7w": "...", "frame1_proof": "..."}],\n'
        '  "optimized_script": "texte complet prêt pour la voix off",\n'
        '  "loop_bridge": "explication du raccord fin -> début + question binaire",\n'
        '  "storyboard": [{"time": "0-3s", "visual_caption": "...", "narration": "..."}],\n'
        '  "pattern_interrupts": [{"sec": 6, "visual": "zoom punch", "sfx": "swoosh"}]\n'
        "}"
    )
    user_p = f"Sujet : {topic or 'non précisé'}\nDurée cible : {duration_sec}s\n\nScript actuel :\n{script_text or topic}"
    out = _query_json(user_p, sys_p)
    if not isinstance(out, dict) or not out.get("optimized_script"):
        raise RuntimeError("L'IA n'a pas renvoyé le script optimisé.")
    return out


def swipe_away_audit(script_text: str, duration_sec: int = 30) -> Dict[str, Any]:
    """Prompt #8 : Audit anti-swipe avant export + checklist 5 points."""
    script_text = (script_text or "").strip()
    if not script_text:
        raise ValueError("Aucun script à auditer.")

    sys_p = (
        "Tu es un auditeur rétention Shorts/TikTok. Audite ce script AVANT export en français. "
        "Repère la seconde exacte où les spectateurs risquent le plus de swiper, explique pourquoi le rythme chute, "
        "donne la correction exacte, et fournis une checklist finale en 5 points. "
        "Réponds UNIQUEMENT par un objet JSON valide :\n"
        "{\n"
        '  "retention_score": 0-100,\n'
        '  "swipe_risk_second": 4,\n'
        '  "why_momentum_drops": "explication concrète",\n'
        '  "exact_fix": "réécriture ou coupe exacte à faire",\n'
        '  "checklist_5": [{"item": "critère", "ok": true, "note": "détail court"}]\n'
        "}"
    )
    user_p = f"Durée cible : {duration_sec}s\n\nScript à auditer :\n{script_text}"
    out = _query_json(user_p, sys_p)
    if not isinstance(out, dict):
        raise RuntimeError("L'audit anti-swipe a échoué.")
    return out
