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
        "label": "ClipRoll Tomate",
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
    "clean_white": {
        "label": "Blanc net (contour noir)",
        "active_color": "&H00FFFFFF",   # tout blanc, comme les contes 2D × 3D de référence
        "base_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "hook_bg": "&H00241A1E",
        "bar_color": "#FFFFFF",
    },
    "warm_cream": {
        "label": "Crème chaleureux (dessin animé)",
        "active_color": "&H008AE0FF",   # #FFE08A : mot prononcé jaune crème
        "base_color": "&H00FFFFFF",
        "outline_color": "&H00202A3B",  # contour brun foncé #3B2A20
        "hook_bg": "&H00DCF4FF",
        "bar_color": "#FFE08A",
    },
    "toon_pink": {
        "label": "Dessin à compteur (blanc, mot prononcé rose)",
        "active_color": "&H008C50F0",   # #F0508C
        "base_color": "&H00FFFFFF",
        "outline_color": "&H002B2125",  # encre #25212B
        "hook_bg": "&H002B2125",
        "bar_color": "#F0508C",
    },
    "toon_yellow": {
        "label": "Parabole (blanc, mot prononcé jaune)",
        "active_color": "&H003FD2FF",   # #FFD23F
        "base_color": "&H00FFFFFF",
        "outline_color": "&H002B2125",  # encre #25212B
        "hook_bg": "&H002B2125",
        "bar_color": "#FFD23F",
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
        "label": "Dark Luxury (ClipRoll)",
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
    "cinema_gold": {
        "label": "Cinema Gold (Fête / Pop)",
        "description": "Aplats chauds saturés or/corail/turquoise, look flat vector festif",
    },
    "pop_flat": {
        "label": "Pop Flat (Cartoon clair)",
        "description": "Ciel bleu vif et formes colorées douces, look dessin animé clair",
    },
}


