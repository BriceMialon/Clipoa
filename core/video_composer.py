import subprocess
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import FFMPEG_PATH, RENDERS_DIR, DEFAULT_THEME, DEFAULT_SUBTITLE_STYLE


# ASS color format is &HAABBGGRR (Alpha, Blue, Green, Red)
SUBTITLE_STYLES: Dict[str, Dict[str, str]] = {
    "submagic_yellow": {
        "label": "Submagic Jaune",
        "active_color": "&H0000E6FF",   # #FFE600
        "base_color": "&H00FFFFFF",     # #FFFFFF
        "outline_color": "&H000A0B0F",  # Deep black
        "hook_bg": "&H002E4AFF",        # #FF4A2E (ShortCrew tomato)
        "bar_color": "#FFE600",
    },
    "shortcrew_red": {
        "label": "ShortCrew Tomate",
        "active_color": "&H002E4AFF",   # #FF4A2E
        "base_color": "&H00FFFFFF",
        "outline_color": "&H000A0B0F",
        "hook_bg": "&H002E4AFF",
        "bar_color": "#FF4A2E",
    },
    "neon_green": {
        "label": "Néon Vert",
        "active_color": "&H0088FF00",   # #00FF88
        "base_color": "&H00FFFFFF",
        "outline_color": "&H0008100C",
        "hook_bg": "&H0055AA00",
        "bar_color": "#00FF88",
    },
    "cyber_cyan": {
        "label": "Cyber Cyan",
        "active_color": "&H00FFE500",   # #00E5FF
        "base_color": "&H00FFFFFF",
        "outline_color": "&H00120A05",
        "hook_bg": "&H00B87A00",
        "bar_color": "#00E5FF",
    },
}

THEMES: Dict[str, Dict[str, str]] = {
    "dark_luxury": {
        "label": "Dark Luxury (ShortCrew)",
        "description": "Fond noir profond avec halo rouge/ambre animé et grain cinéma",
    },
    "cyber_grid": {
        "label": "Cyber Grid (Tech / IA)",
        "description": "Fond bleu nuit avec grille néon et pulsation cyan/violet",
    },
    "warm_studio": {
        "label": "Warm Studio (Business)",
        "description": "Dégradé chaud ambre & espresso avec vignettage studio",
    },
    "neon_pulse": {
        "label": "Neon Pulse (Dynamique)",
        "description": "Vague lumineuse bi-ton magenta/indigo en mouvement fluide",
    },
}


# Couleurs des mots-clés (méthode Clipoa) : jaune = noms/chiffres, rouge = danger, vert = positif
KEYWORD_COLORS: Dict[str, str] = {
    "yellow": "&H0000E6FF",  # #FFE600
    "red": "&H003C4CE7",     # #E74C3C
    "green": "&H0071CC2E",   # #2ECC71
}

LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"  # standard Shorts / TikTok / Reels


