"""Accroches qui ne se répètent pas, durée calée sur le débit réel, casting des voix par emploi (27/11/2026)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import speech_rate, voice_casting  # noqa: E402
from core import script_template as st  # noqa: E402
from core import style_plugins as sp  # noqa: E402


class TestSpeechRate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(speech_rate, "RATE_FILE", Path(self.tmp.name) / "rate.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_default_then_learned(self):
        self.assertEqual(speech_rate.words_per_sec(), speech_rate.DEFAULT_WPS)
        speech_rate.record("elevenlabs", 161, 44.6)  # vraie mesure du dernier Stickman
        self.assertAlmostEqual(speech_rate.words_per_sec("elevenlabs"), 161 / 44.6, places=2)
        self.assertAlmostEqual(speech_rate.words_per_sec(), 161 / 44.6, places=2)
        speech_rate.record("multi:elevenlabs+edge_tts", 90, 30)
        self.assertLess(speech_rate.words_per_sec("elevenlabs"), 161 / 44.6)

    def test_aberrant_ignored(self):
        self.assertIsNone(speech_rate.record("gemini_tts", 145, 200))  # 0,7 mot/s : voix cassée
        self.assertIsNone(speech_rate.record("gemini_tts", 5, 2))
        self.assertEqual(speech_rate.words_per_sec(), speech_rate.DEFAULT_WPS)

    def test_word_range_follows_rate(self):
        slow = sp.duration_to_word_range(60, words_per_sec=2.65)
        fast = sp.duration_to_word_range(60, words_per_sec=3.4)
        self.assertEqual(fast["target_words"], 204)
        self.assertGreater(fast["min_words"], slow["max_words"])
        self.assertTrue(fast["min_words"] <= fast["target_words"] <= fast["max_words"])

    def test_fit_tempo(self):
        self.assertEqual(speech_rate.fit_tempo(58, 60), 1.0)
        self.assertEqual(speech_rate.fit_tempo(45, 60), 1.0)  # trop court : jamais ralentie
        t = speech_rate.fit_tempo(70, 60)
        self.assertGreater(t, 1.05)
        self.assertLessEqual(t, speech_rate.MAX_TOTAL_SPEEDUP)
        # déjà accélérée ×1,08 par ElevenLabs : le total reste ≤ 1,15
        self.assertLessEqual(speech_rate.fit_tempo(94, 60, 1.08) * 1.08, speech_rate.MAX_TOTAL_SPEEDUP + 1e-6)

    def test_style_tempo_capped(self):
        self.assertAlmostEqual(speech_rate.cap_style_tempo(1.12, 1.08) * 1.08, 1.15, places=2)
        self.assertEqual(speech_rate.cap_style_tempo(1.12, 1.0), 1.12)
        self.assertEqual(speech_rate.cap_style_tempo(1.0, 1.08), 1.0)


class TestOpenings(unittest.TestCase):
    RECENT = ["Dans ma ville, tout le monde devient viral.", "Dans mon village, une clochette sonne chaque nuit."]

    def test_repeated_opening(self):
        self.assertTrue(st.repeated_opening("Dans ma ville, on couvre les miroirs. Sauf moi.", self.RECENT))
        self.assertTrue(st.repeated_opening("Dans cette ville, les chats votent.", self.RECENT))
        self.assertFalse(st.repeated_opening("Trois abonnés, dont ma mère.", self.RECENT))
        self.assertFalse(st.repeated_opening("", self.RECENT))

    def test_block_lists_openings(self):
        b = st.avoid_titles_block(["Titre"], openings=self.RECENT)
        self.assertIn("Dans mon village, une clochette", b)
        self.assertIn("Titre", b)
        self.assertEqual(st.avoid_titles_block([], openings=[]), "")

    def test_no_imposed_formula_in_styles(self):
        for txt in (sp.STYLE_BIBLE_ROBLOX_3D, sp.NARRATIVE_RULES_ROBLOX_3D, sp.NARRATIVE_RULES_2D_MONDE_3D,
                    sp.NARRATIVE_RULES_FETE_EN_FOLIE):
            self.assertNotIn("Dans ma ville", txt)
            self.assertNotIn("Ouverture obligatoire", txt)

    def test_old_installed_bible_is_migrated(self):
        upd = sp.STARTER_DEFAULT_UPDATES["roblox_3d"]["da_prompt"]
        old = "# STYLE BIBLE — « 3D Roblox » : Dans ma ville (pop) & Conte en blocs (mélancolie)\n5. **Ouverture obligatoire**"
        self.assertTrue(any(old.startswith(o[7:]) for o in upd[0]))

    def test_write_script_rewrites_repeated_hook(self):
        from agents.team import LeScenariste
        first = {"title": "T", "hook_spoken": "Dans ma ville, les chats votent.", "full_spoken_script": "Dans ma ville, les chats votent. Fin."}
        fixed = dict(first, hook_spoken="Mon chat a voté.", full_spoken_script="Mon chat a voté. Fin.")
        with patch("core.script_template.recent_video_openings", return_value=self.RECENT), \
                patch.object(LeScenariste, "revise_script", return_value=fixed) as rev:
            out = LeScenariste._ensure_new_opening(first)
        self.assertEqual(out["hook_spoken"], "Mon chat a voté.")
        rev.assert_called_once()
        with patch("core.script_template.recent_video_openings", return_value=self.RECENT), \
                patch.object(LeScenariste, "revise_script") as rev2:
            self.assertIs(LeScenariste._ensure_new_opening(fixed), fixed)
        rev2.assert_not_called()


class TestCasting(unittest.TestCase):
    ROSTER = [{"voice_id": "orionID", "name": "Orion", "roles": ["narrateur_recit"]},
              {"voice_id": "clairID", "name": "Claire", "roles": ["explication"]}]

    def test_sanitize_roster(self):
        out = voice_casting.sanitize_roster(self.ROSTER + [{"voice_id": "x", "roles": ["inconnu"]}, {"voice_id": "orionID", "roles": ["mechant"]}])
        self.assertEqual([v["voice_id"] for v in out], ["orionID", "clairID"])

    def test_accent_ranking(self):
        us = {"name": "Adam - American, Dark and Tough", "accent": "american"}
        fr = {"name": "Nicolas - Narrator", "accent": "parisian"}
        qc = {"name": "Thomas", "accent": "quebec"}
        self.assertGreater(voice_casting._accent_score(fr, "fr"), voice_casting._accent_score(qc, "fr"))
        self.assertGreater(voice_casting._accent_score(qc, "fr"), voice_casting._accent_score(us, "fr"))

    def _cands(self):
        with patch.object(voice_casting, "load_roster", return_value=self.ROSTER), \
                patch.object(voice_casting, "account_voices", return_value=[]), \
                patch.object(voice_casting, "library_voices", return_value=[
                    {"voice_id": "nico", "name": "Nicolas", "accent": "parisian", "language": "fr", "use": "narrative_story", "source": "library"}]):
            return voice_casting.build_candidates("k", "fr")

    def test_roster_first_and_described(self):
        c = self._cands()
        self.assertEqual(c[0]["voice_id"], "orionID")
        self.assertIn("VALIDÉE", voice_casting._describe(c[0]))

    def _roster_lib_candidates(self, allow_add):
        with patch.object(voice_casting, "load_roster", return_value=[{"voice_id": "nico", "name": "Nicolas", "roles": ["narrateur_energique"]}]), \
                patch.object(voice_casting, "account_voices", return_value=[]), \
                patch.object(voice_casting, "_added_ids", return_value=set()), \
                patch.object(voice_casting, "library_add_allowed", return_value=allow_add), \
                patch.object(voice_casting, "library_voices", return_value=[
                    {"voice_id": "nico", "name": "Nicolas", "public_owner_id": "own", "language": "fr", "source": "library"}]):
            return voice_casting.build_candidates("k", "fr")

    def test_roster_voice_from_library_keeps_owner(self):
        c = self._roster_lib_candidates(allow_add=True)
        self.assertEqual(c[0]["source"], "library")
        self.assertEqual(c[0]["public_owner_id"], "own")
        self.assertTrue(c[0]["validated"])

    def test_library_copy_on_account_skipped_on_free_tier(self):
        acc = [{"voice_id": "ana", "name": "ClipRoll · Anatole", "category": "professional", "source": "account", "library_copy": True},
               {"voice_id": "rog", "name": "Roger", "category": "premade", "source": "account", "library_copy": False}]
        with patch.object(voice_casting, "load_roster", return_value=[]), \
                patch.object(voice_casting, "account_voices", return_value=acc), \
                patch.object(voice_casting, "_added_ids", return_value=set()), \
                patch.object(voice_casting, "library_add_allowed", return_value=False), \
                patch.object(voice_casting, "library_voices", return_value=[]):
            free = [v["voice_id"] for v in voice_casting.build_candidates("k", "fr", free_only=True)]
            paid = [v["voice_id"] for v in voice_casting.build_candidates("k", "fr", free_only=False)]
        self.assertNotIn("ana", free)
        self.assertIn("rog", free)
        self.assertIn("ana", paid)

    def test_is_library_copy(self):
        self.assertTrue(voice_casting._is_library_copy({"sharing": {"status": "copied"}}))
        self.assertTrue(voice_casting._is_library_copy({"is_owner": False, "category": "professional"}))
        self.assertFalse(voice_casting._is_library_copy({"category": "premade"}))
        self.assertFalse(voice_casting._is_library_copy({"is_owner": True, "category": "cloned"}))

    def test_free_tier_foreign_voice_goes_to_free_french_voice(self):
        from core.voice_engine import VoiceEngine
        cast = {"narrator": {"voice_id": "rog", "name": "Roger", "foreign": True}, "characters": {}}
        with patch.object(VoiceEngine, "get_elevenlabs_key", return_value="k"), \
                patch.object(voice_casting, "is_free_tier", return_value=True):
            self.assertIn("gratuit", VoiceEngine._free_tier_foreign_note(cast))
        with patch.object(VoiceEngine, "get_elevenlabs_key", return_value="k"), \
                patch.object(voice_casting, "is_free_tier", return_value=False):
            self.assertEqual(VoiceEngine._free_tier_foreign_note(cast), "")
        self.assertEqual(VoiceEngine._free_tier_foreign_note({"narrator": {"foreign": False}}), "")

    def test_library_voice_skipped_when_add_not_allowed(self):
        c = self._roster_lib_candidates(allow_add=False)
        self.assertNotIn("nico", [v["voice_id"] for v in c])

    def test_heuristic_uses_role_not_always_orion(self):
        c = self._cands()
        story = voice_casting.heuristic_pick(c, "fr", "Une nuit, un secret.", role=voice_casting.narrator_role("Une nuit, un secret."))
        tuto = voice_casting.heuristic_pick(c, "fr", "Astuce : la méthode en 3 étapes.", role=voice_casting.narrator_role("Astuce : la méthode en 3 étapes."))
        self.assertEqual(story["name"], "Orion")
        self.assertEqual(tuto["name"], "Claire")

    def test_default_speed(self):
        with patch.object(voice_casting, "_default_speed", return_value=1.08):
            self.assertEqual(voice_casting._settings({})["speed"], 1.08)
            self.assertEqual(voice_casting._settings({"speed": 1.4})["speed"], 1.15)

    def test_library_blocked_after_refusal(self):
        with tempfile.TemporaryDirectory() as d, patch.object(voice_casting, "LIBRARY_CACHE", Path(d) / "lib.json"):
            self.assertFalse(voice_casting.library_blocked())
            voice_casting._mark_library_blocked("HTTP 402")
            self.assertTrue(voice_casting.library_blocked())
            self.assertEqual(voice_casting.library_voices("k", "fr"), [])

    def test_casting_summary_in_metadata(self):
        from core.pipeline import ShortCrewPipeline as ProductionPipeline
        res = {"provider": "elevenlabs", "casting": {"by_ai": True, "language": "fr", "narrator": {"name": "Orion", "voice_id": "o", "settings": {"speed": 1.08}}}}
        out = ProductionPipeline._casting_summary(res)
        self.assertEqual(out["narrator"]["name"], "Orion")
        self.assertEqual(ProductionPipeline._casting_summary({"provider": "edge_tts"}), {"provider": "edge_tts"})


if __name__ == "__main__":
    unittest.main()
