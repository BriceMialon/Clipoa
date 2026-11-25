import os
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable

from core.scraper import CompetitorScraper
from core.transcriber import AudioTranscriber
from core.voice_engine import VoiceEngine
from core.video_composer import VideoComposer
from core.video_editor import VideoEditor
from core.quality_controller import QualityController
from core.blender_engine import BlenderEngine
from core.postiz_client import PostizClient
from core.checkpoints import load_checkpoint, save_checkpoint, clear_checkpoint
from core.style_plugins import StylePluginStore
from agents.team import LeCloneur, LeScenariste, LeStratege, LeControleur
from config import STORAGE_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE


class ShortCrewPipeline:
    """
    Main orchestration engine implementing the complete ShortCrew workflow:
    1. Competitor outlier detection & recipe extraction ('Le Cloneur')
    2. Weekly content strategy & scriptwriting ('Le Stratège' & 'Le Scénariste')
    3. Neural voice generation & dynamic video rendering ('Le Réalisateur')
    4. Long-form filmed video cutting into vertical 9:16 shorts ('Le Monteur')
    5. Frame-by-frame quality audit ('Le Contrôle')
    6. Targeted revisions with plain language
    """

    @classmethod
    def clone_competitor_short(
        cls,
        video_url: str,
        my_topic: str,
        niche: str = "general",
        user_style: Optional[str] = None,
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        cookies_from_browser: Optional[str] = None,
        voice: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        resume_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _prog(pct: int, msg: str):
            print(msg)
            if progress_cb:
                progress_cb(pct, msg)

        session_id = resume_session_id or f"clone_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        cp = load_checkpoint(session_id)

        if "downloaded" not in cp:
            _prog(10, "📥 [1/5] Téléchargement du short concurrent...")
            cp["downloaded"] = CompetitorScraper.download_video(
                video_url,
                output_id=session_id,
                cookies_from_browser=cookies_from_browser,
            )
            save_checkpoint(session_id, cp)
        downloaded = cp["downloaded"]
        comp_meta = downloaded.get("metadata", {})

        if "comp_transcript" not in cp:
            _prog(28, "🎙️ [2/5] Transcription audio locale (Whisper)...")
            cp["comp_transcript"] = AudioTranscriber.transcribe(downloaded["audio_path"])
            save_checkpoint(session_id, cp)
        comp_transcript = cp["comp_transcript"]

        if "recipe" not in cp:
            _prog(45, "🧠 [3/5] Le Cloneur extrait la recette virale...")
            cp["recipe"] = LeCloneur.analyze_recipe(
                transcript=comp_transcript["text"],
                title=comp_meta.get("title") or Path(video_url).name,
                views=int(comp_meta.get("views") or 0),
            )
            save_checkpoint(session_id, cp)
        recipe = cp["recipe"]

        if "script" not in cp:
            _prog(60, f"✍️ [4/5] Le Scénariste écrit ton script sur '{my_topic}'...")
            cp["script"] = LeScenariste.write_script(
                topic=my_topic,
                recipe=recipe,
                user_style=user_style,
            )
            save_checkpoint(session_id, cp)
        script = cp["script"]

        if "voice_res" not in cp or "voice_transcript" not in cp:
            _prog(75, "🎙️ [5/5] Voix neuronale + sous-titres Submagic...")
            cp["voice_res"] = VoiceEngine.generate_voice(
                text=script.get("full_spoken_script", ""),
                output_name=session_id,
                voice=voice,
            )
            cp["voice_transcript"] = AudioTranscriber.transcribe(cp["voice_res"]["audio_wav"])
            save_checkpoint(session_id, cp)
        voice_res = cp["voice_res"]
        voice_transcript = cp["voice_transcript"]

        if "video_path" not in cp or not os.path.exists(cp["video_path"]):
            _prog(84, "🎬 [5/5] Rendu vidéo vertical 1080x1920...")
            cp["video_path"] = VideoComposer.compose_short(
                output_name=session_id,
                audio_path=voice_res["audio_wav"],
                script_data=script,
                transcript_data=voice_transcript,
                theme=theme,
                subtitle_style=subtitle_style,
            )
            save_checkpoint(session_id, cp)
        video_path = cp["video_path"]

        _prog(92, "🔍 Le Contrôle audite la vidéo finale...")
        audit = QualityController.audit_production(video_path, script)

        result = {
            "session_id": session_id,
            "type": "clone",
            "status": "ready",
            "theme": theme,
            "subtitle_style": subtitle_style,
            "voice": voice,
            "competitor_meta": comp_meta,
            "competitor_recipe": recipe,
            "script": script,
            "video_path": video_path,
            "audit": audit,
            "social_caption": script.get("social_caption", ""),
        }

        meta_file = Path(video_path).parent / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        clear_checkpoint(session_id)
        _prog(100, "✅ Short cloné et prêt !")
        return result

    @classmethod
    def create_direct_short(
        cls,
        topic: str = "",
        user_style: Optional[str] = None,
        background_video: Optional[str] = None,
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        voice: Optional[str] = None,
        use_blender_3d: bool = False,
        retention_boost: bool = True,
        plugin_id: Optional[str] = None,
        custom_script: Optional[str] = None,
        custom_title: Optional[str] = None,
        target_duration_sec: int = 60,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        resume_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a short directly from an idea OR a user's own script ('La Fabrique'),
        optionally applying a Style Plugin's Art Direction (DA) via Claude, with checkpoint resume support.
        """
        def _prog(pct: int, msg: str):
            print(msg)
            if progress_cb:
                progress_cb(pct, msg)

        plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=True) if plugin_id else None
        is_custom_script = bool((custom_script or "").strip())
        da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=is_custom_script) if plugin else ""
        effective_theme = theme or (plugin.get("theme") if plugin else DEFAULT_THEME) or DEFAULT_THEME
        effective_sub = subtitle_style or (plugin.get("subtitle_style") if plugin else DEFAULT_SUBTITLE_STYLE) or DEFAULT_SUBTITLE_STYLE

        session_id = resume_session_id or f"{'plugin' if plugin else ('custom' if is_custom_script else 'direct')}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        cp = load_checkpoint(session_id)

        if "script" not in cp:
            if is_custom_script:
                if plugin:
                    _prog(15, f"🎨 [1/4] Claude applique la DA « {plugin['name']} » sur ton script perso...")
                else:
                    _prog(15, "✍️ [1/4] Préparation de ton script personnalisé...")
                cp["script"] = LeScenariste.direct_custom_script(
                    custom_script=custom_script or "",
                    title=(custom_title or topic or "").strip(),
                    da_context=da_ctx or None,
                )
            else:
                if plugin:
                    _prog(15, f"🎨 [1/4] Claude écrit le script dans la DA « {plugin['name']} »...")
                else:
                    _prog(15, "✍️ [1/4] Le Scénariste écrit ton script avec Claude...")
                cp["script"] = LeScenariste.write_script(
                    topic=topic,
                    user_style=user_style,
                    da_context=da_ctx or None,
                    target_duration_sec=target_duration_sec,
                )
            save_checkpoint(session_id, cp)
        script = cp["script"]

        if "voice_res" not in cp or "voice_transcript" not in cp:
            _prog(42, "🎙️ [2/4] Synthèse vocale + synchronisation mot-par-mot...")
            cp["voice_res"] = VoiceEngine.generate_voice(
                text=script.get("full_spoken_script", ""),
                output_name=session_id,
                voice=voice,
            )
            cp["voice_transcript"] = AudioTranscriber.transcribe(cp["voice_res"]["audio_wav"])
            save_checkpoint(session_id, cp)
        voice_res = cp["voice_res"]
        voice_transcript = cp["voice_transcript"]

        if "video_path" not in cp or not os.path.exists(cp["video_path"]):
            effective_bg = background_video
            if not effective_bg and use_blender_3d and BlenderEngine.is_available():
                _prog(58, "🧊 [3/4] Rendu 3D Blender headless...")
                try:
                    out_dir = Path(voice_res["audio_wav"]).parent
                    py_script = str(out_dir / "scene_3d.py")
                    bg_out = str(out_dir / "blender_bg.mp4")
                    BlenderEngine.create_sample_3d_script(script.get("hook_screen_text") or (topic or "CLIPOA")[:30], py_script)
                    if BlenderEngine.render_script(py_script, bg_out, frames=150):
                        effective_bg = bg_out
                except Exception as e:
                    print(f"⚠️ Rendu Blender ignoré ({e}).")

            _prog(68, "🎬 [3/4] Rendu vertical 1080x1920 + sous-titres Submagic...")
            cp["video_path"] = VideoComposer.compose_short(
                output_name=session_id,
                audio_path=voice_res["audio_wav"],
                script_data=script,
                transcript_data=voice_transcript,
                background_video=effective_bg,
                theme=effective_theme,
                subtitle_style=effective_sub,
                retention_boost=retention_boost,
            )
            save_checkpoint(session_id, cp)
        video_path = cp["video_path"]

        _prog(90, "🔍 [4/4] Audit qualité par Le Contrôle...")
        audit = QualityController.audit_production(video_path, script)

        render_type = "plugin_da" if plugin else ("custom_script" if is_custom_script else "direct")
        result = {
            "session_id": session_id,
            "type": render_type,
            "plugin_id": plugin["id"] if plugin else "",
            "plugin_name": plugin["name"] if plugin else "",
            "target_duration_sec": int(target_duration_sec or 60),
            "status": "ready",
            "theme": effective_theme,
            "subtitle_style": effective_sub,
            "voice": voice,
            "background_video": background_video,
            "script": script,
            "video_path": video_path,
            "audit": audit,
            "social_caption": script.get("social_caption", ""),
        }

        meta_file = Path(video_path).parent / "metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        clear_checkpoint(session_id)
        plugin_suffix = f" ({plugin['name']})" if plugin else ""
        _prog(100, f"✅ Short prêt{plugin_suffix} !")
        return result

    @classmethod
    def cut_long_video(
        cls,
        source: str,
        num_clips: int = 3,
        crop_mode: str = "center",
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        remove_silences: bool = False,
        language: str = "fr",
    ) -> Dict[str, Any]:
        """
        Découpe une vidéo longue filmée (fichier local ou URL YouTube) en Shorts verticaux 9:16 ('Le Monteur').
        """
        return VideoEditor.cut_long_video(
            source=source,
            num_clips=num_clips,
            crop_mode=crop_mode,
            subtitle_style=subtitle_style,
            remove_silences=remove_silences,
            language=language,
        )

    @classmethod
    def revise_short(cls, session_id: str, feedback: str) -> Dict[str, Any]:
        """
        Applies a natural language correction to an existing short.
        Only the targeted elements are regenerated.
        """
        render_dir = STORAGE_DIR / "renders" / session_id
        meta_file = render_dir / "metadata.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Session {session_id} introuvable (metadata.json manquant).")

        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"\n🔄 Application de la retouche ciblée : '{feedback}'...")
        updated_script = LeScenariste.revise_script(data["script"], feedback)

        voice_res = VoiceEngine.generate_voice(
            text=updated_script.get("full_spoken_script", ""),
            output_name=session_id,
            voice=data.get("voice"),
        )
        voice_transcript = AudioTranscriber.transcribe(voice_res["audio_wav"])

        video_path = VideoComposer.compose_short(
            output_name=session_id,
            audio_path=voice_res["audio_wav"],
            script_data=updated_script,
            transcript_data=voice_transcript,
            background_video=data.get("background_video"),
            theme=data.get("theme", DEFAULT_THEME),
            subtitle_style=data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
        )

        audit = QualityController.audit_production(video_path, updated_script)

        data["script"] = updated_script
        data["video_path"] = video_path
        data["audit"] = audit
        if updated_script.get("social_caption"):
            data["social_caption"] = updated_script["social_caption"]

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return data
