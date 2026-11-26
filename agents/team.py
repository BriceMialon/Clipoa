import json
import re
import logging
from typing import Dict, Any, Optional, List
from core.claude_bridge import ClaudeBridge
from agents.prompts import (
    PROMPT_CLONEUR,
    PROMPT_SCENARISTE,
    PROMPT_STRATEGE,
    PROMPT_CONTROLEUR,
    PROMPT_MONTEUR,
)

logger = logging.getLogger("AITeam")

def _clean_json_response(raw: str) -> Dict[str, Any]:
    """Helper to cleanly parse JSON even if Claude/Gemini wraps it in prose or markdown backticks."""
    text = (raw or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fallback: extract outermost JSON object or array
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                pass
    logger.warning(f"Failed to parse json directly. Raw response: {text[:200]}")
    return {"raw_output": raw}

class LeCloneur:
    @classmethod
    def analyze_recipe(cls, transcript: str, title: str = "", views: int = 0) -> Dict[str, Any]:
        prompt = (
            f"Titre du short : {title}\n"
            f"Vues obtenues : {views}\n\n"
            f"Transcription intégrale :\n{transcript}\n\n"
            "Analyse la recette de ce short et fournis le template réutilisable au format JSON."
        )
        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_CLONEUR)
        return _clean_json_response(raw)

