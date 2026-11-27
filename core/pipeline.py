import os
import re
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
from core.sound_designer import SoundDesigner, get_wav_duration
from core.timing_tracker import record_actual_timing
from core import production_method as pm
from core.script_template import recent_video_titles, avoid_titles_block
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
        Méthode ClipRoll : plan de production calé sur la voix réelle (plans 2-4 s, twist, SFX ancrés,
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
            "words": words,
            "duration": dur,
            "audio": final_audio,
            "premixed": final_audio != voice_wav,
            "no_music": no_music,
        }

    @staticmethod
    def visual_style_for(plugin: Optional[Dict[str, Any]]) -> Optional[str]:
        """Style de rendu Blender d'un style (plugin) : roblox | paper2d | flat_vector | explainer2d, ou None."""
        if not plugin:
            return None
        prod = plugin.get("production") or {}
        if prod.get("visual_style"):
            return prod["visual_style"]
        if plugin.get("render_mode") == "blender3d":
            return "paper2d" if prod.get("character_style") == "flat2d" else "roblox"
        return None

    @classmethod
    def render_blender_story(
        cls,
        session_id: str,
        script: Dict[str, Any],
        plan: Dict[str, Any],
        words: Optional[List[Dict[str, Any]]],
        plugin: Optional[Dict[str, Any]],
        audio_dur_sec: float,
        out_dir: Path,
        engine: str = "claude",
        engine_model: Optional[str] = None,
        da_ctx: str = "",
        title_text: str = "CLIPOA",
        all_shots: Optional[List[Dict[str, Any]]] = None,
        progress: Optional[Callable[[int, str], None]] = None,
    ) -> Optional[str]:
        """
        Même processus pour tous les styles Blender : Claude décrit le décor de
        CETTE histoire, Blender le construit dans le style choisi. Repli sur l'ancienne scène si tout échoue.
        """
        from core.scene_designer import design_scene
        from core.progress_ticker import MonotoneProgress, ticking
        _p = MonotoneProgress(progress)  # images Blender et minuteur partagent la même barre
        style = cls.visual_style_for(plugin) or "roblox"
        from core.edition import restrict_visual_style
        style = restrict_visual_style(style, plugin)
        eng_lbl = "Claude"
        py_script = str(out_dir / f"{session_id}_scene_3d.py")
        bg_out = str(out_dir / f"{session_id}_blender_bg.mp4")
        if style == "custom":
            # style copié d'une vidéo : moteur écrit sur mesure par l'IA (page animée / three.js ou Blender)
            try:
                from core import custom_engine
                return custom_engine.render_with_style_engine(
                    plugin, session_id, script, words or [], plan, audio_dur_sec, bg_out,
                    engine=engine, model=engine_model, da_hint=da_ctx, progress=progress,
                )
            except Exception as e:
                style = ((plugin or {}).get("production") or {}).get("fallback_style") or "explainer2d"
                _p(56, f"⚠️ Moteur sur mesure indisponible ({str(e)[:90]}) — style intégré le plus proche ({style})")
        if style == "toon_svg":
            # Dessin à compteur : images vectorielles dessinées (SVG), aucun Blender ; repli sur l'Explainer 2D si besoin
            try:
                from core import toon_engine
                if not toon_engine.is_available():
                    raise RuntimeError("navigateur de rendu (Playwright) absent")
                return toon_engine.render_story(session_id, script, plan, words or [], audio_dur_sec, out_dir,
                                                model=engine_model, da_hint=da_ctx, progress=progress)
            except Exception as e:
                print(f"⚠️ Dessin à compteur indisponible ({e}) : rendu Explainer 2D à la place.")
                _p(56, f"⚠️ Dessin à compteur indisponible ({str(e)[:90]}) — rendu Explainer 2D à la place")
                if not BlenderEngine.is_available():
                    return None
                style = "explainer2d"
        if style == "cine3d":
            # Qualité Docteur Shark : moteur three.js ciné ; repli automatique sur Blender Roblox si besoin
            try:
                from core import cine_director
                return cine_director.direct(session_id, script, words or [], audio_dur_sec,
                                            str(out_dir / f"{session_id}_cine_bg.mp4"), engine=engine, model=engine_model,
                                            da_hint=da_ctx, progress=progress)
            except Exception as e:
                print(f"⚠️ Mode Ciné indisponible ({e}) : rendu Blender Roblox à la place.")
                if progress:
                    progress(56, f"⚠️ Mode Ciné indisponible ({str(e)[:90]}) — rendu Blender Roblox à la place")
                style = "roblox"
        total_frames = max(36, int(round(audio_dur_sec * 12)))

        def _blender_prog(f_cur: int, f_tot: int):
            _p(61 + int(round(25 * min(1.0, f_cur / max(1, f_tot)))), f"🧊 [3/4] Rendu Blender en cours… image {f_cur}/{f_tot}")

        try:
            with ticking(_p, 55, 60, 60, f"🎬 [3/4] {eng_lbl} met en scène le décor de ton histoire"):
                spec = design_scene(script, plan, style=style, engine=engine, model=engine_model, words=words, da_hint=da_ctx)
            # style copié d'une vidéo : ses vraies couleurs et sa lumière priment sur les choix du décorateur
            prod = (plugin or {}).get("production") or {}
            if isinstance(prod.get("palette"), dict) and prod["palette"]:
                spec["palette"] = {**(spec.get("palette") or {}), **prod["palette"]}
            if prod.get("time_of_day") in ("day", "sunset", "night"):
                spec["time_of_day"] = prod["time_of_day"]
                for _loc in spec.get("locations") or []:
                    _loc["time_of_day"] = None
            try:
                with open(out_dir / f"{session_id}_scene_spec.json", "w", encoding="utf-8") as f:
                    json.dump(spec, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            _p(60, f"🧊 [3/4] Construction Blender ({len(spec.get('locations') or [])} lieux, {len(plan.get('shots') or [])} plans, style {style})...")
            quality = "fast" if (plugin or {}).get("_render_quality") == "fast" else "hq"
            BlenderEngine.create_scene_from_spec(spec, plan.get("shots") or [], py_script, audio_dur_sec, style=style, words=words, quality=quality)
            with ticking(_p, 61, 86, max(60, total_frames * 1.5), "🧊 [3/4] Rendu Blender en cours"):
                ok = BlenderEngine.render_script(py_script, bg_out, frames=total_frames, progress_cb=_blender_prog)
            if ok:
                return bg_out
            print("⚠️ Rendu du décor sur mesure échoué : scène de secours.")
        except Exception as e:
            print(f"⚠️ Décor sur mesure ignoré ({e}) : scène de secours.")
        try:
            BlenderEngine.create_roblox_3d_scene(
                title_text=title_text, script_save_path=py_script, spoken_script=script.get("full_spoken_script", ""),
                frames=total_frames, shots=all_shots or [], audio_duration_sec=audio_dur_sec,
                timed_shots=plan.get("shots"), mood=plan.get("mood"), character_style=plan.get("character_style") or "r6",
            )
            if BlenderEngine.render_script(py_script, bg_out, frames=total_frames, progress_cb=_blender_prog):
                return bg_out
        except Exception as e:
            print(f"⚠️ Rendu Blender ignoré ({e}).")
        return None

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

    @staticmethod
    def _casting_summary(voice_res: Dict[str, Any]) -> Dict[str, Any]:
        cast = (voice_res or {}).get("casting") or {}
        if not isinstance(cast, dict) or not cast.get("narrator"):
            return {"provider": (voice_res or {}).get("provider", "")}
        def _one(c):
            return {k: c.get(k) for k in ("name", "voice_id", "settings", "why", "source") if c.get(k) is not None}
        out = {"provider": voice_res.get("provider", ""), "by_ai": bool(cast.get("by_ai")), "language": cast.get("language", ""),
               "narrator": _one(cast["narrator"]),
               "characters": {k: _one(c) for k, c in (cast.get("characters") or {}).items() if isinstance(c, dict)}}
        if cast.get("accent_warning"):
            out["accent_warning"] = cast["accent_warning"]
        return out

    @classmethod
    def _fit_voice_to_target(cls, voice_res: Dict[str, Any], spoken: str, target_duration_sec: Optional[int],
                             prod: Optional[Dict[str, Any]] = None, progress=None) -> None:
        """
        1. Rythme du style (Stickman : accélération + silences coupés), plafonné pour ne pas cumuler avec la vitesse
           ElevenLabs (×1,08 × ×1,12 donnait une voix pressée).
        2. Si la voix dépasse la durée demandée, elle est resserrée (dans la limite d'une accélération totale de ×1,15).
        3. Le débit réel est enregistré : le prochain script aura le bon nombre de mots.
        """
        from core import speech_rate
        prod = prod or {}
        wav = voice_res.get("audio_wav") or ""
        if not wav or not os.path.exists(wav):
            return
        speedup = float(voice_res.get("el_speed") or 1.0)
        style_tempo = speech_rate.cap_style_tempo(float(prod.get("voice_tempo") or 1.0), speedup)
        if abs(style_tempo - 1.0) > 0.01 or prod.get("trim_silence"):
            try:
                if progress:
                    progress(46, "🎙️ [2/4] Voix resserrée (rythme du style)…")
                if SoundDesigner.tighten_voice(wav, style_tempo, bool(prod.get("trim_silence"))):
                    speedup *= style_tempo
            except Exception as e:
                print(f"⚠️ Voix non accélérée ({e})")
        dur = get_wav_duration(wav)
        dur_before_fit = dur
        if target_duration_sec:
            extra = speech_rate.fit_tempo(dur, float(target_duration_sec), speedup)
            if extra > 1.0:
                try:
                    if SoundDesigner.tighten_voice(wav, extra, trim_silence=False):
                        print(f"⏱️ Voix de {dur:.1f} s pour {target_duration_sec} s demandées : resserrée ×{extra:.2f}.")
                        speedup *= extra
                        dur = get_wav_duration(wav)
                except Exception as e:
                    print(f"⚠️ Durée de la voix non ajustée ({e})")
            if dur < float(target_duration_sec) * 0.85:
                print(f"⏱️ Voix de {dur:.1f} s pour {target_duration_sec} s demandées : le prochain script sera plus long.")
        n_words = len(re.findall(r"[\wÀ-ÿ'’-]+", spoken or ""))
        # débit mesuré AVANT le recalage sur la cible (sinon chaque recalage gonflerait le débit et rallongerait le script suivant)
        learned = speech_rate.record(voice_res.get("provider", ""), n_words, dur_before_fit)
        voice_res["final_duration_s"] = round(dur, 2)
        voice_res["total_speedup"] = round(speedup, 3)
        if learned:
            voice_res["measured_wps"] = learned

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
        render_quality: str = "hq",
    ) -> Dict[str, Any]:
        """
        Creates a short directly from an idea OR a user's own script ('La Fabrique'),
        optionally applying a Style Plugin's Art Direction (DA) via Claude,
        with multi-shot Blender 3D scenes, ambient music/SFX, and self-learning timings.
        """
        t_start_total = time.time()
        from core.progress_ticker import MonotoneProgress, ticking
        _mono = MonotoneProgress(progress_cb)  # la barre ne recule jamais et avance pendant les longues étapes

        def _prog(pct: int, msg: str):
            print(msg)
            _mono(pct, msg)

        active_engine = "claude"
        eng_name = "Claude"

        plugin = StylePluginStore.get_plugin(plugin_id, include_script_body=True) if plugin_id else None
        if plugin:
            # qualité Blender choisie dans la Fabrique : « hq » (EEVEE, par défaut) ou « fast » (Workbench)
            plugin = dict(plugin, _render_quality="fast" if render_quality == "fast" else "hq")
        # Force automatiquement Blender 3D côté serveur dès que le style choisi requiert Blender (ex. 3D Roblox, 2D × Monde 3D),
        if plugin and (plugin.get("render_mode") == "blender3d" or cls.visual_style_for(plugin)):
            use_blender_3d = True
        is_custom_script = bool((custom_script or "").strip())
        da_ctx = StylePluginStore.build_da_context(plugin_id, preserve_user_script=is_custom_script) if plugin else ""
        effective_theme = theme or (plugin.get("theme") if plugin else DEFAULT_THEME) or DEFAULT_THEME
        effective_sub = subtitle_style or (plugin.get("subtitle_style") if plugin else DEFAULT_SUBTITLE_STYLE) or DEFAULT_SUBTITLE_STYLE

        session_id = resume_session_id or f"{'plugin' if plugin else ('custom' if is_custom_script else 'direct')}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        cp = load_checkpoint(session_id)

        if "script" not in cp:
            if is_custom_script:
                if plugin:
                    _msg = f"🎨 [1/4] {eng_name} applique la DA « {plugin['name']} » sur ton script perso"
                else:
                    _msg = "✍️ [1/4] Préparation de ton script personnalisé"
                with ticking(_mono, 15, 40, 45, _msg):
                    cp["script"] = LeScenariste.direct_custom_script(
                        custom_script=custom_script or "",
                        title=(custom_title or topic or "").strip(),
                        da_context=da_ctx or None,
                    )
            else:
                if plugin:
                    _msg = f"🎨 [1/4] {eng_name} écrit le script dans la DA « {plugin['name']} »"
                else:
                    _msg = f"✍️ [1/4] Le Scénariste écrit ton script avec {eng_name}"
                with ticking(_mono, 15, 40, 70, _msg):
                    cp["script"] = LeScenariste.write_script(
                        topic=topic,
                        user_style=user_style,
                        da_context=da_ctx or None,
                        target_duration_sec=target_duration_sec,
                    )
            save_checkpoint(session_id, cp)
        script = cp["script"]

        if "voice_res" not in cp or "voice_transcript" not in cp:
            _dialogue = script.get("dialogue") if isinstance(script.get("dialogue"), list) and len(script.get("dialogue")) >= 2 else None
            with ticking(_mono, 41, 46, 45, "🎙️ [2/4] Choix des voix et synthèse vocale"):
                cp["voice_res"] = VoiceEngine.generate_voice(
                    text=script.get("full_spoken_script", ""),
                    output_name=session_id,
                    voice=voice,
                    # Le tableau du script (ou le « dialogue » écrit par l'IA) dit qui parle : une voix par personnage
                    segments=template_shots if (is_custom_script and isinstance(template_shots, list)) else _dialogue,
                    style_hint=" · ".join(x for x in ((plugin or {}).get("name"), (plugin or {}).get("tagline"), (topic or "")[:120]) if x),
                    voices_hint=script.get("voices") if isinstance(script.get("voices"), list) else None,
                )
            # Style à narration dense (Stickman) : voix accélérée + silences raccourcis, puis durée calée sur la cible,
            # AVANT le calage mot à mot
            _prod = (plugin or {}).get("production") or {}
            cls._fit_voice_to_target(cp["voice_res"], script.get("full_spoken_script", ""), target_duration_sec, _prod, _prog)
            with ticking(_mono, 46, 50, 40, "🎙️ [2/4] Calage des sous-titres mot à mot"):
                cp["voice_transcript"] = AudioTranscriber.transcribe(cp["voice_res"]["audio_wav"])
            save_checkpoint(session_id, cp)
        voice_res = cp["voice_res"]
        voice_transcript = cp["voice_transcript"]

        if "video_path" not in cp or not os.path.exists(cp["video_path"]):
            effective_bg = background_video
            audio_dur_sec = get_wav_duration(voice_res["audio_wav"])
            all_shots = template_shots if (isinstance(template_shots, list) and len(template_shots) >= 2) else (script.get("visual_storyboard") or [])

            # Méthode ClipRoll : plan calé sur la voix + musique d'ambiance & bruitages (SFX) si cochés
            with ticking(_mono, 50, 54, 20, "🎵 [2/4] Plan de production, musique d'ambiance & bruitages (SFX)"):
                mixres = cls._plan_and_mix(
                    session_id, script, voice_res, voice_transcript, all_shots,
                    enable_music=enable_music, enable_sfx=enable_sfx,
                    style_overrides=(plugin or {}).get("production") if isinstance((plugin or {}).get("production"), dict) else None,
                )
            plan = mixres["plan"]
            final_audio_wav = mixres["audio"]
            blender_bg_path = ""

            if not effective_bg and use_blender_3d and (BlenderEngine.is_available() or cls.visual_style_for(plugin) == "toon_svg"):
                bg = cls.render_blender_story(
                    session_id=session_id, script=script, plan=plan, words=mixres.get("words"), plugin=plugin,
                    audio_dur_sec=audio_dur_sec, out_dir=Path(voice_res["audio_wav"]).parent,
                    engine=active_engine, engine_model=engine_model, da_ctx=da_ctx,
                    title_text=script.get("hook_screen_text") or (topic or "CLIPOA")[:40], all_shots=all_shots,
                    progress=_prog,
                )
                if bg:
                    effective_bg = bg
                    blender_bg_path = bg

            with ticking(_mono, 87, 95, 70, "🎬 [3/4] Montage final 1080x1920 + sous-titres"):
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

        with ticking(_mono, 95, 99, 40, "🔍 [4/4] Audit qualité par Le Contrôle"):
            audit = QualityController.audit_production(video_path, script)
        record_actual_timing(active_engine, "blender3d" if use_blender_3d else "motion", time.time() - t_start_total, target_duration_sec)
        if not resume_session_id:
            # benchmark par style : temps réel + coût Claude réel de CETTE fabrication
            try:
                from core.timing_tracker import record_style_run, style_key
                record_style_run(style_key((plugin or {}).get("id", ""), copied=bool((plugin or {}).get("hidden"))),
                                 active_engine, time.time() - t_start_total, target_duration_sec, t_start_total)
            except Exception:
                pass

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
            # voix réellement utilisée (pour relier plus tard la voix aux vues, et varier d'une vidéo à l'autre)
            "voice_casting": cls._casting_summary(voice_res),
            "voice_timing": {k: voice_res.get(k) for k in ("provider", "el_speed", "total_speedup", "final_duration_s", "measured_wps") if voice_res.get(k) is not None},
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
