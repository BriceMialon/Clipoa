"""
Sous-titres fidèles au script : on garde les MOTS du script et on ne prend à Whisper que le CALAGE temporel.

Whisper se trompe sur les homophones (« un mètre dix » → « un maître dix », « les tables » → « l'étable »).
Le texte parlé est pourtant connu : on aligne les mots du script sur les mots transcrits (difflib, mots normalisés
sans accents ni ponctuation), puis chaque mot du script reçoit les temps du ou des mots Whisper correspondants.
- mots identiques : temps du mot Whisper ;
- bloc remplacé (homophone, nombre écrit en chiffres…) : durée du bloc Whisper répartie selon la longueur des mots ;
- mots du script absents de la transcription : placés dans le trou entre les voisins calés ;
- mots transcrits absents du script : ignorés.
Si le script ne correspond visiblement pas à l'audio (moins de 30 % de mots en commun), on garde Whisper.
"""
import difflib
import re
import unicodedata
from typing import Any, Dict, List

MIN_MATCH_RATIO = 0.30
_TAG_RE = re.compile(r"\[[^\]]*\]|<[^>]*>")  # balises ElevenLabs « [whispers] », SSML


def _norm(tok: str) -> str:
    t = unicodedata.normalize("NFKD", str(tok or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t)


def script_tokens(script_text: str) -> List[str]:
    """Mots affichables du script ; la ponctuation isolée (« — », « ... ») est collée au mot précédent."""
    text = _TAG_RE.sub(" ", str(script_text or ""))
    text = re.sub(r"[*_`#]", "", text)
    out: List[str] = []
    for raw in text.split():
        if not _norm(raw):
            if out:
                out[-1] = out[-1] + ("" if raw in "—–-" else raw)
            continue
        out.append(raw)
    return out


def _spread(tokens: List[str], start: float, end: float) -> List[Dict[str, Any]]:
    """Répartit [start, end] entre les mots, au prorata de leur longueur."""
    if not tokens:
        return []
    end = max(end, start + 0.05 * len(tokens))
    weights = [max(1, len(_norm(t))) for t in tokens]
    total = float(sum(weights))
    res, t = [], start
    for tok, w in zip(tokens, weights):
        d = (end - start) * w / total
        res.append({"word": tok, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return res


def align_script_to_words(script_text: str, whisper_words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Renvoie la liste {word, start, end} avec les mots du script et le calage de Whisper."""
    toks = script_tokens(script_text)
    if not toks or not whisper_words:
        return whisper_words
    a = [_norm(t) for t in toks]
    b = [_norm(w.get("word", "")) for w in whisper_words]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    matched = sum(bl.size for bl in sm.get_matching_blocks())
    if matched < MIN_MATCH_RATIO * max(len(a), len(b)):
        return whisper_words

    out: List[Dict[str, Any]] = []
    pending: List[str] = []  # mots du script sans équivalent transcrit, placés au prochain mot calé

    def _flush(next_start: float):
        if not pending:
            return
        prev_end = out[-1]["end"] if out else max(0.0, next_start - 0.3 * len(pending))
        out.extend(_spread(pending, prev_end, max(prev_end, next_start)))
        pending.clear()

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            _flush(float(whisper_words[j1]["start"]))
            for k in range(i2 - i1):
                w = whisper_words[j1 + k]
                out.append({"word": toks[i1 + k], "start": float(w["start"]), "end": float(w["end"])})
        elif op == "replace":
            _flush(float(whisper_words[j1]["start"]))
            out.extend(_spread(toks[i1:i2], float(whisper_words[j1]["start"]), float(whisper_words[j2 - 1]["end"])))
        elif op == "delete":  # mots du script que Whisper n'a pas transcrits
            pending.extend(toks[i1:i2])
        # « insert » : mot entendu par Whisper mais absent du script → ignoré
    if pending:
        last = out[-1]["end"] if out else float(whisper_words[0]["start"])
        tail_end = max(last + 0.3 * len(pending), float(whisper_words[-1]["end"]))
        out.extend(_spread(pending, last, tail_end))
        pending.clear()

    # temps croissants, sans chevauchement
    for k in range(1, len(out)):
        if out[k]["start"] < out[k - 1]["end"]:
            out[k]["start"] = out[k - 1]["end"]
        if out[k]["end"] < out[k]["start"]:
            out[k]["end"] = out[k]["start"] + 0.05
    return out