class LeScenariste:
    @classmethod
    def write_script(
        cls,
        topic: str,
        recipe: Optional[Dict[str, Any]] = None,
        user_style: Optional[str] = None,
        da_context: Optional[str] = None,
        target_duration_sec: int = 60,
    ) -> Dict[str, Any]:
        from core.style_plugins import duration_to_word_range
        dur = duration_to_word_range(target_duration_sec)
        prompt = (
            f"Sujet à traiter : {topic}\n"
            f"DURÉE CIBLE DE LA VIDÉO : environ {dur['duration_sec']} secondes "
            f"(entre {dur['min_words']} et {dur['max_words']} mots parlés dans `full_spoken_script`, "
            f"environ {dur['plans_min']} à {dur['plans_max']} plans dans `visual_storyboard`). "
            "Respecte impérativement cette durée cible.\n"
        )
        if da_context:
            prompt += f"\n{da_context}\n"
        if recipe:
            prompt += f"\nRecette d'une vidéo qui marche (piste de rythme et de style, l'idée prime) :\n{json.dumps(recipe, ensure_ascii=False, indent=2)}\n"
        if user_style:
            prompt += f"\nStyle et façon de parler de l'utilisateur :\n{user_style}\n"
        from core.script_template import recent_video_titles, avoid_titles_block
        prompt += avoid_titles_block(recent_video_titles())
        prompt += (
            "\nL'histoire part de ce sujet et de rien d'autre : invente des personnages, un objet-clé, des lieux et un "
            "retournement propres à ce sujet (les exemples de la DA sont du style, pas des sujets).\n"
        )
        prompt += "\nRédige le script final prêt à être synthétisé ainsi que le visual_storyboard dans la DA demandée, au format JSON strict."

        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_SCENARISTE)
        return _clean_json_response(raw)

    @classmethod
    def direct_custom_script(
        cls,
        custom_script: str,
        title: str = "",
        da_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prend le script PERSONNEL de l'utilisateur (conservé mot à mot) et demande à Claude
        de concevoir toute la Direction Artistique (visual_storyboard, hook_screen_text,
        social_caption) selon le Plugin de Style actif.
        """
        clean_script = (custom_script or "").strip()
        fallback_title = (title or clean_script.split(".")[0][:48] or "Mon Short").strip()
        if not da_context:
            return {
                "title": fallback_title,
                "hook_spoken": clean_script.split(".")[0][:120],
                "hook_screen_text": fallback_title[:40],
                "full_spoken_script": clean_script,
                "visual_storyboard": [],
                "social_caption": f"{fallback_title} #shorts #video",
            }

        prompt = (
            f"{da_context}\n\n"
            f"Titre souhaité (optionnel) : {fallback_title}\n\n"
            f"SCRIPT EXACT DE L'UTILISATEUR (À CONSERVER MOT POUR MOT) :\n{clean_script}\n\n"
            "Prépare la mise en scène, le découpage visuel (visual_storyboard), le hook_screen_text et la social_caption "
            "dans la Direction Artistique du plugin ci-dessus, tout en gardant `full_spoken_script` strictement fidèle au texte de l'utilisateur. "
            "Rends le JSON strict."
        )
        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_SCENARISTE, action="plugin_da_direction")
        parsed = _clean_json_response(raw)
        if not isinstance(parsed, dict):
            parsed = {}
        # Guarantee the user's exact spoken script is always preserved!
        parsed["full_spoken_script"] = clean_script
        parsed.setdefault("title", fallback_title)
        parsed.setdefault("hook_spoken", clean_script.split(".")[0][:120])
        parsed.setdefault("hook_screen_text", (parsed.get("title") or fallback_title)[:40])
        parsed.setdefault("social_caption", f"{parsed['title']} #shorts")
        return parsed

    @classmethod
    def revise_script(cls, script_data: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """
        Modification ciblée en langage naturel :
        Exemple : 'refais le début de la vidéo pour qu'il soit plus percutant'.
        Le reste du short ne bouge pas.
        """
        prompt = (
            f"Script actuel :\n{json.dumps(script_data, ensure_ascii=False, indent=2)}\n\n"
            f"Demande de modification de l'utilisateur :\n\"{feedback}\"\n\n"
            "Modifie UNIQUEMENT le point demandé. Conserve tout le reste intact. Rends le JSON complet mis à jour."
        )
        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_SCENARISTE)
        return _clean_json_response(raw)

class LeStratege:
    @classmethod
    def plan_weekly_shorts(cls, niche: str, user_profile: str = "", engine: str = "claude") -> List[Dict[str, Any]]:
        prompt = (
            f"Niche / Thématique : {niche}\n"
            f"Profil du créateur : {user_profile}\n\n"
            "Génère la planification complète des 5 shorts de la semaine (du lundi au vendredi) au format JSON strict :\n"
            '{"semaine": [{"jour": "Lundi", "angle": "...", "titre": "...", "promesse": "..."}]}'
        )
        if (engine or "claude").strip().lower() == "gemini":
            from core.gemini_studio import GeminiStudio
            raw = GeminiStudio.query(prompt, system_prompt=PROMPT_STRATEGE, model=GeminiStudio.get_best_available_model())
        else:
            raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_STRATEGE, action="weekly_plan")
        res = _clean_json_response(raw)
        if isinstance(res, list):
            return res
        return res.get("semaine") or res.get("shorts") or [res]

class LeControleur:
    @classmethod
    def audit_script(cls, script_data: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            f"Voici le script du short à valider :\n"
            f"{json.dumps(script_data, ensure_ascii=False, indent=2)}\n\n"
            "Évalue ce script selon les standards stricts de rétention des Shorts et TikToks. Rends ton audit en JSON."
        )
        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_CONTROLEUR)
        return _clean_json_response(raw)


class LeMonteur:
    @classmethod
    def find_best_clips(
        cls,
        segments: List[Dict[str, Any]],
        num_clips: int = 3,
        min_duration: int = 20,
        max_duration: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Analyse la transcription horodatée d'une vidéo longue et sélectionne
        les `num_clips` passages les plus viraux.
        """
        lines = []
        for seg in segments:
            s = round(float(seg.get("start", 0.0)), 2)
            e = round(float(seg.get("end", 0.0)), 2)
            txt = str(seg.get("text", "")).strip()
            if txt:
                lines.append(f"[{s}s - {e}s] {txt}")

        transcript_block = "\n".join(lines)
        # Keep prompt within a clean size window
        if len(transcript_block) > 24000:
            transcript_block = transcript_block[:24000] + "\n...[tronqué]"

        prompt = (
            f"Voici la transcription horodatée de la vidéo filmée :\n\n"
            f"{transcript_block}\n\n"
            f"Sélectionne les {num_clips} meilleurs moments viraux (durée entre {min_duration}s et {max_duration}s chacun). "
            f"Rends le JSON strict avec la clé 'clips'."
        )
        raw = ClaudeBridge.query(prompt, system_prompt=PROMPT_MONTEUR)
        parsed = _clean_json_response(raw)
        if isinstance(parsed, list):
            return parsed[:num_clips]
        clips = parsed.get("clips") or []
        return clips[:num_clips]
