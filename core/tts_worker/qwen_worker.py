# -*- coding: utf-8 -*-
"""
Worker voix HD locale (Qwen3-TTS, Apache 2.0). Exécuté avec le Python isolé `venv_tts` (>= 3.10),
jamais importé par ClipRoll (dont le Python est 3.9). Entrée : un fichier JSON ; sortie : un WAV mono.

  python qwen_worker.py job.json
  job = {"text": "...", "out": "/chemin/speech.wav", "speaker": "Ryan", "instruct": "ton posé",
         "language": "French", "model": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
         "ref_audio": null, "ref_text": null}
  python qwen_worker.py --warmup [model]   # télécharge le modèle une fois
"""
import json
import re
import sys
import time

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"


def _device():
    if torch.cuda.is_available():
        return "cuda:0", torch.bfloat16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.float32
    return "cpu", torch.float32


def load(model_id):
    dev, dtype = _device()
    return Qwen3TTSModel.from_pretrained(model_id, device_map=dev, dtype=dtype, attn_implementation="sdpa")


def chunks(text, max_len=220):
    """Phrases regroupées par ~220 caractères : la prosodie reste naturelle et la mémoire stable."""
    parts = re.split(r"(?<=[.!?…])\s+", re.sub(r"\s+", " ", text.strip()))
    out, cur = [], ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > max_len:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out or [text]


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--warmup":
        mid = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
        m = load(mid)
        print(json.dumps({"ok": True, "speakers": list(m.get_supported_speakers() or []) if hasattr(m, "get_supported_speakers") else []}))
        return
    job = json.load(open(sys.argv[1], encoding="utf-8"))
    clone = bool(job.get("ref_audio"))
    model = load(job.get("model") or (CLONE_MODEL if clone else DEFAULT_MODEL))
    lang = job.get("language") or "French"
    t0 = time.time()
    pieces, sr = [], 24000
    prompt = None
    if clone:
        prompt = model.create_voice_clone_prompt(ref_audio=job["ref_audio"], ref_text=job.get("ref_text") or None,
                                                 x_vector_only_mode=not job.get("ref_text"))
    for i, txt in enumerate(chunks(job["text"])):
        if clone:
            wavs, sr = model.generate_voice_clone(text=txt, language=lang, voice_clone_prompt=prompt)
        else:
            wavs, sr = model.generate_custom_voice(text=txt, language=lang, speaker=job.get("speaker") or "Ryan",
                                                   instruct=job.get("instruct") or "")
        pieces.append(np.asarray(wavs[0], dtype=np.float32).reshape(-1))
        pieces.append(np.zeros(int(sr * 0.12), dtype=np.float32))
        print(json.dumps({"progress": i + 1}), flush=True)
    audio = np.concatenate(pieces) if pieces else np.zeros(sr, dtype=np.float32)
    peak = float(np.max(np.abs(audio)) or 1.0)
    if peak > 0.99:
        audio = audio / peak * 0.95
    sf.write(job["out"], audio, sr)
    print(json.dumps({"ok": True, "seconds": round(time.time() - t0, 1), "duration": round(len(audio) / sr, 2)}), flush=True)


if __name__ == "__main__":
    main()
