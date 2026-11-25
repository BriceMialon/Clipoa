import asyncio
import base64
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from config import AUDIO_DIR, FFMPEG_PATH, DEFAULT_TTS_VOICE, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
from core.settings_store import load_settings, save_settings

GEMINI_VOICES = [
    {"id": "gemini:Charon", "label": "Charon · Grave & Cinématique (Gemini 3.8 · Gratuit)"},
    {"id": "gemini:Fenrir", "label": "Fenrir · Intense & Storytelling (Gemini 3.8 · Gratuit)"},
    {"id": "gemini:Orus", "label": "Orus · Posé & Autoritaire (Gemini 3.8 · Gratuit)"},
    {"id": "gemini:Puck", "label": "Puck · Dynamique & Énergique (Gemini 3.8 · Gratuit)"},
    {"id": "gemini:Aoede", "label": "Aoede · Féminine Chaleureuse (Gemini 3.8 · Gratuit)"},
    {"id": "gemini:Kore", "label": "Kore · Féminine Naturelle (Gemini 3.8 · Gratuit)"},
]

GEMINI_TTS_CASCADE = [
    "gemini-3.8-flash-tts",
    "gemini-3.8-flash-lite-tts",
    "gemini-3.1-flash-tts-preview",
]


class VoiceEngine:
    """
    Hybrid Voice Synthesis Engine:
    1. Native ElevenLabs Account integration (real API key, live credit balance, user's cloned & library voices)
    2. Free local neural fallback via edge-tts (0 cost, unlimited)
    """

    @classmethod
    def get_elevenlabs_key(cls, override_key: Optional[str] = None) -> str:
        if override_key:
            return override_key.strip()
        settings = load_settings()
        return (settings.get("elevenlabs", {}).get("api_key") or ELEVENLABS_API_KEY or "").strip()

    @classmethod
    def get_elevenlabs_status(cls, api_key: Optional[str] = None) -> Dict[str, Any]:
        key = cls.get_elevenlabs_key(api_key)
        settings = load_settings().get("elevenlabs", {})
        if not key:
            return {
                "connected": False,
                "enabled": False,
                "tier": "",
                "character_count": 0,
                "character_limit": 0,
                "remaining_chars": 0,
                "est_videos_left": 0,
                "default_voice_id": settings.get("default_voice_id", ""),
                "model_id": settings.get("model_id", "eleven_multilingual_v2"),
                "message": "Non connecté — colle ta clé API ElevenLabs (elevenlabs.io → Profile → API Key)",
            }

        try:
            res = requests.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": key},
                timeout=12,
            )
            if res.status_code == 401:
                # Restricted ElevenLabs keys often lack `user_read` permission for /v1/user/subscription
                # even though Text-to-Speech works fine. Verify via /v1/models before rejecting.
                detail_msg = ""
                try:
                    d = res.json().get("detail")
                    detail_msg = d.get("message", "") if isinstance(d, dict) else str(d or "")
                except Exception:
                    detail_msg = res.text[:140]

                if "missing_permissions" in res.text.lower() or "user_read" in res.text.lower():
                    chk = requests.get(
                        "https://api.elevenlabs.io/v1/models",
                        headers={"xi-api-key": key},
                        timeout=10,
                    )
                    if chk.status_code == 200:
                        return {
                            "connected": True,
                            "enabled": bool(settings.get("enabled", True)),
                            "tier": "restricted_key",
                            "character_count": 0,
                            "character_limit": 0,
                            "remaining_chars": 0,
                            "used_pct": 0.0,
                            "est_videos_left": 10,
                            "default_voice_id": settings.get("default_voice_id", ""),
                            "model_id": settings.get("model_id", "eleven_multilingual_v2"),
                            "message": "Connecté (clé restreinte · TTS actif — active « User: Read » pour voir le solde)",
                        }
                return {
                    "connected": False,
                    "enabled": False,
                    "message": f"Clé ElevenLabs refusée (401) : {detail_msg or 'clé invalide, révoquée ou permissions manquantes'}",
                }
            if res.status_code != 200:
                return {
                    "connected": False,
                    "enabled": False,
                    "message": f"Clé ElevenLabs invalide ou expirée (HTTP {res.status_code})",
                }
            sub = res.json()
            used = int(sub.get("character_count", 0))
            limit = max(1, int(sub.get("character_limit", 10000)))
            remaining = max(0, limit - used)
            # ~1000 chars per 55s short
            est_videos = remaining // 1000
            return {
                "connected": True,
                "enabled": bool(settings.get("enabled", True)),
                "tier": sub.get("tier", "free"),
                "character_count": used,
                "character_limit": limit,
                "remaining_chars": remaining,
                "used_pct": min(100.0, round((used / limit) * 100.0, 1)),
                "est_videos_left": est_videos,
                "default_voice_id": settings.get("default_voice_id", ""),
                "model_id": settings.get("model_id", "eleven_multilingual_v2"),
                "message": f"Connecté ({sub.get('tier', 'free')}) · {remaining:,} crédits restants (~{est_videos} shorts)",
            }
        except Exception as e:
            return {"connected": False, "enabled": False, "message": f"Erreur connexion ElevenLabs : {e}"}

    @classmethod
    def connect_elevenlabs(
        cls,
        api_key: str,
        default_voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        enabled: bool = True
    ) -> Dict[str, Any]:
        status = cls.get_elevenlabs_status(api_key=api_key)
        if not status.get("connected"):
            return status
        payload: Dict[str, Any] = {"api_key": api_key.strip(), "enabled": enabled}
        if default_voice_id:
            payload["default_voice_id"] = default_voice_id.strip()
        if model_id:
            payload["model_id"] = model_id.strip()
        save_settings({"elevenlabs": payload})
        return cls.get_elevenlabs_status()

    @classmethod
    def list_elevenlabs_voices(cls, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
        key = cls.get_elevenlabs_key(api_key)
        if not key:
            return []
        try:
            res = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": key},
                timeout=15,
            )
            if res.status_code != 200:
                return []
            voices = []
            for v in res.json().get("voices", []):
                voices.append({
                    "voice_id": v.get("voice_id"),
                    "name": v.get("name"),
                    "category": v.get("category", "premade"),
                    "preview_url": v.get("preview_url", ""),
                })
            return voices
        except Exception:
            return []

    @classmethod
    def _pick_auto_voice_and_emotion(cls, text: str) -> Dict[str, Any]:
        """Détecte l'émotion et le style du script pour adapter automatiquement la voix et l'intonation."""
        low = (text or "").lower()
        if any(w in low for w in ("frisson", "nuit", "sombre", "mystère", "disparu", "secret", "peur", "piège", "silence", "dangereux")):
            return {
                "gemini_voice": "Charon",
                "style_prompt": "Voix grave, cinématique, mystérieuse et captivante avec des pauses dramatiques naturelles",
                "el_stability": 0.42,
                "el_style": 0.38,
            }
        if any(w in low for w in ("million", "argent", "banque", "arrete", "erreur", "choquant", "incroyable", "jamais", "scandale", "vérité")):
            return {
                "gemini_voice": "Fenrir",
                "style_prompt": "Voix intense, percutante et rythmée de créateur YouTube Shorts / TikTok, ton accrocheur et affirmé",
                "el_stability": 0.38,
                "el_style": 0.45,
            }
        if any(w in low for w in ("astuce", "comment", "étape", "méthode", "conseil", "apprendre", "explique", "guide")):
            return {
                "gemini_voice": "Orus",
                "style_prompt": "Voix posée, claire, experte et engageante avec un débit fluide et naturel",
                "el_stability": 0.55,
                "el_style": 0.25,
            }
        if any(w in low for w in ("histoire", "jour", "vie", "amour", "émotion", "rêve", "coeur", "famille")):
            return {
                "gemini_voice": "Aoede",
                "style_prompt": "Voix chaleureuse, expressive et humaine, ton storytelling intime et authentique",
                "el_stability": 0.48,
                "el_style": 0.35,
            }
        return {
            "gemini_voice": "Puck",
            "style_prompt": "Voix naturelle, vivante et dynamique de créateur vidéo moderne, rythme fluide et captivant",
            "el_stability": 0.45,
            "el_style": 0.30,
        }

    @classmethod
    def generate_voice(
        cls,
        text: str,
        output_name: str,
        voice: Optional[str] = None,
        use_elevenlabs: Optional[bool] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Synthesizes speech from text and returns paths to audio file (.wav/.mp3).
        Supports:
        - 'auto_gemini' / 'auto_el': AI selects voice & adapts emotional tone to script context
        - 'gemini:<VoiceName>': Studio-grade free Gemini 3.8 Flash TTS
        - 'el:<voice_id>': ElevenLabs API
        - 'edge:<voice_name>': Unlimited offline-style Edge-TTS fallback
        """
        if not (text or "").strip():
            raise ValueError("Le script vocal est vide — impossible de synthétiser la voix.")

        target_dir = AUDIO_DIR / output_name
        target_dir.mkdir(parents=True, exist_ok=True)
        audio_mp3 = target_dir / "speech.mp3"
        audio_wav = target_dir / "speech.wav"
        srt_path = target_dir / "subtitles.srt"

        settings = load_settings()
        el_cfg = settings.get("elevenlabs", {})
        el_key = cls.get_elevenlabs_key()
        gem_key = (settings.get("gemini", {}).get("api_key") or os.getenv("GEMINI_API_KEY") or "").strip()

        auto_profile = cls._pick_auto_voice_and_emotion(text)
        chosen_voice = (voice or "").strip()
        explicit_free = chosen_voice.startswith(("edge:", "gemini:", "fr-"))
        style_prompt = auto_profile["style_prompt"]
        el_stability = auto_profile["el_stability"]
        el_style = auto_profile["el_style"]
        provider = "gemini_tts" if gem_key else "edge_tts"

        if chosen_voice == "auto_gemini":
            provider = "gemini_tts" if gem_key else "edge_tts"
            chosen_voice = auto_profile["gemini_voice"]
        elif chosen_voice == "auto_el":
            provider = "elevenlabs" if el_key else ("gemini_tts" if gem_key else "edge_tts")
            chosen_voice = ""
        elif chosen_voice.startswith("el:"):
            provider = "elevenlabs"
            chosen_voice = chosen_voice[3:]
        elif chosen_voice.startswith("gemini:"):
            provider = "gemini_tts"
            chosen_voice = chosen_voice[7:]
        elif chosen_voice.startswith("edge:"):
            provider = "edge_tts"
            chosen_voice = chosen_voice[5:]
        elif chosen_voice.startswith("qwen:"):
            provider = "local_hd"
        elif use_elevenlabs is True and el_key:
            provider = "elevenlabs"
        elif use_elevenlabs is None and el_key and el_cfg.get("enabled", True) and not chosen_voice.startswith("fr-FR-"):
            provider = "elevenlabs"

        raw_audio_in = audio_mp3
        # Voix HD locale gratuite : utilisée dès qu'elle est installée, sauf si une autre voix gratuite est choisie
        if provider in ("gemini_tts", "edge_tts") and not explicit_free:
            try:
                from core import local_tts
                if local_tts.use_by_default():
                    provider = "local_hd"
                    chosen_voice = ""
            except Exception:
                pass
        if provider == "local_hd":
            from core import local_tts
            raw_audio_in = target_dir / "speech_raw.wav"
            try:
                local_tts.synthesize(text, raw_audio_in, voice=chosen_voice or None)
            except Exception as e:
                print(f"Voix HD locale indisponible ({e}) — bascule automatique vers Edge-TTS.")
                provider = "edge_tts"
                raw_audio_in = audio_mp3
                cls._generate_edge_tts(text, DEFAULT_TTS_VOICE, audio_mp3, srt_path)
        elif provider == "elevenlabs" and el_key:
            voice_id = chosen_voice or el_cfg.get("default_voice_id") or ELEVENLABS_VOICE_ID or ""
            el_model = model_id or el_cfg.get("model_id") or "eleven_multilingual_v2"
            try:
                cls._generate_elevenlabs(text, audio_mp3, el_key, voice_id, el_model, stability=el_stability, style=el_style)
            except Exception as e:
                print(f"ElevenLabs indisponible ({e}) — bascule vers Gemini 3.8 TTS / Edge-TTS.")
                if gem_key:
                    provider = "gemini_tts"
                    raw_audio_in = target_dir / "speech_raw.wav"
                    try:
                        cls._generate_gemini_tts(text, auto_profile["gemini_voice"], raw_audio_in, gem_key, style_prompt=style_prompt)
                    except Exception:
                        provider = "edge_tts"
                        raw_audio_in = audio_mp3
                        cls._generate_edge_tts(text, DEFAULT_TTS_VOICE, audio_mp3, srt_path)
                else:
                    provider = "edge_tts"
                    cls._generate_edge_tts(text, DEFAULT_TTS_VOICE, audio_mp3, srt_path)
        elif provider == "gemini_tts" and gem_key:
            gem_voice = chosen_voice or auto_profile["gemini_voice"]
            raw_audio_in = target_dir / "speech_raw.wav"
            try:
                cls._generate_gemini_tts(text, gem_voice, raw_audio_in, gem_key, style_prompt=style_prompt)
            except Exception as e:
                print(f"Gemini TTS indisponible ({e}) — bascule automatique vers Edge-TTS.")
                provider = "edge_tts"
                raw_audio_in = audio_mp3
                cls._generate_edge_tts(text, DEFAULT_TTS_VOICE, audio_mp3, srt_path)
        else:
            provider = "edge_tts"
            edge_voice = chosen_voice if chosen_voice.startswith("fr-") else DEFAULT_TTS_VOICE
            cls._generate_edge_tts(text, edge_voice, audio_mp3, srt_path)

        # Convert to standard 44.1kHz stereo WAV for robust video mixing
        cmd_convert = [
            FFMPEG_PATH,
            "-y",
            "-i", str(raw_audio_in),
            "-ar", "44100",
            "-ac", "2",
            str(audio_wav)
        ]
        subprocess.run(cmd_convert, check=True, capture_output=True)

        return {
            "provider": provider,
            "audio_wav": str(audio_wav),
            "audio_mp3": str(audio_mp3 if audio_mp3.exists() else audio_wav),
            "srt_path": str(srt_path) if srt_path.exists() else ""
        }

    @classmethod
    def _generate_gemini_tts(cls, text: str, voice_name: str, out_wav: Path, api_key: str, style_prompt: str = ""):
        """
        Studio-grade French TTS via Google Gemini 3.8 Flash TTS (Free Tier eligible on AI Studio).
        Handles native audio/wav as well as raw audio/l16 PCM responses.
        """
        tone = style_prompt or "Voix naturelle, expressive et captivante de créateur YouTube Shorts / TikTok"
        prompt = (
            f"Lis ce texte en français ({tone}), sans ajouter ni retirer un seul mot :\n\n"
            f"{text}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice_name}
                    }
                },
            },
        }
        last_err = ""
        for model in GEMINI_TTS_CASCADE:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            try:
                res = requests.post(url, json=payload, timeout=90)
            except requests.RequestException as e:
                last_err = str(e)
                continue
            if res.status_code == 200:
                data = res.json()
                parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                for part in parts:
                    inline = part.get("inlineData") or {}
                    b64 = inline.get("data")
                    mime = (inline.get("mimeType") or "").lower()
                    if b64:
                        raw_bytes = base64.b64decode(b64)
                        if "wav" in mime:
                            out_wav.write_bytes(raw_bytes)
                            return
                        # Raw PCM L16 24kHz mono -> wrap to WAV via FFmpeg
                        raw_pcm = out_wav.with_suffix(".pcm")
                        raw_pcm.write_bytes(raw_bytes)
                        subprocess.run(
                            [FFMPEG_PATH, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw_pcm), str(out_wav)],
                            check=True,
                            capture_output=True,
                        )
                        try:
                            raw_pcm.unlink()
                        except Exception:
                            pass
                        return
                last_err = f"Réponse audio vide ({model})"
                continue
            last_err = f"HTTP {res.status_code} ({model}): {res.text[:160]}"
            if res.status_code in (429, 404, 500, 503):
                continue
            raise RuntimeError(last_err)
        raise RuntimeError(last_err or "Gemini TTS indisponible")

    @classmethod
    def _generate_edge_tts(cls, text: str, voice: str, audio_path: Path, srt_path: Path):
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            sub_maker = edge_tts.SubMaker()
            with open(audio_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        sub_maker.feed(chunk)
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(sub_maker.get_srt())

        asyncio.run(_run())

    @classmethod
    def _generate_elevenlabs(cls, text: str, audio_path: Path, api_key: str, voice_id: str, model_id: str, stability: float = 0.45, style: float = 0.25):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.78,
                "style": style,
                "use_speaker_boost": True,
            },
        }
        res = requests.post(url, headers=headers, json=payload, timeout=90)
        if res.status_code == 200:
            with open(audio_path, "wb") as f:
                f.write(res.content)
        else:
            raise RuntimeError(f"ElevenLabs HTTP {res.status_code}: {res.text[:200]}")
