import logging
import os
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import FFMPEG_PATH
from core import production_method as pm

logger = logging.getLogger("SoundDesigner")


def get_wav_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 24000
            return max(1.0, frames / float(rate))
    except Exception:
        return 45.0


# ---------------------------------------------------------------------------
# Musique d'ambiance générée par code (aucun Content ID) : une progression d'accords par ambiance
# ---------------------------------------------------------------------------
MUSIC_PRESETS: Dict[str, Dict[str, Any]] = {
    # Ré mineur + seconde mineure ré–mi bémol en ostinato grave (méthode Horreur)
    "dark": {
        "bar": 4.0,
        "chords": [(73.42, 110.0, 174.61), (58.27, 116.54, 146.83), (98.0, 146.83, 116.54), (110.0, 138.59, 164.81)],
        "extra": "0.10*sin(2*PI*(36.71*lt(mod(t,2),1)+38.89*gte(mod(t,2),1))*t)*exp(-3*mod(t,1))",
        "lowpass": 1100,
    },
    # La mineur, pulsation 112 bpm (méthode « Instance »)
    "tension": {
        "bar": 2.1429,
        "chords": [(110.0, 130.81, 164.81), (87.31, 130.81, 174.61), (65.41, 130.81, 164.81), (82.41, 123.47, 207.65)],
        "extra": "0.16*sin(2*PI*55*t)*exp(-14*mod(t,0.5357))*(1-exp(-300*mod(t,0.5357)))",
        "lowpass": 1500,
    },
    # Do majeur I–V–vi–IV + arpège pincé 120 bpm
    "upbeat": {
        "bar": 2.0,
        "chords": [(130.81, 164.81, 196.0), (98.0, 123.47, 146.83), (110.0, 130.81, 164.81), (87.31, 110.0, 130.81)],
        "arp": True,
        "lowpass": 3200,
    },
    # Fa majeur doux, nappes lentes
    "calm": {
        "bar": 4.0,
        "chords": [(87.31, 130.81, 164.81), (73.42, 110.0, 174.61), (58.27, 87.31, 146.83), (65.41, 98.0, 164.81)],
        "lowpass": 2000,
    },
}


def _music_expr(mood: str) -> Tuple[str, int]:
    p = MUSIC_PRESETS.get(mood, MUSIC_PRESETS["calm"])
    bar = float(p["bar"])
    chords = p["chords"]
    n = len(chords)
    k = f"floor(mod(t,{bar * n:.4f})/{bar:.4f})"
    env = f"pow(sin(PI*mod(t,{bar:.4f})/{bar:.4f}),0.5)"
    amps = (0.40, 0.27, 0.18)
    parts = []
    for j in range(3):
        f = "+".join(f"{c[j]}*eq({k},{i})" for i, c in enumerate(chords))
        parts.append(f"{amps[j]}*sin(2*PI*({f})*t)")
    expr = f"({'+'.join(parts)})*{env}"
    if p.get("arp"):
        step = bar / 8.0
        idx = f"mod(floor(t/{step:.4f}),3)"
        tones = []
        for j in range(3):
            f = "+".join(f"{c[j] * 4}*eq({k},{i})" for i, c in enumerate(chords))
            tones.append(f"({f})*eq({idx},{j})")
        ph = f"mod(t,{step:.4f})"
        expr += f"+0.16*sin(2*PI*({'+'.join(tones)})*t)*exp(-9*{ph})*(1-exp(-250*{ph}))"
    if p.get("extra"):
        expr += "+" + p["extra"]
    return expr, int(p.get("lowpass", 1800))


# ---------------------------------------------------------------------------
# Bibliothèque de bruitages synthétisés (méthode : chaque son est un événement ancré)
# (source lavfi, filtres) — tous normalisés ~0.9 crête, le volume vient du plan (dB)
# ---------------------------------------------------------------------------
def _ping(f: float, k: float, a: float = 0.4, dec: float = 30.0) -> str:
    return f"gte(t,{k})*{a}*sin(2*PI*{f}*(t-{k}))*exp(-{dec}*(t-{k}))"


