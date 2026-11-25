import logging
import os
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import FFMPEG_PATH

logger = logging.getLogger("SoundDesigner")


def get_wav_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 24000
            return max(1.0, frames / float(rate))
    except Exception:
        return 45.0


class SoundDesigner:
    """
    Générateur et mixeur audio local (100% FFmpeg, 0 clé API requise) :
    - Musique d'ambiance adaptée au ton de la vidéo (mélancolie/horreur vs pop/dynamique)
    - Bruits d'ambiance et effets sonores (SFX) calés sur les transitions de plans
    """

    @classmethod
    def mix_ambient_and_sfx(
        cls,
        voice_wav: str,
        output_wav: str,
        spoken_script: str = "",
        title: str = "",
        shots: Optional[List[Dict[str, Any]]] = None,
        enable_music: bool = True,
        enable_sfx: bool = True,
    ) -> str:
        if not enable_music and not enable_sfx:
            return voice_wav
        if not os.path.exists(voice_wav):
            return voice_wav

        dur = get_wav_duration(voice_wav)
        low = f"{title} {spoken_script}".lower()
        dark_kw = ("horreur", "effray", "nuit", "soir", "dispar", "mort", "fenêtre", "fenetre", "sombre", "peur", "monstre", "seul", "neige", "glace", "triste", "miroir", "deuil")
        is_dark = any(k in low for k in dark_kw)

        fade_out = max(0.5, dur - 2.2)
        inputs = ["-i", voice_wav]
        filter_parts = [
            "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=1.05[voice]"
        ]
        mix_labels = ["[voice]"]
        idx = 1

        # 1. Musique d'ambiance adaptée au ton (pad harmonique doux sous la voix)
        if enable_music:
            if is_dark:
                # Ré mineur sombre/mélancolique (D2=73.4, A2=110, F3=174.6, D3=146.8) avec respiration lente
                expr = (
                    "0.22*sin(2*PI*73.42*t)"
                    "+0.16*sin(2*PI*110.0*t)"
                    "+0.11*sin(2*PI*146.83*t)*(0.55+0.45*sin(2*PI*0.18*t))"
                    "+0.08*sin(2*PI*174.61*t)*(0.5+0.5*sin(2*PI*0.11*t))"
                )
            else:
                # Do majeur / pop doux (C3=130.8, G3=196, E4=329.6) avec pulsation légère
                expr = (
                    "0.18*sin(2*PI*130.81*t)"
                    "+0.14*sin(2*PI*196.0*t)*(0.6+0.4*sin(2*PI*0.5*t))"
                    "+0.10*sin(2*PI*261.63*t)*(0.5+0.5*sin(2*PI*0.25*t))"
                    "+0.06*sin(2*PI*329.63*t)*(0.5+0.5*sin(2*PI*0.33*t))"
                )
            inputs.extend(["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"aevalsrc={expr}:s=44100:c=stereo"])
            filter_parts.append(
                f"[{idx}:a]lowpass=f={'950' if is_dark else '1800'},"
                f"afade=t=in:st=0:d=1.8,afade=t=out:st={fade_out:.2f}:d=2.0,"
                f"volume={'0.14' if is_dark else '0.11'}[music]"
            )
            mix_labels.append("[music]")
            idx += 1

        # 2. Bruits d'ambiance + SFX de transitions calés sur les plans
        if enable_sfx:
            # Ambiance subtile (vent d'hiver / air) + impacts doux aux cuts clés
            sfx_times = [0.25]
            if shots and len(shots) >= 3:
                step = max(1, len(shots) // 4)
                for s_i in range(step, len(shots), step):
                    t_s = float(shots[s_i].get("start_s", -1))
                    if 2.0 < t_s < dur - 2.0:
                        sfx_times.append(round(t_s, 2))
            else:
                for frac in (0.32, 0.68):
                    t_s = round(dur * frac, 2)
                    if 2.0 < t_s < dur - 2.0:
                        sfx_times.append(t_s)

            # Build gentle pulse envelopes at sfx_times on top of soft filtered noise
            pulses = "+".join(
                f"0.45*exp(-((t-{ts})/0.32)*((t-{ts})/0.32))*sin(2*PI*{'62' if is_dark else '140'}*t)"
                for ts in sfx_times[:5]
            )
            inputs.extend(["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"anoisesrc=c=pink:r=44100:a=0.06"])
            noise_idx = idx
            idx += 1
            inputs.extend(["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"aevalsrc={pulses}:s=44100:c=stereo"])
            hit_idx = idx
            idx += 1
            filter_parts.append(
                f"[{noise_idx}:a]aformat=channel_layouts=stereo,"
                f"bandpass=f={'420' if is_dark else '900'}:width_type=h:w=500,"
                f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.2f}:d=1.8,"
                f"volume={'0.18' if is_dark else '0.09'}[amb]"
            )
            filter_parts.append(f"[{hit_idx}:a]lowpass=f=600,volume=0.22[hits]")
            mix_labels.extend(["[amb]", "[hits]"])

        filter_parts.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=2:normalize=0,"
            "alimiter=limit=0.95[outa]"
        )

        cmd = [
            FFMPEG_PATH, "-y",
            *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[outa]",
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            output_wav,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode == 0 and os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000:
                return output_wav
            logger.warning(f"SoundDesigner mix failed: {res.stderr[-250:]}")
        except Exception as e:
            logger.warning(f"SoundDesigner error: {e}")
        return voice_wav
