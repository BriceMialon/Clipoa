import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.claude_bridge import ClaudeBridge
from core.gemini_studio import GeminiStudio
from core.drive_client import DriveClient
from core.style_plugins import StylePluginStore
from core.scraper import CompetitorScraper
from agents.team import _clean_json_response


EXPERT_SCRIPT_SKILL = """Tu es l'Agent Expert Script de ClipRoll — un scénariste d'élite spécialisé dans la rétention extrême sur YouTube Shorts, TikTok et Instagram Reels.

=== SKILL : ARCHITECTURE VIRALE HAUTE RÉTENTION ===
1. HOOK 0-2s (Stop-Scroll absolu) :
   - Ouvre immédiatement par une tension, une contradiction, un chiffre choquant ou une promesse concrète.
   - INTERDIT : « Salut tout le monde », « Aujourd'hui on va voir », « Dans cette vidéo ».
2. RYTHME ORAL (130 à 165 mots pour 48-58 secondes) :
   - Phrases courtes (6 à 12 mots max), langage oral naturel et direct.
   - Zéro remplissage : chaque phrase apporte un fait nouveau ou une relance d'attention (micro-hook toutes les 7 secondes).
3. ESCALADE & TWIST (20-45s) :
   - Crée une boucle ouverte dès la 1ère phrase qui n'est résolue qu'à la fin.
   - Insère un retournement ou une révélation contre-intuitive au milieu pour empêcher le décrochage.
4. CHUTE & BOUCLE (45-58s) :
   - Termine par une phrase mémorable qui déclenche commentaires, sauvegardes ou replays (ou une boucle naturelle vers le début).
5. AUTO-AUDIT :
   - Évalue ton propre script sur 4 critères (/10) : hook, retention, clarte, viralite.
"""