SFX_LIBRARY: Dict[str, Tuple[str, str]] = {
    "whoosh": ("anoisesrc=d=0.75:c=pink:r=44100:a=0.9", "highpass=f=350,lowpass=f=3200,afade=t=in:d=0.4:curve=exp,afade=t=out:st=0.4:d=0.35"),
    "hush": ("anoisesrc=d=0.9:c=white:r=44100:a=0.5", "highpass=f=2800,afade=t=in:d=0.3,afade=t=out:st=0.4:d=0.5"),
    "impact": ("aevalsrc='0.9*sin(2*PI*(48+110*exp(-14*t))*t)*exp(-4.5*t)':d=1.4:s=44100", "lowpass=f=900"),
    "drop": ("aevalsrc='0.95*sin(2*PI*(70*exp(-1.2*t)+28)*t)*exp(-1.8*t)':d=2.2:s=44100", "lowpass=f=600"),
    "coins": ("aevalsrc='" + "+".join([_ping(2960, 0), _ping(3520, 0.06), _ping(4180, 0.13), _ping(3300, 0.21)]) + "':d=0.6:s=44100", "highpass=f=1500"),
    "ding": ("aevalsrc='0.6*sin(2*PI*1568*t)*exp(-5*t)+0.25*sin(2*PI*3136*t)*exp(-8*t)':d=1.1:s=44100", "anull"),
    "knock": ("aevalsrc='0.9*sin(2*PI*120*t)*exp(-45*t)+" + _ping(115, 0.2, 0.8, 45) + "':d=0.55:s=44100", "lowpass=f=700"),
    "creak": ("aevalsrc='0.5*sin(2*PI*(180+70*sin(2*PI*9*t))*t)*sin(PI*t)+0.25*sin(2*PI*(360+140*sin(2*PI*9*t))*t)*sin(PI*t)':d=1.0:s=44100", "bandpass=f=500:w=600"),
    "pop": ("aevalsrc='0.8*sin(2*PI*(520+1100*exp(-35*t))*t)*exp(-22*t)':d=0.3:s=44100", "anull"),
    "chime": ("aevalsrc='" + "+".join([_ping(1046.5, 0, 0.35, 3.5), _ping(1318.5, 0.12, 0.3, 3.5), _ping(1568, 0.24, 0.3, 3.5)]) + "':d=1.6:s=44100", "anull"),
    "heartbeat": ("aevalsrc='0.9*sin(2*PI*52*t)*exp(-16*t)+" + _ping(48, 0.3, 0.7, 16) + "':d=0.9:s=44100", "lowpass=f=300"),
}


