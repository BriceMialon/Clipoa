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
from core.style_plugins import StylePluginStore, duration_to_word_range
from core.antigravity_bridge import AntigravityBridge
from core.sound_designer import SoundDesigner, get_wav_duration
from core.timing_tracker import record_actual_timing
from core import production_method as pm
from agents.team import LeCloneur, LeScenariste, LeStratege, LeControleur
from agents.prompts import PROMPT_SCENARISTE
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
    def _plan_and_mix(
        cls,
        session_id: str,
        script: Dict[str, Any],
        voice_res: Dict[str, Any],
        voice_transcript: Optional[Dict[str, Any]],
        shots: Optional[List[Dict[str, Any]]],
        enable_music: bool = True,
        enable_sfx: bool = True,
        style_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Méthode Clipoa : plan de production calé sur la voix réelle (plans 2-4 s, twist, SFX ancrés,
        mots-clés, cartons) puis mix audio (musique d'ambiance + bruitages + version sans musique).
        """
        voice_wav = voice_res["audio_wav"]
        dur = get_wav_duration(voice_wav)
        words = VideoComposer._extract_word_list(voice_transcript, script.get("full_spoken_script", ""), dur)
        plan = pm.build_plan(script, words, dur, shots, style_overrides=style_overrides)
        out_dir = Path(voice_wav).parent
        try:
            pm.save_plan(plan, str(out_dir / f"{session_id}_production_plan.json"))
        except Exception as e:
            print(f"⚠️ Plan de production non sauvegardé ({e}).")
        final_audio, no_music = voice_wav, None
        if enable_music or enable_sfx:
            mixed = str(out_dir / f"{session_id}_mixed.wav")
            nm = str(out_dir / f"{session_id}_sans_musique.wav") if enable_music else None
            final_audio = SoundDesigner.mix_ambient_and_sfx(
                voice_wav=voice_wav,
                output_wav=mixed,
                spoken_script=script.get("full_spoken_script", ""),
                title=script.get("title") or "",
                shots=shots,
                enable_music=enable_music,
                enable_sfx=enable_sfx,
                plan=plan,
                output_no_music_wav=nm,
            )
            if nm and final_audio != voice_wav and os.path.exists(nm):
                no_music = nm
        return {
            "plan": plan,
            "duration": dur,
            "audio": final_audio,
            "premixed": final_audio != voice_wav,
            "no_music": no_music,
        }

    @staticmethod
    def _finalize_outputs(video_path: str, plan: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Range le plan à côté de la vidéo et expose la version sans musique."""
        render_dir = Path(video_path).parent
        try:
            pm.save_plan(plan, str(render_dir / "production_plan.json"))
        except Exception:
            pass
        nm = render_dir / "final_short_sans_musique.mp4"
        result["video_path_no_music"] = str(nm) if nm.exists() else ""
        result["production_stats"] = dict(plan.get("stats") or {}, mood=plan.get("mood"), twist_t=plan.get("twist_t"))

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
        enable_music: bool = True,
        enable_sfx: bool = True,
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

        clone_shots = script.get("visual_storyboard") or []
        _prog(80, "🎵 [5/5] Plan de production + musique d'ambiance & bruitages...")
        mixres = cls._plan_and_mix(session_id, script, voice_res, voice_transcript, clone_shots, enable_music, enable_sfx)
        if "video_path" not in cp or not os.path.exists(cp["video_path"]):
            _prog(84, "🎬 [5/5] Rendu vidéo vertical 1080x1920...")
            cp["video_path"] = VideoComposer.compose_short(
                output_name=session_id,
                audio_path=mixres["audio"],
                script_data=script,
                transcript_data=voice_transcript,
                theme=theme,
                subtitle_style=subtitle_style,
                plan=mixres["plan"],
                audio_premixed=mixres["premixed"],
                alt_audio_path=mixres["no_music"],
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
            "enable_music": enable_music,
            "enable_sfx": enable_sfx,
            "storyboard_shots": clone_shots,
        }
        cls._finalize_outputs(video_path, mixres["plan"], result)

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
        engine: str = "claude",
        engine_model: Optional[str] = None,
        enable_music: bool = True,
        enable_sfx: bool = True,
        template_shots: Optional[List[Dict[str, Any]]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        resume_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a short directly from an idea OR a user's own script ('La Fabrique'),
        optionally applying a Style Plugin's Art Direction (DA) via Claude or Antigravity,
        with multi-shot Blender 3D scenes, ambient music/SFX, and self-learning timings.
        """
        t_start_total = time.time()
        def _prog(pct: int, msg: str):
            print(msg)
            if progress_cb:
                progress_cb(pct, msg)

        active_engine = (engine or "claude").strip().lower()
        if active_engine not in ("claude", "antigravity"):
            active_engine = "claude"
        eng_name = "Antigravity" if active_engine == "antigravity" else "Claude"

        plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=True) if plugin_id else None
        # Force automatiquement Blender 3D côté serveur dès que le style choisi requiert Blender (ex. 3D Roblox, 2D × Monde 3D),
        # que l'IA soit Claude ou Antigravity.
        if plugin and plugin.get("render_mode") == "blender3d":
            use_blender_3d = True
        is_custom_script = bool((custom_script or "").strip())
        da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=is_custom_script) if plugin else ""
        effective_theme = theme or (plugin.get("theme") if plugin else DEFAULT_THEME) or DEFAULT_THEME
        effective_sub = subtitle_style or (plugin.get("subtitle_style") if plugin else DEFAULT_SUBTITLE_STYLE) or DEFAULT_SUBTITLE_STYLE

        session_id = resume_session_id or f"{'agy' if active_engine == 'antigravity' else ('plugin' if plugin else ('custom' if is_custom_script else 'direct'))}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        cp = load_checkpoint(session_id)

        if "script" not in cp:
            if active_engine == "antigravity":
                dur_info = duration_to_word_range(target_duration_sec)
                if is_custom_script:
                    _prog(15, f"✨ [1/4] Antigravity ({engine_model or 'auto'}) prépare la mise en scène sur ton script...")
                    ag_prompt = (
                        f"Script exact de l'utilisateur à conserver MOT POUR MOT dans `full_spoken_script` :\n{custom_script}\n\n"
                        f"Titre optionnel : {(custom_title or topic or '').strip()}\n"
                        f"{da_ctx}\n"
                        "Réponds UNIQUEMENT en JSON valide avec les clés : title, hook_screen_text, full_spoken_script, visual_storyboard (liste de scènes), twist_text, caption_keywords, on_screen_notes, social_caption."
                    )
                else:
                    _prog(15, f"✨ [1/4] Antigravity ({engine_model or 'auto'}) écrit ton script (~{dur_info['duration_sec']}s)...")
                    ag_prompt = (
                        f"Sujet : {topic}\n"
                        f"Durée cible : ~{dur_info['duration_sec']} secondes ({dur_info['min_words']} à {dur_info['max_words']} mots parlés, {dur_info['plans_min']} à {dur_info['plans_max']} plans).\n"
                        f"{('Style demandé : ' + user_style + chr(10)) if user_style else ''}"
                        f"{da_ctx}\n"
                        "Réponds UNIQUEMENT en JSON valide avec les clés : title, hook_screen_text, full_spoken_script, visual_storyboard, twist_text, caption_keywords, on_screen_notes, social_caption."
                    )
                raw_ag = AntigravityBridge.query(ag_prompt, system_prompt=PROMPT_SCENARISTE, model=engine_model)
                parsed_ag = None
                try:
                    m = raw_ag.strip()
                    if "```" in m:
                        import re as _re
                        blk = _re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", m)
                        if blk:
                            m = blk.group(1).strip()
                    parsed_ag = json.loads(m[m.find("{") : m.rfind("}") + 1])
                except Exception:
                    parsed_ag = {
                        "title": (custom_title or topic or "Mon Short")[:60],
                        "hook_screen_text": (custom_title or topic or "Mon Short")[:45],
                        "full_spoken_script": (custom_script or raw_ag).strip(),
                        "visual_storyboard": [],
                        "social_caption": f"{(custom_title or topic or 'Short')[:80]} #Shorts",
                    }
                if is_custom_script:
                    parsed_ag["full_spoken_script"] = (custom_script or "").strip()
                cp["script"] = parsed_ag
            elif is_custom_script:
                if plugin:
                    _prog(15, f"🎨 [1/4] {eng_name} applique la DA « {plugin['name']} » sur ton script perso...")
                else:
                    _prog(15, "✍️ [1/4] Préparation de ton script personnalisé...")
                cp["script"] = LeScenariste.direct_custom_script(
                    custom_script=custom_script or "",
                    title=(custom_title or topic or "").strip(),
                    da_context=da_ctx or None,
                )
            else:
                if plugin:
                    _prog(15, f"🎨 [1/4] {eng_name} écrit le script dans la DA « {plugin['name']} »...")
                else:
                    _prog(15, f"✍️ [1/4] Le Scénariste écrit ton script avec {eng_name}...")
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
            audio_dur_sec = get_wav_duration(voice_res["audio_wav"])
            all_shots = template_shots if (isinstance(template_shots, list) and len(template_shots) >= 2) else (script.get("visual_storyboard") or [])

            # Méthode Clipoa : plan calé sur la voix + musique d'ambiance & bruitages (SFX) si cochés
            _prog(50, "🎵 [2/4] Plan de production, musique d'ambiance & bruitages (SFX)...")
            mixres = cls._plan_and_mix(
                session_id, script, voice_res, voice_transcript, all_shots,
                enable_music=enable_music, enable_sfx=enable_sfx,
                style_overrides=(plugin or {}).get("production") if isinstance((plugin or {}).get("production"), dict) else None,
            )
            plan = mixres["plan"]
            final_audio_wav = mixres["audio"]
            blender_bg_path = ""

            if not effective_bg and use_blender_3d and BlenderEngine.is_available():
                _prog(56, f"🧊 [3/4] Rendu multi-plans 3D Blender ({len(plan.get('shots') or []) or max(8, len(all_shots))} plans calés sur la voix · {int(round(audio_dur_sec))}s)...")
                try:
                    out_dir = Path(voice_res["audio_wav"]).parent
                    py_script = str(out_dir / f"{session_id}_scene_3d.py")
                    bg_out = str(out_dir / f"{session_id}_blender_bg.mp4")
                    total_frames = max(72, int(round(audio_dur_sec * 12)))
                    rendered = False
                    def _blender_prog(f_cur: int, f_tot: int):
                        pct = 56 + int(round(17 * min(1.0, f_cur / max(1, f_tot))))
                        _prog(pct, f"🧊 [3/4] Rendu 3D Blender en cours… image {f_cur}/{f_tot}")
                    # Pour Roblox 3D & 2D×Monde 3D : moteur multi-plans 3D couvrant 100% de la durée de la vidéo !
                    if plugin and plugin.get("id") in ("roblox_3d", "2d_monde_3d"):
                        BlenderEngine.create_roblox_3d_scene(
                            title_text=script.get("hook_screen_text") or (topic or "CLIPOA")[:40],
                            script_save_path=py_script,
                            spoken_script=script.get("full_spoken_script", ""),
                            frames=total_frames,
                            shots=all_shots,
                            audio_duration_sec=audio_dur_sec,
                            timed_shots=plan.get("shots"),
                        )
                        rendered = BlenderEngine.render_script(py_script, bg_out, frames=total_frames, progress_cb=_blender_prog)
                    else:
                        ai_ok = AntigravityBridge.generate_blender_script(
                            topic=topic or script.get("title") or "Short 3D",
                            spoken_script=script.get("full_spoken_script", ""),
                            script_save_path=py_script,
                            da_context=da_ctx,
                            visual_storyboard=all_shots,
                            frames=total_frames,
                            engine=active_engine,
                            model=engine_model,
                        )
                        if ai_ok:
                            rendered = BlenderEngine.render_script(py_script, bg_out, frames=total_frames, progress_cb=_blender_prog)
                        if not rendered:
                            BlenderEngine.create_roblox_3d_scene(
                                title_text=script.get("hook_screen_text") or (topic or "CLIPOA")[:40],
                                script_save_path=py_script,
                                spoken_script=script.get("full_spoken_script", ""),
                                frames=total_frames,
                                shots=all_shots,
                                audio_duration_sec=audio_dur_sec,
                            )
                            rendered = BlenderEngine.render_script(py_script, bg_out, frames=total_frames, progress_cb=_blender_prog)
                    if rendered:
                        effective_bg = bg_out
                        blender_bg_path = bg_out
                except Exception as e:
                    print(f"⚠️ Rendu Blender ignoré ({e}).")

            _prog(74, "🎬 [3/4] Montage final 1080x1920 + sous-titres...")
            cp["video_path"] = VideoComposer.compose_short(
                output_name=session_id,
                audio_path=final_audio_wav,
                script_data=script,
                transcript_data=voice_transcript,
                background_video=effective_bg,
                theme=effective_theme,
                subtitle_style=effective_sub,
                retention_boost=retention_boost,
                plan=plan,
                audio_premixed=mixres["premixed"],
                alt_audio_path=mixres["no_music"],
            )
            cp["plan"] = plan
            cp["blender_bg"] = blender_bg_path
            save_checkpoint(session_id, cp)
        video_path = cp["video_path"]

        _prog(90, "🔍 [4/4] Audit qualité par Le Contrôle...")
        audit = QualityController.audit_production(video_path, script)
        record_actual_timing(active_engine, "blender3d" if use_blender_3d else "motion", time.time() - t_start_total, target_duration_sec)

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
            "enable_music": enable_music,
            "enable_sfx": enable_sfx,
            "blender_bg": cp.get("blender_bg", ""),
            "storyboard_shots": template_shots if (isinstance(template_shots, list) and len(template_shots) >= 2) else (script.get("visual_storyboard") or []),
            "retention_boost": retention_boost,
        }
        if cp.get("plan"):
            cls._finalize_outputs(video_path, cp["plan"], result)

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

        # Retouche : on garde musique/bruitages et le fond 3D Blender déjà rendu (pas de re-rendu coûteux)
        mixres = cls._plan_and_mix(
            session_id, updated_script, voice_res, voice_transcript, data.get("storyboard_shots") or updated_script.get("visual_storyboard") or [],
            enable_music=bool(data.get("enable_music", True)), enable_sfx=bool(data.get("enable_sfx", True)),
        )
        bg = data.get("background_video") or ""
        if not bg and data.get("blender_bg") and os.path.exists(data["blender_bg"]):
            bg = data["blender_bg"]
        video_path = VideoComposer.compose_short(
            output_name=session_id,
            audio_path=mixres["audio"],
            script_data=updated_script,
            transcript_data=voice_transcript,
            background_video=bg or None,
            theme=data.get("theme", DEFAULT_THEME),
            subtitle_style=data.get("subtitle_style", DEFAULT_SUBTITLE_STYLE),
            retention_boost=bool(data.get("retention_boost", True)),
            plan=mixres["plan"],
            audio_premixed=mixres["premixed"],
            alt_audio_path=mixres["no_music"],
        )
        cls._finalize_outputs(video_path, mixres["plan"], data)

        audit = QualityController.audit_production(video_path, updated_script)

        data["script"] = updated_script
        data["video_path"] = video_path
        data["audit"] = audit
        if updated_script.get("social_caption"):
            data["social_caption"] = updated_script["social_caption"]

        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return data
