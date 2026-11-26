import json
import logging
import os
import threading
from pathlib import Path
from typing import Dict, Any, List
from config import TRANSCRIPTS_DIR

logger = logging.getLogger("Transcriber")

class AudioTranscriber:
    """
    Local transcription engine using faster-whisper.
    Extracts text and exact word-level timestamps.
    """
    _model = None
    _model_lock = threading.Lock()

    @classmethod
    def get_model(cls, model_size: str = "base"):
        with cls._model_lock:
            if cls._model is None:
                from faster_whisper import WhisperModel
                logger.info(f"Loading faster-whisper model ({model_size})...")
                # device='cpu' with compute_type='int8' is ultra fast and stable on Apple Silicon
                # modèle installé par packaging/install.sh (version fixée, rangé avec ClipRoll) ; sinon téléchargement habituel
                local = os.getenv("CLIPOA_WHISPER_DIR", "")
                source = local if model_size == "base" and local and os.path.isfile(os.path.join(local, "model.bin")) else model_size
                cls._model = WhisperModel(source, device="cpu", compute_type="int8")
            return cls._model

    @classmethod
    def transcribe(cls, audio_path: str, model_size: str = "base", language: str = "fr") -> Dict[str, Any]:
        model = cls.get_model(model_size)
        
        segments, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True
        )

        full_text_list = []
        segments_data = []

        for segment in segments:
            full_text_list.append(segment.text.strip())
            words = []
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "probability": round(w.probability, 2)
                    })
            segments_data.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip(),
                "words": words
            })

        full_text = " ".join(full_text_list)
        result = {
            "language": info.language,
            "duration": round(info.duration, 2),
            "text": full_text,
            "segments": segments_data
        }

        # Cache transcript uniquely per session/folder to avoid overwriting speech_transcript.json
        p = Path(audio_path)
        audio_key = f"{p.parent.name}_{p.stem}" if p.parent.name else p.stem
        output_file = TRANSCRIPTS_DIR / f"{audio_key}_transcript.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        return result