class VideoComposer:
    """
    Video rendering and composition engine (1080x1920 vertical 9:16).
    Features:
    - Word-by-word Submagic/TikTok highlighted kinetic subtitles (.ass)
    - Multi-line animated hook banner rendered natively in libass (full French accent support)
    - 4 fast animated procedural visual themes + B-roll / blurred-bg support
    - Animated retention progress bar
    """

    @classmethod
    def get_media_duration(cls, media_path: str) -> float:
        cmd = [FFMPEG_PATH, "-i", media_path, "-hide_banner"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", res.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        return 10.0

    @classmethod
    def get_audio_duration(cls, audio_path: str) -> float:
        return cls.get_media_duration(audio_path)

    @staticmethod
    def _format_ass_time(seconds: float) -> str:
        seconds = max(0.0, seconds)
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        cs = int(round((s - int(s)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h:01d}:{m:02d}:{int(s):02d}.{cs:02d}"

    @staticmethod
    def _escape_ass_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")

    @staticmethod
    def _wrap_hook_text(text: str, max_chars_per_line: int = 22) -> str:
        """Wraps hook text cleanly across up to 2-3 balanced lines using ASS \\N."""
        words = text.strip().upper().split()
        if not words:
            return ""
        lines: List[str] = []
        current: List[str] = []
        for w in words:
            candidate = " ".join(current + [w])
            if current and len(candidate) > max_chars_per_line:
                lines.append(" ".join(current))
                current = [w]
            else:
                current.append(w)
        if current:
            lines.append(" ".join(current))
        return "\\N".join(lines[:3])

    @classmethod
    def _extract_word_list(
        cls,
        transcript_data: Optional[Dict[str, Any]],
        fallback_script: str,
        duration: float
    ) -> List[Dict[str, Any]]:
        """Flattens Whisper transcript into a clean list of {word, start, end}."""
        all_words: List[Dict[str, Any]] = []
        if transcript_data and transcript_data.get("segments"):
            for seg in transcript_data["segments"]:
                words = seg.get("words") or []
                if words:
                    for w in words:
                        txt = str(w.get("word", "")).strip()
                        if txt:
                            all_words.append({
                                "word": txt,
                                "start": float(w.get("start", seg.get("start", 0.0))),
                                "end": float(w.get("end", seg.get("end", 0.5))),
                            })
                else:
                    seg_words = str(seg.get("text", "")).strip().split()
                    if seg_words:
                        seg_start = float(seg.get("start", 0.0))
                        seg_end = float(seg.get("end", seg_start + 1.0))
                        step = max(0.08, (seg_end - seg_start) / len(seg_words))
                        for idx, sw in enumerate(seg_words):
                            all_words.append({
                                "word": sw,
                                "start": seg_start + idx * step,
                                "end": seg_start + (idx + 1) * step,
                            })
        if all_words:
            all_words = cls._merge_word_fragments(all_words)
            return all_words
        if fallback_script.strip():
            raw_words = fallback_script.strip().split()
            step = max(0.12, (duration - 0.5) / max(1, len(raw_words)))
            for idx, rw in enumerate(raw_words):
                all_words.append({
                    "word": rw,
                    "start": round(idx * step, 2),
                    "end": round((idx + 1) * step, 2),
                })
        return all_words

    @staticmethod
    def _merge_word_fragments(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recolle les morceaux de Whisper : « s » + « 'est » -> « s'est », « abonne » + « -toi », « ville » + « ? »."""
        merged: List[Dict[str, Any]] = []
        for w in words:
            txt = str(w.get("word", "")).strip()
            if merged and txt and (txt[0] in "'’-" or all(ch in "?!.,;:…»" for ch in txt)):
                merged[-1] = dict(merged[-1], word=merged[-1]["word"] + txt, end=max(merged[-1]["end"], w["end"]))
            else:
                merged.append(dict(w))
        return merged

    @classmethod
    def _chunk_words(cls, words: List[Dict[str, Any]], max_words: int = 3, max_chars: int = 20) -> List[List[Dict[str, Any]]]:
        """Groups words into punchy kinetic chunks (2-3 words, breaking naturally on punctuation)."""
        chunks: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        current_len = 0

        for w in words:
            w_text = w["word"]
            w_len = len(w_text)
            should_break = (
                len(current) >= max_words
                or (current and current_len + w_len + 1 > max_chars)
            )
            if should_break:
                chunks.append(current)
                current = []
                current_len = 0

            current.append(w)
            current_len += w_len + (1 if current_len > 0 else 0)

            # Break right after strong punctuation so sentences feel crisp
            if w_text.endswith((".", "!", "?", ":")):
                chunks.append(current)
                current = []
                current_len = 0

        if current:
            chunks.append(current)
        return chunks

    @classmethod
    def generate_ass_subtitles(
        cls,
        words: List[Dict[str, Any]],
        output_ass_path: str,
        style_name: str = DEFAULT_SUBTITLE_STYLE,
        hook_text: str = "",
        hook_duration: float = 3.4,
        keywords: Optional[Dict[str, List[str]]] = None,
        notes: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Creates a Submagic/TikTok-grade Advanced SubStation Alpha (.ass) file:
        - Word-by-word color highlight + micro-pop scale animation on the active word
        - Clean multi-line animated hook banner in top safe zone (0..3.4s)
        """
        style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["submagic_yellow"])
        active_color = style["active_color"]
        base_color = style["base_color"]
        outline_color = style["outline_color"]
        hook_bg = style["hook_bg"]

        # Font fallback: Arial Black / Helvetica Neue / Arial (macOS ships all of these)
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,72,{base_color},{active_color},{outline_color},&H80000000,-1,0,0,0,100,100,1,0,1,7,3,5,70,70,0,1
Style: Hook,Arial Black,62,&H00FFFFFF,&H00FFFFFF,{hook_bg},&H0007080B,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,260,1
Style: Note,Arial Black,92,&H0000E6FF,&H0000E6FF,&H000A0B0F,&H80000000,-1,0,0,0,100,100,1,0,1,8,4,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []

        # 1. Animated Hook Overlay (Layer 1, top safe zone)
        if hook_text and hook_text.strip():
            wrapped_hook = cls._wrap_hook_text(cls._escape_ass_text(hook_text))
            hook_start = cls._format_ass_time(0.05)
            hook_end = cls._format_ass_time(hook_duration)
            hook_anim = r"{\fad(120,250)\fscx86\fscy86\t(0,180,\fscx100\fscy100)}"
            events.append(f"Dialogue: 1,{hook_start},{hook_end},Hook,,0,0,0,,{hook_anim}{wrapped_hook}")

        # 1b. Cartons de texte géants aux moments clés (méthode : « 100 € → 200 € », « ↑ LIEN EN BIO ↑ »)
        for note in (notes or []):
            try:
                n_txt = cls._wrap_hook_text(cls._escape_ass_text(str(note.get("text", ""))), 16)
                n_start = float(note.get("start", 0.0))
                n_end = float(note.get("end", n_start + 2.4))
            except (TypeError, ValueError):
                continue
            if not n_txt or n_end <= n_start:
                continue
            px, py = (note.get("pos") or [540, 400])[:2]
            n_anim = rf"{{\an5\pos({int(px)},{int(py)})\fad(90,160)\fscx70\fscy70\t(0,140,\fscx100\fscy100)}}"
            events.append(
                f"Dialogue: 2,{cls._format_ass_time(n_start)},{cls._format_ass_time(n_end)},Note,,0,0,0,,{n_anim}{n_txt}"
            )

        # Mots-clés colorés
        from core.production_method import norm_word
        kw_color: Dict[str, str] = {}
        for col in ("yellow", "green", "red"):
            for kw in ((keywords or {}).get(col) or []):
                kw_color[norm_word(kw)] = KEYWORD_COLORS[col]

        # 2. Word-by-word kinetic subtitles (Layer 0, center-lower safe zone y=1120)
        chunks = cls._chunk_words(words)
        for c_idx, chunk in enumerate(chunks):
            next_chunk_start = chunks[c_idx + 1][0]["start"] if c_idx + 1 < len(chunks) else None

            for w_idx, active_w in enumerate(chunk):
                start_t = active_w["start"]
                if w_idx + 1 < len(chunk):
                    next_w_start = chunk[w_idx + 1]["start"]
                    end_t = next_w_start if (next_w_start - active_w["end"]) < 0.45 else active_w["end"]
                else:
                    end_t = active_w["end"]
                    if next_chunk_start is not None and 0 < (next_chunk_start - end_t) < 0.25:
                        end_t = next_chunk_start

                if end_t <= start_t + 0.03:
                    end_t = start_t + 0.08

                rendered_parts: List[str] = []
                for j, item in enumerate(chunk):
                    token = cls._escape_ass_text(item["word"].upper())
                    k_col = kw_color.get(norm_word(item["word"])) if kw_color else None
                    if j == w_idx:
                        # Highlighted active word with snappy pop animation (mot-clé : sa couleur + pop plus fort)
                        pop = "126" if k_col else "118"
                        rendered_parts.append(
                            rf"{{\1c{k_col or active_color}&\fscx{pop}\fscy{pop}\t(0,85,\fscx108\fscy108)}}{token}{{\rDefault}}"
                        )
                    elif k_col:
                        rendered_parts.append(rf"{{\1c{k_col}&}}{token}{{\rDefault}}")
                    else:
                        rendered_parts.append(token)

                line_text = " ".join(rendered_parts)
                # Center-lower vertical safe zone (above TikTok/Shorts UI controls)
                pos_tag = r"{\an5\pos(540,1120)}"
                if w_idx == 0:
                    pos_tag = r"{\an5\pos(540,1120)\fscx94\fscy94\t(0,70,\fscx100\fscy100)}"

                events.append(
                    f"Dialogue: 0,{cls._format_ass_time(start_t)},{cls._format_ass_time(end_t)},Default,,0,0,0,,{pos_tag}{line_text}"
                )

        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")
        return output_ass_path

    @classmethod
    def _build_procedural_bg_filter(cls, theme: str, duration: float) -> str:
        """
        Builds a fast, silky-smooth animated 1080x1920 background filtergraph.
        Computes smooth motion gradients at 180x320 and bicubic-upscales to 1080x1920 for high FPS on CPU.
        """
        d = f"{duration:.2f}"
        if theme == "cyber_grid":
            return (
                f"color=c=#050816:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(8 + 24*exp(-((X-90-35*sin(T*0.7))^2+(Y-110-30*cos(T*0.5))^2)/4200),0,255)':"
                "g='clip(14 + 62*exp(-((X-90+40*cos(T*0.6))^2+(Y-210-30*sin(T*0.5))^2)/5200),0,255)':"
                "b='clip(32 + 115*exp(-((X-90-30*sin(T*0.5))^2+(Y-160)^2)/6800),0,255)',"
                "scale=1080:1920:flags=bicubic,"
                "drawgrid=w=90:h=90:t=1:c=#00E5FF@0.09,"
                "vignette=PI/4"
            )
        elif theme == "warm_studio":
            return (
                f"color=c=#0D0907:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(22 + 95*exp(-((X-90-28*sin(T*0.45))^2+(Y-130-22*cos(T*0.35))^2)/6500),0,255)':"
                "g='clip(13 + 48*exp(-((X-90-28*sin(T*0.45))^2+(Y-135-22*cos(T*0.35))^2)/5500),0,255)':"
                "b='clip(10 + 18*exp(-((X-90+20*cos(T*0.4))^2+(Y-220)^2)/6000),0,255)',"
                "scale=1080:1920:flags=bicubic,"
                "noise=alls=3:allf=t,"
                "vignette=PI/3.5"
            )
        elif theme == "neon_pulse":
            return (
                f"color=c=#080612:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(18 + 105*exp(-((X-50-40*sin(T*0.8))^2+(Y-100-40*cos(T*0.6))^2)/5500),0,255)':"
                "g='clip(10 + 28*exp(-((X-130+35*cos(T*0.7))^2+(Y-220+35*sin(T*0.5))^2)/5200),0,255)':"
                "b='clip(34 + 125*exp(-((X-125+35*cos(T*0.7))^2+(Y-200+35*sin(T*0.6))^2)/6200),0,255)',"
                "scale=1080:1920:flags=bicubic,"
                "vignette=PI/4"
            )
        else:
            # Default: dark_luxury (ShortCrew signature charcoal + subtle animated tomato/amber aura)
            return (
                f"color=c=#07080B:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(11 + 88*exp(-((X-90-35*sin(T*0.55))^2+(Y-120-35*cos(T*0.45))^2)/5600),0,255)':"
                "g='clip(12 + 24*exp(-((X-90-35*sin(T*0.55))^2+(Y-120-35*cos(T*0.45))^2)/4600),0,255)':"
                "b='clip(17 + 26*exp(-((X-90+30*cos(T*0.4))^2+(Y-230)^2)/6200),0,255)',"
                "scale=1080:1920:flags=bicubic,"
                "noise=alls=3:allf=t,"
                "vignette=PI/3.8"
            )

    @classmethod
    def compose_short(
        cls,
        output_name: str,
        audio_path: str,
        script_data: Dict[str, Any],
        transcript_data: Optional[Dict[str, Any]] = None,
        background_video: Optional[str] = None,
        theme: str = DEFAULT_THEME,
        subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
        crop_mode: str = "center",
        retention_boost: bool = True,
        plan: Optional[Dict[str, Any]] = None,
        audio_premixed: bool = False,
        alt_audio_path: Optional[str] = None,
    ) -> str:
        """
        `plan` (production_method) : mots-clés colorés + cartons de texte.
        `audio_premixed` : l'audio vient déjà du SoundDesigner (voix traitée + musique + SFX) -> seul le
        loudnorm -14 LUFS est appliqué (pas de double compression, pas de whoosh en double).
        `alt_audio_path` : piste « sans musique » -> écrit aussi final_short_sans_musique.mp4 (vidéo copiée).

        Generates the final 1080x1920 MP4 vertical short video with:
        - Animated procedural background OR B-roll (center crop or blurred vertical background)
        - Word-by-word Submagic-style ASS subtitles
        - Animated multi-line Hook banner (first 3.4s)
        - Smooth retention progress bar
        - Optional retention boost: subtle hook audio accent + broadcast voice compression + gentle B-roll zoom
        """
        output_dir = RENDERS_DIR / output_name
        output_dir.mkdir(parents=True, exist_ok=True)
        final_mp4 = output_dir / "final_short.mp4"
        ass_path = output_dir / "subtitles.ass"

        duration = cls.get_audio_duration(audio_path) + 0.45

        words = cls._extract_word_list(
            transcript_data=transcript_data,
            fallback_script=script_data.get("full_spoken_script", ""),
            duration=duration,
        )

        hook_text = script_data.get("hook_screen_text") or script_data.get("title", "")
        cls.generate_ass_subtitles(
            words=words,
            output_ass_path=str(ass_path),
            style_name=subtitle_style,
            hook_text=hook_text,
            hook_duration=min(3.4, duration * 0.45),
            keywords=(plan or {}).get("keywords"),
            notes=(plan or {}).get("notes"),
        )

        ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        style_cfg = SUBTITLE_STYLES.get(subtitle_style, SUBTITLE_STYLES["submagic_yellow"])
        bar_color = style_cfg["bar_color"]

        if background_video and os.path.exists(background_video):
            inputs = ["-stream_loop", "-1", "-i", background_video, "-i", audio_path]
            audio_idx = "1:a"
            # Fond basse définition (rendu Blender 540x960 @ 12 fps) : agrandissement lanczos + netteté
            bg_w = cls._probe_width(background_video)
            sharpen = ",unsharp=5:5:0.8:5:5:0.0" if 0 < bg_w < 1000 else ""
            if crop_mode == "blurred_bg":
                bg_chain = (
                    "[0:v]split=2[vbg][vfg];"
                    "[vbg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:4,eq=brightness=-0.12[bg_blur];"
                    "[vfg]scale=1080:-2:force_original_aspect_ratio=decrease[fg_sharp];"
                    "[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2,fps=30,vignette=PI/5[base]"
                )
            elif retention_boost:
                # Subtle dynamic micro-zoom (1.0 -> 1.05 oscillation) to keep visual motion alive
                bg_chain = (
                    "[0:v]scale=1160:2062:force_original_aspect_ratio=increase:flags=lanczos,"
                    "crop=1080:1920:x='(iw-1080)/2+16*sin(t*0.5)':y='(ih-1920)/2+12*cos(t*0.4)',"
                    f"fps=30{sharpen},eq=brightness=-0.05:contrast=1.06:saturation=1.05,vignette=PI/5[base]"
                )
            else:
                bg_chain = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
                    f"fps=30{sharpen},eq=brightness=-0.06:contrast=1.05,vignette=PI/5[base]"
                )
        else:
            inputs = ["-i", audio_path]
            audio_idx = "0:a"
            proc_bg = cls._build_procedural_bg_filter(theme, duration)
            bg_chain = f"{proc_bg}[base]"

        # Animated progress bar overlaid at the very top (clean 10px bar)
        bar_chain = (
            f"color=c={bar_color}:s=1080x10:d={duration:.2f}:r=30[bar];"
            f"[base][bar]overlay=x='-W+W*(t/{duration:.2f})':y=0:shortest=1,"
            f"ass='{ass_escaped}',format=yuv420p[vout]"
        )

        if audio_premixed:
            # Mix déjà fait par le SoundDesigner : on normalise seulement le volume (-14 LUFS)
            audio_chain = f"[{audio_idx}]{LOUDNORM}[aout]"
        elif retention_boost:
            # Broadcast voice clarity + subtle procedural 0.38s hook whoosh accent (100% local & royalty-free)
            audio_chain = (
                f"[{audio_idx}]highpass=f=70,acompressor=threshold=-18dB:ratio=2.4:attack=15:release=120[voice];"
                "aevalsrc=0.11*exp(-7.5*t)*sin(2*PI*(110+380*exp(-9*t))*t):d=0.38:s=44100:c=stereo[sfx];"
                f"[voice][sfx]amix=inputs=2:duration=first:normalize=0,{LOUDNORM}[aout]"
            )
        else:
            audio_chain = f"[{audio_idx}]highpass=f=70,{LOUDNORM}[aout]"
        filter_complex = f"{bg_chain};{bar_chain};{audio_chain}"
        audio_map = "[aout]"

        cmd = [
            FFMPEG_PATH,
            "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", audio_map,
            *cls.VIDEO_ENCODE_ARGS,
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-t", f"{duration:.2f}",
            "-movflags", "+faststart",
            str(final_mp4)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg compose error: {result.stderr[-1200:]}")

        if plan:
            try:
                import json as _json
                with open(output_dir / "production_plan.json", "w", encoding="utf-8") as pf:
                    _json.dump(plan, pf, indent=2, ensure_ascii=False)
            except Exception:
                pass

        if alt_audio_path and os.path.exists(alt_audio_path):
            cls.mux_alternate_audio(str(final_mp4), alt_audio_path, str(output_dir / "final_short_sans_musique.mp4"), duration)

        return str(final_mp4)

    # Encodage final : qualité supérieure (les plateformes ré-encodent, il faut leur donner une bonne source)
    VIDEO_ENCODE_ARGS = [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
        "-r", "30", "-g", "60", "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
    ]

    @classmethod
    def _probe_width(cls, media_path: str) -> int:
        try:
            res = subprocess.run([FFMPEG_PATH, "-hide_banner", "-i", media_path], capture_output=True, text=True, timeout=30)
            m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", res.stderr)
            return int(m.group(1)) if m else 0
        except Exception:
            return 0

    @classmethod
    def mux_alternate_audio(cls, video_mp4: str, audio_path: str, out_mp4: str, duration: float) -> Optional[str]:
        """Même image, autre piste audio (ex. version sans musique) : vidéo copiée, pas de ré-encodage."""
        cmd = [
            FFMPEG_PATH, "-y", "-i", video_mp4, "-i", audio_path,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-af", f"apad,{LOUDNORM}", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-t", f"{duration:.2f}", "-movflags", "+faststart", out_mp4,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return out_mp4 if res.returncode == 0 and os.path.exists(out_mp4) else None