class ScriptExpertAgent:
    """
    Agent Expert Script de ClipRoll :
    - Tourne sur Claude Opus (medium) OU le meilleur modèle Google Gemini disponible
    - Injecte automatiquement la Direction Artistique (DA) du Plugin de Style sélectionné
    - Connecté au scraper concurrents pour générer soit du 100% neuf, soit à partir des pépites d'un concurrent
    """

    @classmethod
    def _load_skills_context(cls, plugin_id: Optional[str] = None) -> str:
        sync_dir = DriveClient.get_sync_dir()
        chunks: List[str] = [EXPERT_SCRIPT_SKILL]

        guide_path = sync_dir / "guide_retention.md"
        if guide_path.exists():
            try:
                txt = guide_path.read_text(encoding="utf-8", errors="ignore").strip()
                if txt:
                    chunks.append("=== GUIDE RÉTENTION LOCAL ===\n" + txt[:3200])
            except Exception:
                pass

        if plugin_id:
            da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=False)
            if da_ctx:
                chunks.append(da_ctx[:4800])

        return "\n\n".join(chunks)

    @classmethod
    def _call_brain(cls, prompt: str, system_prompt: str, engine: str = "claude") -> Dict[str, Any]:
        if engine == "gemini":
            raw = GeminiStudio.query(prompt, system_prompt=system_prompt, model=GeminiStudio.get_best_available_model())
        else:
            raw = ClaudeBridge.query(prompt, system_prompt=system_prompt, action="script_expert")
        return _clean_json_response(raw)

    @classmethod
    def generate(
        cls,
        topic: str = "",
        niche: str = "",
        competitor_url: str = "",
        plugin_id: Optional[str] = None,
        target_duration_sec: int = 60,
        engine: str = "claude",
    ) -> Dict[str, Any]:
        from core.style_plugins import duration_to_word_range
        dur = duration_to_word_range(target_duration_sec)
        dur_rule = (
            f"\nDURÉE CIBLE OBLIGATOIRE : ~{dur['duration_sec']} secondes "
            f"(écris entre {dur['min_words']} et {dur['max_words']} mots parlés)."
        )
        sys_prompt = (
            cls._load_skills_context(plugin_id=plugin_id)
            + dur_rule
            + '\n\nFormat de sortie JSON STRICT uniquement :\n'
              '{"title": "Titre court", "hook_screen_text": "3-5 MOTS CHOC", '
              '"script": "Texte parlé complet mot à mot", '
              '"why_viral": "Pourquoi ce script va retenir l\'audience", '
              '"scores": {"hook": 9.2, "retention": 9.0, "viralite": 9.1}, '
              '"tip": "1 conseil concret pour le rendu"}'
        )

        comp_block = ""
        scanned_meta = None
        if competitor_url.strip():
            try:
                scan = CompetitorScraper.find_outliers(competitor_url.strip(), limit=20, threshold=1.8)
                outliers = scan.get("outliers") or []
                scanned_meta = {
                    "channel_url": scan.get("channel_url"),
                    "median_views": scan.get("median_views", 0),
                    "outliers_count": len(outliers),
                }
                if outliers:
                    lines = "\n".join(
                        f"- {o.get('title')} ({o.get('ratio')}x médiane · {o.get('views'):,} vues)"
                        for o in outliers[:8]
                    )
                    comp_block = (
                        f"\n\nDONNÉES LIVE DU PLUGIN SCRAPER CONCURRENTS ({scan.get('channel_url')}) :\n"
                        f"Médiane du compte : {scan.get('median_views', 0):,} vues\n"
                        f"Vidéos qui ont explosé :\n{lines}\n"
                        "Analyse la mécanique psychologique de ces pépites et crée un script 100% ORIGINAL qui applique ce qui marche."
                    )
            except Exception as e:
                comp_block = f"\n(Note scraper : {e})"

        if topic.strip():
            user_prompt = f"Sujet demandé : {topic.strip()}\n{f'Niche : {niche}' if niche else ''}{comp_block}\nÉcris le meilleur script possible en JSON strict."
        else:
            user_prompt = f"Je pars de 0{f' dans la niche : {niche}' if niche else ''}.{comp_block}\nInvente une idée à fort potentiel viral et écris le script complet en JSON strict."

        res = cls._call_brain(user_prompt, sys_prompt, engine=engine)
        if scanned_meta:
            res["competitor_scan"] = scanned_meta
        return res

    @classmethod
    def refine(
        cls,
        current_script: str,
        title: str,
        instruction: str,
        plugin_id: Optional[str] = None,
        engine: str = "claude",
    ) -> Dict[str, Any]:
        sys_prompt = (
            cls._load_skills_context(plugin_id=plugin_id)
            + '\n\nApplique précisément la modification demandée par le créateur tout en gardant un rythme oral irréprochable.\n'
              'Format de sortie JSON STRICT uniquement :\n'
              '{"title": "...", "hook_screen_text": "3-5 MOTS CHOC", "script": "...", '
              '"changes": "Résumé en 1 phrase de ce qui a été amélioré", '
              '"scores": {"hook": 9.4, "retention": 9.2, "viralite": 9.3}}'
        )
        prompt = f"Titre actuel : {title}\n\nScript actuel :\n{current_script}\n\nConsigne de modification : {instruction}"
        return cls._call_brain(prompt, sys_prompt, engine=engine)

    @classmethod
    def propose_from_outliers(
        cls,
        outliers: List[Dict[str, Any]],
        niche: str = "ma chaîne",
        plugin_id: Optional[str] = None,
        engine: str = "claude",
    ) -> List[Dict[str, Any]]:
        sys_prompt = (
            cls._load_skills_context(plugin_id=plugin_id)
            + '\n\nÀ partir des vidéos concurrentes qui ont explosé, propose 5 idées 100% originales avec leur script complet prêt à tourner.\n'
              'Rends UNIQUEMENT un JSON strict : {"ideas": [{"title": "...", "hook_screen_text": "...", "why_viral": "...", "script": "..."}]}'
        )
        top_lines = "\n".join(
            f"- {o.get('title', 'Sans titre')} ({o.get('ratio', 2)}x médiane, {o.get('views', 0)} vues)"
            for o in outliers[:10]
        )
        prompt = f"Niche / chaîne cible : {niche}\n\nPépites concurrentes détectées :\n{top_lines}\n\nPropose 5 idées + scripts originaux."
        res = cls._call_brain(prompt, sys_prompt, engine=engine)
        if isinstance(res, dict):
            return res.get("ideas") or []
        return res if isinstance(res, list) else []
