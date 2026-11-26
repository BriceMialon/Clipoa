import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import FFMPEG_PATH, RENDERS_DIR, DOWNLOADS_DIR, DEFAULT_SUBTITLE_STYLE
from core.scraper import CompetitorScraper
from core.transcriber import AudioTranscriber
from core.video_composer import VideoComposer, SUBTITLE_STYLES, LOUDNORM
from core.production_method import classify_keywords
from agents.team import LeMonteur


class VideoEditor:
    """
    'Le Monteur' — Module de montage de vidéos filmées longues en Shorts verticaux 9:16 (1080x1920).
    Pipeline :
    1. Ingestion d'une vidéo locale (.mp4/.mov/.mkv) ou d'une URL YouTube
    2. Transcription mot-par-mot locale (faster-whisper)
    3. Sélection IA des meilleurs moments viraux (LeMonteur)
    4. Découpe précise + suppression optionnelle des silences (jump-cuts)
    5. Recadrage vertical 9:16 ('center' ou 'blurred_bg') + sous-titres Submagic mot-par-mot + hook + barre de progression
    """

    @classmethod
    def _extract_audio_wav(cls, video_path: str, audio_out: Path) -> str:
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(audio_out),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode != 0:
            raise RuntimeError(f"Erreur extraction audio : {res.stderr[-600:]}")
        return str(audio_out)

    @classmethod
    def _detect_speech_intervals(
        cls,
        clip_path: str,
        clip_duration: float,
        noise_db: str = "-35dB",
        min_silence: float = 0.75,
        pad: float = 0.12
    ) -> List[Tuple[float, float]]:
        """
        Uses FFmpeg silencedetect to identify non-silent speech intervals for dynamic jump-cuts.
        """
        cmd = [
            FFMPEG_PATH,
            "-i", clip_path,
            "-af", f"silencedetect=noise={noise_db}:d={min_silence}",
            "-f", "null",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", res.stderr)]
        ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", res.stderr)]

        if not starts:
            return [(0.0, clip_duration)]

        silences: List[Tuple[float, float]] = []
        for idx, s in enumerate(starts):
            e = ends[idx] if idx < len(ends) else clip_duration
            silences.append((s, e))

        speech: List[Tuple[float, float]] = []
        cursor = 0.0
        for s, e in silences:
            seg_end = min(clip_duration, s + pad)
            if seg_end - cursor >= 0.25:
                speech.append((cursor, seg_end))
            cursor = max(cursor, e - pad)

        if clip_duration - cursor >= 0.25:
            speech.append((cursor, clip_duration))

        return speech if speech else [(0.0, clip_duration)]

    @classmethod
    def _remove_silences_jumpcut(cls, input_clip: str, output_clip: str, clip_duration: float) -> str:
        """Cuts out dead pauses to create punchy TikTok/YouTube jump-cut pacing."""
        intervals = cls._detect_speech_intervals(input_clip, clip_duration)
        if len(intervals) <= 1 and (intervals[0][1] - intervals[0][0]) >= clip_duration - 0.4:
            # Nothing significant to cut
            return input_clip

        filter_parts = []
        concat_inputs = []
        for idx, (s, e) in enumerate(intervals):
            filter_parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{idx}]")
            filter_parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{idx}]")
            concat_inputs.append(f"[v{idx}][a{idx}]")

        filter_complex = ";".join(filter_parts) + f";{''.join(concat_inputs)}concat=n={len(intervals)}:v=1:a=1[vout][aout]"
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", input_clip,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-threads", "0",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            output_clip,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            # Fallback safely to original clip if concat fails
            return input_clip
        return output_clip

    @staticmethod
    def _slice_words_for_clip(
        transcript: Dict[str, Any],
        start_sec: float,
        end_sec: float
    ) -> List[Dict[str, Any]]:
        """Extracts and time-shifts word timestamps to [0, clip_duration]."""
        words: List[Dict[str, Any]] = []
        for seg in transcript.get("segments", []):
            for w in seg.get("words", []):
                ws = float(w.get("start", 0.0))
                we = float(w.get("end", ws + 0.1))
                if we >= start_sec and ws <= end_sec:
                    shifted_s = max(0.0, ws - start_sec)
                    shifted_e = max(shifted_s + 0.05, min(end_sec - start_sec, we - start_sec))
                    txt = str(w.get("word", "")).strip()
                    if txt:
                        words.append({
                            "word": txt,
                            "start": round(shifted_s, 2),
                            "end": round(shifted_e, 2),
                        })
        return words

    @classmethod
    def _render_vertical_clip(
        cls,
        clip_source: str,
        output_mp4: str,
        ass_path: str,
        duration: float,
        crop_mode: str = "center",
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
    ) -> str:
        """
        Converts a trimmed clip into a polished 1080x1920 vertical short with
        Submagic ASS subtitles, hook banner, and animated progress bar.
        """
        ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        style_cfg = SUBTITLE_STYLES.get(subtitle_style, SUBTITLE_STYLES["submagic_yellow"])
        bar_color = style_cfg["bar_color"]

        if crop_mode == "blurred_bg":
            bg_chain = (
                "[0:v]split=2[vbg][vfg];"
                "[vbg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:4,eq=brightness=-0.14[bg_blur];"
                "[vfg]scale=1080:-2:force_original_aspect_ratio=decrease:flags=lanczos[fg_sharp];"
                "[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2,fps=30,vignette=PI/5[base]"
            )
        else:
            bg_chain = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,fps=30,"
                "eq=contrast=1.04:saturation=1.06,vignette=PI/5[base]"
            )

        bar_chain = (
            f"color=c={bar_color}:s=1080x10:d={duration:.2f}:r=30[bar];"
            f"[base][bar]overlay=x='-W+W*(t/{duration:.2f})':y=0:shortest=1,"
            f"ass='{ass_escaped}',format=yuv420p[vout]"
        )
        filter_complex = f"{bg_chain};{bar_chain}"

        cmd = [
            FFMPEG_PATH,
            "-y",
            "-i", clip_source,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            *VideoComposer.VIDEO_ENCODE_ARGS,
            # Voix filmée plus claire + volume normalisé -14 LUFS (standard Shorts)
            "-af", f"highpass=f=80,equalizer=f=3000:t=q:w=1.0:g=2,acompressor=threshold=-20dB:ratio=2.2:attack=15:release=150,{LOUDNORM}",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-movflags", "+faststart",
            output_mp4,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            raise RuntimeError(f"Erreur rendu vertical du clip : {res.stderr[-1000:]}")
        return output_mp4

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
        Full workflow: turns a long video (local file path or YouTube URL) into `num_clips` vertical 9:16 shorts.
        """
        batch_id = f"cut_{int(time.time())}_{uuid.uuid4().hex[:5]}"
        work_dir = DOWNLOADS_DIR / batch_id
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. Resolve source (URL vs local file)
        if source.startswith(("http://", "https://")):
            print(f"\n[1/4] 📥 Téléchargement de la vidéo source ({source})...")
            dl = CompetitorScraper.download_video(source, output_id=batch_id, extract_frames=False)
            video_path = dl["video_path"]
            audio_path = dl["audio_path"]
            source_title = dl["metadata"].get("title", "Vidéo importée")
        else:
            p = Path(source).expanduser().resolve()
            if not p.exists():
                raise FileNotFoundError(f"Fichier vidéo introuvable : {source}")
            video_path = str(p)
            source_title = p.stem
            print(f"\n[1/4] 🎞️ Extraction audio de la vidéo locale ({p.name})...")
            audio_path = cls._extract_audio_wav(video_path, work_dir / "source_audio.wav")

        total_duration = VideoComposer.get_media_duration(video_path)

        # 2. Transcribe with word-level timestamps
        print(f"\n[2/4] 🎙️ Transcription mot-par-mot ({total_duration:.1f}s)...")
        transcript = AudioTranscriber.transcribe(audio_path, language=language)

        # 3. Select viral moments using LeMonteur
        print(f"\n[3/4] 🧠 Sélection des {num_clips} meilleurs passages par Le Monteur...")
        if total_duration <= 62.0:
            raw_clips = [{
                "start_sec": 0.0,
                "end_sec": round(total_duration, 2),
                "title": source_title[:60],
                "hook_screen_text": source_title.upper()[:28],
                "viral_score": 9.0,
                "reason": "Vidéo déjà au format court — recadrage 9:16 et sous-titres Submagic appliqués.",
            }]
        else:
            raw_clips = LeMonteur.find_best_clips(transcript.get("segments", []), num_clips=num_clips)

        # Sanitize clip ranges
        valid_clips: List[Dict[str, Any]] = []
        for idx, c in enumerate(raw_clips[:num_clips]):
            try:
                s = max(0.0, float(c.get("start_sec", 0.0)))
                e = min(total_duration, float(c.get("end_sec", s + 35.0)))
                if e - s < 5.0:
                    e = min(total_duration, s + 30.0)
                if e - s >= 4.0:
                    valid_clips.append({
                        "start_sec": round(s, 2),
                        "end_sec": round(e, 2),
                        "title": str(c.get("title") or f"{source_title} — Extrait #{idx + 1}"),
                        "hook_screen_text": str(c.get("hook_screen_text") or f"EXTRAIT #{idx + 1}"),
                        "viral_score": c.get("viral_score", 8.8),
                        "reason": str(c.get("reason", "Extrait sélectionné par Le Monteur")),
                    })
            except Exception:
                continue

        if not valid_clips:
            valid_clips = [{
                "start_sec": 0.0,
                "end_sec": round(min(total_duration, 45.0), 2),
                "title": f"{source_title} — Extrait #1",
                "hook_screen_text": "À VOIR ABSOLUMENT",
                "viral_score": 8.5,
                "reason": "Découpe automatique de secours.",
            }]

        # 4. Cut, optionally remove silences, and render each vertical short
        print(f"\n[4/4] ✂️ Montage et rendu 1080x1920 de {len(valid_clips)} short(s)...")
        produced_shorts: List[Dict[str, Any]] = []

        for idx, clip in enumerate(valid_clips, start=1):
            session_id = f"{batch_id}_clip{idx}"
            out_dir = RENDERS_DIR / session_id
            out_dir.mkdir(parents=True, exist_ok=True)

            raw_cut = out_dir / "raw_cut.mp4"
            ass_path = out_dir / "subtitles.ass"
            final_mp4 = out_dir / "final_short.mp4"

            start_s = clip["start_sec"]
            end_s = clip["end_sec"]
            clip_dur = max(1.0, end_s - start_s)

            # Frame-accurate trim
            cmd_trim = [
                FFMPEG_PATH,
                "-y",
                "-ss", f"{start_s:.2f}",
                "-i", video_path,
                "-t", f"{clip_dur:.2f}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                str(raw_cut),
            ]
            subprocess.run(cmd_trim, check=True, capture_output=True, timeout=300)

            active_clip_path = str(raw_cut)
            if remove_silences:
                jc_path = out_dir / "jumpcut.mp4"
                active_clip_path = cls._remove_silences_jumpcut(str(raw_cut), str(jc_path), clip_dur)
                actual_dur = VideoComposer.get_media_duration(active_clip_path)
                # Re-transcribe jump-cut audio so word timestamps remain 100% locked
                jc_wav = out_dir / "jc_audio.wav"
                cls._extract_audio_wav(active_clip_path, jc_wav)
                jc_transcript = AudioTranscriber.transcribe(str(jc_wav), language=language)
                clip_words = VideoComposer._extract_word_list(jc_transcript, "", actual_dur)
            else:
                actual_dur = VideoComposer.get_media_duration(active_clip_path)
                clip_words = cls._slice_words_for_clip(transcript, start_s, end_s)

            # Generate Submagic word-by-word ASS subtitles + Hook
            VideoComposer.generate_ass_subtitles(
                words=clip_words,
                output_ass_path=str(ass_path),
                style_name=subtitle_style,
                hook_text=clip["hook_screen_text"],
                hook_duration=min(3.4, actual_dur * 0.45),
                keywords=classify_keywords({"hook_screen_text": clip["hook_screen_text"]}, clip_words),
            )

            # Render final 1080x1920 vertical video
            cls._render_vertical_clip(
                clip_source=active_clip_path,
                output_mp4=str(final_mp4),
                ass_path=str(ass_path),
                duration=actual_dur,
                crop_mode=crop_mode,
                subtitle_style=subtitle_style,
            )

            # Clean temporary intermediate files
            for tmp_file in [raw_cut, out_dir / "jumpcut.mp4", out_dir / "jc_audio.wav"]:
                if tmp_file.exists():
                    try:
                        tmp_file.unlink()
                    except Exception:
                        pass

            clip_meta = {
                "session_id": session_id,
                "type": "monteur_cut",
                "source": source,
                "start_sec": start_s,
                "end_sec": end_s,
                "duration": round(actual_dur, 2),
                "crop_mode": crop_mode,
                "subtitle_style": subtitle_style,
                "remove_silences": remove_silences,
                "script": {
                    "title": clip["title"],
                    "hook_screen_text": clip["hook_screen_text"],
                    "hook_spoken": clip["reason"],
                },
                "video_path": str(final_mp4),
                "audit": {
                    "score_global": f"{clip['viral_score']}/10",
                    "decision": "VALIDE",
                    "points_forts": [clip["reason"]],
                },
            }
            with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(clip_meta, f, indent=2, ensure_ascii=False)

            produced_shorts.append(clip_meta)

        return {
            "batch_id": batch_id,
            "source_title": source_title,
            "total_duration": round(total_duration, 2),
            "clips_count": len(produced_shorts),
            "clips": produced_shorts,
        }