# Couleurs des mots-clés (méthode ClipRoll) : jaune = noms/chiffres, rouge = danger, vert = positif
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
        # « 10 M », « 100 € », « 3 ANS » : le chiffre reste collé à son unité
        glued = re.sub(r"(\d) (?=[^\W\d_]{1,4}\b|[€%$£]|\d{3}\b)", "\\1\u0001", text.strip().upper())
        words = [w.replace("\u0001", " ") for w in glued.split()]
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
        """Liste {word, start, end} : mots du script si connu, temps de Whisper."""
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
            if fallback_script.strip():
                # Mots du script (connus) + calage Whisper : évite « UN MAÎTRE DIX » pour « un mètre dix »
                from core.script_align import align_script_to_words
                all_words = align_script_to_words(fallback_script, all_words)
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
        caption_mode: str = "chunk",
        note_color: str = "",
        note_look: str = "text",
        look: str = "",
        hud: Optional[List[Dict[str, Any]]] = None,
        hud_color: str = "",
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
Style: Hud,Arial Black,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,7,56,56,150,1
Style: NoteCard,Arial Black,70,&H00202A3B,&H00202A3B,&H00DCF4FF,&H00202A3B,-1,0,0,0,100,100,1,0,3,24,0,5,60,60,0,1
Style: Cine,Montserrat Black,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,9,2,5,60,60,0,1
Style: CineKey,Luckiest Guy,118,&H0000E6FF,&H0000E6FF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,9,2,5,60,60,0,1
Style: Toon,Fredoka,90,&H00FFFFFF,&H00FFFFFF,&H002B2125,&H802B2125,-1,0,0,0,100,100,1,0,1,8,3,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events: List[str] = []
        toon = look == "toon"
        if toon:
            # « Dessin à compteur » : l'en-tête fixe (titre, règle, compteur) est déjà dessiné dans l'image
            hook_text, notes, hud = "", None, None

        # 1. Animated Hook Overlay (Layer 1, top safe zone)
        if hook_text and hook_text.strip():
            wrapped_hook = cls._wrap_hook_text(cls._escape_ass_text(hook_text))
            hook_start = cls._format_ass_time(0.05)
            hook_end = cls._format_ass_time(hook_duration)
            hook_anim = r"{\fad(120,250)\fscx86\fscy86\t(0,180,\fscx100\fscy100)}"
            events.append(f"Dialogue: 1,{hook_start},{hook_end},Hook,,0,0,0,,{hook_anim}{wrapped_hook}")

        # 1a. Compteurs permanents en haut à gauche (« ALTITUDE : 5 M »), chaque étape jusqu'à la suivante
        hx_h = str(hud_color or "#FFD23F").lstrip("#")
        hud_col = f"&H{hx_h[4:6]}{hx_h[2:4]}{hx_h[0:2]}&" if len(hx_h) == 6 else "&H3FD2FF&"
        for step in (hud or []):
            try:
                h_lines = [cls._escape_ass_text(str(x)) for x in (step.get("lines") or [])][:2]
                h_start, h_end = float(step.get("start", 0.0)), float(step.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if not h_lines or h_end <= h_start:
                continue
            body = h_lines[0] + ("\\N{\\1c" + hud_col + "}" + h_lines[1] if len(h_lines) > 1 else "")
            events.append(
                f"Dialogue: 3,{cls._format_ass_time(h_start)},{cls._format_ass_time(h_end)},Hud,,0,0,0,,{{\\an7\\pos(56,150)}}{body}"
            )

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
            n_col = ""
            hx = str(note_color or "").lstrip("#")
            if len(hx) == 6 and note_look == "card":
                n_col = rf"\1c&H{hx[4:6]}{hx[2:4]}{hx[0:2]}&"
            elif len(hx) == 6:
                # ASS = &HBBGGRR : texte de la couleur du style, contour blanc fin
                n_col = rf"\1c&H{hx[4:6]}{hx[2:4]}{hx[0:2]}&\3c&H00FFFFFF&\bord5"
            if look == "cine":
                n_col += r"\fnLuckiest Guy"
            n_anim = rf"{{\an5\pos({int(px)},{int(py)})\fad(90,160)\fscx70\fscy70\t(0,140,\fscx100\fscy100){n_col}}}"
            events.append(
                f"Dialogue: 2,{cls._format_ass_time(n_start)},{cls._format_ass_time(n_end)},{'NoteCard' if note_look == 'card' else 'Note'},,0,0,0,,{n_anim}{n_txt}"
            )

        # Mots-clés colorés
        from core.production_method import norm_word
        kw_color: Dict[str, str] = {}
        for col in ("yellow", "green", "red"):
            for kw in ((keywords or {}).get(col) or []):
                kw_color[norm_word(kw)] = KEYWORD_COLORS[col]

        # 2. Word-by-word kinetic subtitles (Layer 0, center-lower safe zone y=1120)
        # « one_word » : un seul mot à la fois au centre (DA type Fête en folie / Christophe)
        if caption_mode == "none":
            chunks = []  # style sans sous-titres (ex. Explainer 2D) : seulement les grandes étiquettes
        else:
            chunks = cls._chunk_words(words, max_words={"one_word": 1, "two_words": 2}.get(caption_mode, 3))
        if look == "cine" and chunks:
            # Vidéos de référence : UN mot à la fois, Montserrat Black 104 blanc contour 9 à y=1230 ;
            # mots-clés en MAJUSCULES Luckiest Guy 118 (jaune idée, rouge perte, vert gain), petit « pop » d'entrée.
            flat = [w for ch in cls._chunk_words(words, max_words=1) for w in ch]
            for i, w in enumerate(flat):
                st = float(w["start"])
                en = float(flat[i + 1]["start"]) if i + 1 < len(flat) and float(flat[i + 1]["start"]) - float(w["end"]) < 0.5 else float(w["end"]) + 0.12
                if en <= st + 0.05:
                    en = st + 0.12
                k_col = kw_color.get(norm_word(w["word"])) if kw_color else None
                if k_col:
                    txt = cls._escape_ass_text(w["word"].upper())
                    events.append(f"Dialogue: 0,{cls._format_ass_time(st)},{cls._format_ass_time(en)},CineKey,,0,0,0,,"
                                  rf"{{\an5\pos(540,1230)\1c{k_col}&\fscx80\fscy80\t(0,90,\fscx108\fscy108)\t(90,160,\fscx100\fscy100)}}{txt}")
                else:
                    txt = cls._escape_ass_text(w["word"])
                    events.append(f"Dialogue: 0,{cls._format_ass_time(st)},{cls._format_ass_time(en)},Cine,,0,0,0,,"
                                  rf"{{\an5\pos(540,1230)\fscx88\fscy88\t(0,80,\fscx100\fscy100)}}{txt}")
            chunks = []
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
                cy = 1500 if toon else 1120
                pos_tag = rf"{{\an5\pos(540,{cy})}}"
                if w_idx == 0:
                    pos_tag = rf"{{\an5\pos(540,{cy})\fscx94\fscy94\t(0,70,\fscx100\fscy100)}}"
                if toon:
                    line_text = line_text.replace("{\\rDefault}", "{\\rToon}")

                events.append(
                    f"Dialogue: 0,{cls._format_ass_time(start_t)},{cls._format_ass_time(end_t)},{'Toon' if toon else 'Default'},,0,0,0,,{pos_tag}{line_text}"
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
        elif theme == "cinema_gold":
            # Aplats chauds saturés (or -> corail) avec halo turquoise qui dérive : festif, lisible, flat
            return (
                f"color=c=#F4A531:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(250 - 40*(Y/320) + 5*exp(-((X-90-40*sin(T*0.6))^2+(Y-90)^2)/2500),0,255)':"
                "g='clip(178 - 90*(Y/320) + 40*exp(-((X-60+30*cos(T*0.5))^2+(Y-230-20*sin(T*0.4))^2)/3000),0,255)':"
                "b='clip(50 + 40*(Y/320) + 150*exp(-((X-60+30*cos(T*0.5))^2+(Y-230-20*sin(T*0.4))^2)/3000),0,255)',"
                "scale=1080:1920:flags=bicubic,"
                "vignette=PI/6"
            )
        elif theme == "pop_flat":
            # Ciel bleu vif + taches colorées douces qui flottent (look dessin animé clair)
            return (
                f"color=c=#4FB3FF:s=180x320:d={d}:r=30,"
                "format=rgb24,"
                "geq="
                "r='clip(70 + 40*(Y/320) + 180*exp(-((X-40-25*sin(T*0.5))^2+(Y-80)^2)/1600),0,255)':"
                "g='clip(170 + 30*(Y/320) + 60*exp(-((X-140+20*cos(T*0.45))^2+(Y-250)^2)/2200),0,255)':"
                "b='clip(255 - 70*(Y/320) - 120*exp(-((X-40-25*sin(T*0.5))^2+(Y-80)^2)/1600),0,255)',"
                "scale=1080:1920:flags=bicubic"
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
            keywords=(plan or {}).get("keywords") if ((plan or {}).get("captions") or {}).get("keyword_colors", True) else None,
            notes=(plan or {}).get("notes"),
            caption_mode=((plan or {}).get("captions") or {}).get("mode", "chunk"),
            note_color=((plan or {}).get("captions") or {}).get("note_color", ""),
            note_look=((plan or {}).get("captions") or {}).get("note_look", "text"),
            hud=(plan or {}).get("hud"),
            hud_color=(plan or {}).get("hud_color", ""),
            look=((plan or {}).get("captions") or {}).get("look", ""),
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
            # Styles clairs (Explainer, Fête en folie) : pas d'assombrissement ni de vignettage
            clean = ((plan or {}).get("grade") == "clean")
            grade = "" if clean else ",eq=brightness=-0.05:contrast=1.06:saturation=1.05,vignette=PI/5"
            if ((plan or {}).get("grade") == "glow"):
                # Stickman : halo doux (copie floutée en mode écran), sans assombrir les visages blancs
                # courbe : les têtes (gris clair du rendu Workbench) repassent en blanc pur, décor plus lumineux
                grade = (",eq=saturation=1.12,format=gbrp,curves=all='0/0 0.5/0.6 0.8/0.99 1/1',split[glw0][glw1];[glw1]scale=270:480,gblur=sigma=5,"
                         "scale=1080:1920[glw2];[glw0][glw2]blend=all_mode=screen:all_opacity=0.22,format=yuv420p")
            if crop_mode == "blurred_bg":
                bg_chain = (
                    "[0:v]split=2[vbg][vfg];"
                    "[vbg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:4,eq=brightness=-0.12[bg_blur];"
                    "[vfg]scale=1080:-2:force_original_aspect_ratio=decrease[fg_sharp];"
                    "[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2,fps=30,vignette=PI/5[base]"
                )
            elif ((plan or {}).get("captions") or {}).get("look") == "toon":
                # Dessin à compteur : le zoom de chaque image est déjà fait, pas de flottement en plus
                bg_chain = f"[0:v]scale=1080:1920:flags=lanczos,fps=30{grade}[base]"
            elif retention_boost:
                # Subtle dynamic micro-zoom (1.0 -> 1.05 oscillation) to keep visual motion alive
                bg_chain = (
                    "[0:v]scale=1160:2062:force_original_aspect_ratio=increase:flags=lanczos,"
                    "crop=1080:1920:x='(iw-1080)/2+16*sin(t*0.5)':y='(ih-1920)/2+12*cos(t*0.4)',"
                    f"fps=30{sharpen}{grade}[base]"
                )
            else:
                bg_chain = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
                    f"fps=30{sharpen}{grade}[base]"
                )
        else:
            inputs = ["-i", audio_path]
            audio_idx = "0:a"
            proc_bg = cls._build_procedural_bg_filter(theme, duration)
            bg_chain = f"{proc_bg}[base]"

        # Polices des sous-titres Ciné (téléchargées avec le moteur Ciné)
        fontsdir_opt = ""
        if ((plan or {}).get("captions") or {}).get("look") == "cine":
            try:
                from core.cine_setup import FONTS_DIR
                if FONTS_DIR.exists():
                    fd = str(FONTS_DIR).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
                    fontsdir_opt = f":fontsdir='{fd}'"
            except Exception:
                pass
        if ((plan or {}).get("captions") or {}).get("look") == "toon":
            # police Fredoka livrée dans assets/fonts ; pas de barre de progression (l'en-tête occupe le haut)
            fd = str(Path(__file__).resolve().parent.parent / "assets" / "fonts").replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            bar_chain = f"[base]ass='{ass_escaped}':fontsdir='{fd}',format=yuv420p[vout]"
        else:
            # Animated progress bar overlaid at the very top (clean 10px bar)
            bar_chain = (
                f"color=c={bar_color}:s=1080x10:d={duration:.2f}:r=30[bar];"
                f"[base][bar]overlay=x='-W+W*(t/{duration:.2f})':y=0:shortest=1,"
                f"ass='{ass_escaped}'{fontsdir_opt},format=yuv420p[vout]"
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
        "-c:v", "libx264", "-preset", "fast", "-threads", "0", "-crf", "19", "-profile:v", "high",
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
