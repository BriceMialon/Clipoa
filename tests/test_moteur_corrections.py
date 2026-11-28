"""Corrections du moteur vidéo (28/11) : sous-titres = mots du script, plans bornés, voix ElevenLabs sans ajout au compte."""
import unittest
from unittest.mock import patch

from core import production_method as pm
from core import voice_casting as vc
from core.script_align import align_script_to_words
from core.video_composer import VideoComposer


def _w(words, step=0.3):
    return [{"word": w, "start": round(i * step, 2), "end": round(i * step + step - 0.05, 2)} for i, w in enumerate(words)]


class ScriptAlignTest(unittest.TestCase):
    def test_script_words_replace_whisper_mistakes(self):
        whisper = _w("il mesurait un maître dix assis sous l'étable sans bruit".split())
        out = align_script_to_words("Il mesurait un mètre dix, assis sous les tables — sans bruit.", whisper)
        self.assertEqual([x["word"] for x in out],
                         ["Il", "mesurait", "un", "mètre", "dix,", "assis", "sous", "les", "tables", "sans", "bruit."])
        for a, b in zip(out, out[1:]):
            self.assertLessEqual(a["end"], b["start"] + 1e-6)
        self.assertAlmostEqual(out[0]["start"], 0.0)
        self.assertAlmostEqual(out[-1]["end"], whisper[-1]["end"])

    def test_missing_words_are_placed(self):
        out = align_script_to_words("Le premier, Malik, file direct.", _w("le premier file direct".split()))
        self.assertEqual([x["word"] for x in out], ["Le", "premier,", "Malik,", "file", "direct."])

    def test_unrelated_script_keeps_whisper(self):
        whisper = _w("totalement autre chose ici".split())
        self.assertEqual(align_script_to_words("Bonjour à tous les amis", whisper), whisper)

    def test_audio_tags_removed(self):
        out = align_script_to_words("[whispers] Chut, écoute.", _w("chut écoute".split()))
        self.assertEqual([x["word"] for x in out], ["Chut,", "écoute."])

    def test_extract_word_list_uses_script(self):
        tr = {"segments": [{"words": _w("le troisième t-o achète".split())}]}
        w = VideoComposer._extract_word_list(tr, "Le troisième, Théo, achète", 2.0)
        self.assertEqual([x["word"] for x in w], ["Le", "troisième,", "Théo,", "achète"])


class ShotLengthTest(unittest.TestCase):
    def test_parabole_long_shot_is_split(self):
        words = _w(["mot"] * 162, 0.35)
        shots = [{"start_s": t} for t in (0, 5, 8, 11, 19.06, 26, 29, 42.58, 52.28)]
        for mn, mx in ((3.0, 6.5), (1.2, 3.0), (1.6, 4.2)):
            segs = pm.align_shots(shots, words, 56.66, min_len=mn, max_len=mx)
            lens = [s["end"] - s["start"] for s in segs]
            self.assertLessEqual(max(lens), mx + 0.01, (mn, mx, lens))
            self.assertAlmostEqual(segs[-1]["end"], 56.66, places=1)


class VoiceLibraryTest(unittest.TestCase):
    LIB = {"voice_id": "lib1", "name": "Tenko", "source": "library", "public_owner_id": "o"}

    def test_no_add_without_consent(self):
        with patch.object(vc, "library_add_allowed", return_value=False), \
             patch.object(vc, "_read_json", return_value={}), \
             patch.object(vc.requests, "post") as post:
            self.assertEqual(vc.resolve_voice_id("k", dict(self.LIB)), "")
            post.assert_not_called()

    def test_free_account_excludes_library_voices(self):
        acc = [{"voice_id": "mine", "name": "Ma voix", "category": "cloned", "source": "account"},
               {"voice_id": "lib1", "name": "Tenko", "category": "professional", "source": "account"}]
        with patch.object(vc, "account_voices", return_value=acc), \
             patch.object(vc, "library_voices", return_value=[dict(self.LIB, voice_id="lib2")]), \
             patch.object(vc, "load_roster", return_value=[]), \
             patch.object(vc, "_added_ids", return_value={"lib1"}), \
             patch.object(vc, "library_add_allowed", return_value=False):
            free = {v["voice_id"] for v in vc.build_candidates("k", "fr", free_only=True)}
            paid = {v["voice_id"] for v in vc.build_candidates("k", "fr", free_only=False)}
        self.assertIn("mine", free)
        self.assertNotIn("lib1", free)
        self.assertNotIn("lib2", free)
        self.assertIn("lib1", paid)      # déjà sur le compte payant : utilisable
        self.assertNotIn("lib2", paid)   # pas encore ajoutée : on ne l'ajoute pas sans accord

    def test_fallback_note_is_clear(self):
        from core.voice_engine import VoiceEngine
        note = VoiceEngine._el_fallback_note(RuntimeError("ElevenLabs HTTP 402: paid_plan_required"), "Tenko")
        self.assertIn("offre ElevenLabs payante", note)
        self.assertIn("Tenko", note)


if __name__ == "__main__":
    unittest.main()