class SoundDesigner:
    """
    Générateur et mixeur audio local (100% FFmpeg, 0 clé API) appliquant la méthode Clipoa :
    - Musique d'ambiance par ambiance (sombre / tension / dynamique / calme), à -16..-18 dB, qui
      s'efface sous la voix (sidechain) et se COUPE juste avant le twist (silence franc).
    - Bruitages ancrés sur des événements du plan (hook, coupes espacées, mots, twist, CTA), <= 20.
    - Version « sans musique » (voix + bruitages) produite en même temps.
    """

    @classmethod
    def _fallback_plan(cls, voice_wav: str, spoken_script: str, title: str, shots: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        dur = get_wav_duration(voice_wav)
        toks = (spoken_script or "").split()
        step = max(0.12, (dur - 0.3) / max(1, len(toks)))
        words = [{"word": w, "start": round(i * step, 2), "end": round((i + 1) * step, 2)} for i, w in enumerate(toks)]
        return pm.build_plan({"title": title, "full_spoken_script": spoken_script}, words, dur, shots)

    @classmethod
    def _build_cmd(
        cls,
        voice_wav: str,
        output_wav: str,
        plan: Dict[str, Any],
        dur: float,
        enable_music: bool,
        enable_sfx: bool,
    ) -> List[str]:
        mood = plan.get("mood") or "calm"
        dark = pm.is_dark_mood(mood)
        twist_t = plan.get("twist_t")
        music_cfg = plan.get("music") or {}
        fade_out = max(0.5, dur - 1.8)

        inputs: List[str] = ["-i", voice_wav]
        parts: List[str] = []
        idx = 1
        n_sc = (1 if enable_music else 0) + (1 if (enable_music and dark) else 0)

        voice_chain = (
            "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "highpass=f=80,equalizer=f=3200:t=q:w=1.0:g=2.5,"
            "acompressor=threshold=-20dB:ratio=2.5:attack=12:release=140:makeup=1.4"
        )
        if n_sc:
            outs = "[vmix]" + "".join(f"[vsc{i}]" for i in range(n_sc))
            parts.append(f"{voice_chain},asplit={n_sc + 1}{outs}")
        else:
            parts.append(f"{voice_chain}[vmix]")
        mix = ["[vmix]"]
        sc_i = 0

        if enable_music:
            expr, lp = _music_expr(mood)
            inputs += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", f"aevalsrc='{expr}':s=44100"]
            cut = ""
            cut_len = float(music_cfg.get("cut_before_twist_s") or 0.0)
            if twist_t is not None and cut_len > 0:
                a, b = max(0.0, float(twist_t) - cut_len), float(twist_t) + 0.15
                cut = f",volume=enable='between(t,{a:.2f},{b:.2f})':volume=0"
            parts.append(
                f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,lowpass=f={lp},"
                "aecho=0.8:0.8:70|140:0.25|0.15,"
                f"afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out:.2f}:d=1.6,"
                f"volume={float(music_cfg.get('db', -17.0)):.1f}dB{cut}[mus_raw]"
            )
            parts.append(f"[mus_raw][vsc{sc_i}]sidechaincompress=threshold=0.05:ratio=3:attack=25:release=420[mus]")
            sc_i += 1
            mix.append("[mus]")
            idx += 1

            if dark:
                # Nappe d'air / vent / salle, très basse et ducked
                inputs += ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anoisesrc=c=pink:r=44100:a=0.5"]
                parts.append(
                    f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,bandpass=f=420:width_type=h:w=500,"
                    f"afade=t=in:st=0:d=1.5,afade=t=out:st={fade_out:.2f}:d=1.6,volume=-27dB[amb_raw]"
                )
                parts.append(f"[amb_raw][vsc{sc_i}]sidechaincompress=threshold=0.04:ratio=3:attack=30:release=500[amb]")
                sc_i += 1
                mix.append("[amb]")
                idx += 1

        if enable_sfx:
            labels = []
            for e_i, ev in enumerate(plan.get("sfx") or []):
                src = SFX_LIBRARY.get(str(ev.get("kind")))
                if not src:
                    continue
                at = float(ev.get("at", 0.0))
                if at >= dur - 0.15:
                    continue
                ms = int(round(at * 1000))
                inputs += ["-f", "lavfi", "-i", src[0]]
                parts.append(
                    f"[{idx}:a]{src[1]},aformat=sample_rates=44100:channel_layouts=stereo,"
                    f"volume={float(ev.get('db', -14.0)):.1f}dB,adelay=delays={ms}:all=1[s{e_i}]"
                )
                labels.append(f"[s{e_i}]")
                idx += 1
            if len(labels) == 1:
                mix.append(labels[0])
            elif labels:
                parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[sfxbus]")
                mix.append("[sfxbus]")

        if len(mix) == 1:
            parts.append("[vmix]alimiter=limit=0.95:level=0[outa]")
        else:
            parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:dropout_transition=2:normalize=0,alimiter=limit=0.95:level=0[outa]")

        return [
            FFMPEG_PATH, "-y", *inputs,
            "-filter_complex", ";".join(parts),
            "-map", "[outa]", "-c:a", "pcm_s16le", "-ar", "44100", "-t", f"{dur:.2f}",
            output_wav,
        ]

    @staticmethod
    def tighten_voice(voice_wav: str, tempo: float = 1.0, trim_silence: bool = True) -> bool:
        """
        Narration dense (réf. Stickman : ~3,7 mots/s, presque sans pause) : raccourcit les silences de plus de
        0,18 s (on en garde 0,12 s pour ne jamais couper un mot) puis accélère la voix sans changer sa hauteur.
        Remplace le WAV sur place ; renvoie False (voix intacte) si FFmpeg échoue.
        """
        tempo = max(0.8, min(1.4, float(tempo or 1.0)))
        filters = []
        if trim_silence:
            filters.append("silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:"
                           "stop_duration=0.18:stop_threshold=-42dB:stop_silence=0.12")
        if abs(tempo - 1.0) > 0.01:
            filters.append(f"atempo={tempo:.3f}")
        if not filters or not os.path.exists(voice_wav):
            return False
        tmp = voice_wav + ".tight.wav"
        try:
            r = subprocess.run([FFMPEG_PATH, "-y", "-i", voice_wav, "-af", ",".join(filters), tmp],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0 or not os.path.exists(tmp) or get_wav_duration(tmp) < 0.5:
                logger.warning(f"tighten_voice ignoré : {r.stderr[-300:] if r.stderr else 'sortie vide'}")
                return False
            os.replace(tmp, voice_wav)
            return True
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    @classmethod
    def _run(cls, cmd: List[str], output_wav: str) -> bool:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
            if res.returncode == 0 and os.path.exists(output_wav) and os.path.getsize(output_wav) > 1000:
                return True
            logger.warning(f"SoundDesigner mix failed: {res.stderr[-400:]}")
        except Exception as e:
            logger.warning(f"SoundDesigner error: {e}")
        return False

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
        plan: Optional[Dict[str, Any]] = None,
        output_no_music_wav: Optional[str] = None,
    ) -> str:
        """
        Mixe voix + musique + bruitages selon le plan de production. Renvoie le WAV mixé
        (ou la voix seule si le mix échoue). Si `output_no_music_wav` est fourni, écrit aussi
        la version sans musique (voix + bruitages).
        """
        if not enable_music and not enable_sfx:
            return voice_wav
        if not os.path.exists(voice_wav):
            return voice_wav
        dur = get_wav_duration(voice_wav)
        if not plan:
            plan = cls._fallback_plan(voice_wav, spoken_script, title, shots)

        ok = cls._run(cls._build_cmd(voice_wav, output_wav, plan, dur, enable_music, enable_sfx), output_wav)
        if output_no_music_wav and enable_music:
            cls._run(cls._build_cmd(voice_wav, output_no_music_wav, plan, dur, False, True), output_no_music_wav)
        return output_wav if ok else voice_wav
