"""Casting des voix par l'IA, script libre et barre de progression qui avance pendant les longues étapes."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestScriptFreeFormat(unittest.TestCase):
    def test_prompt_lets_ai_choose_format_but_keeps_pipeline_table(self):
        from core.script_template import build_script_generation_prompt, VIDEO_SCRIPT_TEMPLATE
        sys_p, user_p = build_script_generation_prompt("Un sketch entre deux pigeons", 45)
        self.assertIn("déduis toi-même", sys_p)
        self.assertIn("Aucune recette imposée", sys_p)
        self.assertNotIn("6 sections", sys_p)
        for needed in ("## 1. Fiche projet", "## 2. Personnages", "## 3. Le script", "| Qui parle | Texte |"):
            self.assertIn(needed, VIDEO_SCRIPT_TEMPLATE)
        self.assertNotIn("## 4.", VIDEO_SCRIPT_TEMPLATE)

    def test_style_narrative_rules_are_a_hint_not_a_mold(self):
        from core.style_plugins import StylePluginStore
        ctx = StylePluginStore.build_da_context("2d_monde_3d")
        if ctx:
            self.assertIn("pas une obligation", ctx)

    def test_scenariste_prompt_has_no_forced_recipe(self):
        from agents.prompts import PROMPT_SCENARISTE
        self.assertIn("déduis de la demande", PROMPT_SCENARISTE)
        self.assertIn('"dialogue"', PROMPT_SCENARISTE)


class TestVoiceCasting(unittest.TestCase):
    CANDS = [
        {"voice_id": "fr_m", "name": "Hugo", "gender": "male", "age": "young", "language": "fr", "use": "narrative_story", "source": "library", "public_owner_id": "o1"},
        {"voice_id": "fr_f", "name": "Léna", "gender": "female", "age": "young", "language": "fr", "use": "characters_animation", "source": "library", "public_owner_id": "o2"},
        {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George", "gender": "male", "language": "en", "use": "narration", "source": "default"},
    ]

    def _cands(self):
        out = [dict(c) for c in self.CANDS]
        for i, c in enumerate(out):
            c["ref"] = f"V{i + 1}"
        return out

    def test_speaker_key_merges_voice_off_and_on_screen(self):
        from core.voice_engine import VoiceEngine
        self.assertEqual(VoiceEngine._speaker_key("Nino (VO)"), "nino")
        self.assertEqual(VoiceEngine._speaker_key("**Nino**"), "nino")
        self.assertEqual(VoiceEngine._speaker_key("Narrateur (VO)"), "")

    def test_detect_language(self):
        from core.voice_casting import detect_language
        self.assertEqual(detect_language("Dans ma ville, tout le monde est viral, mais pas moi."), "fr")
        self.assertEqual(detect_language("In my town, everyone is famous and you are not."), "en")

    def test_ai_cast_maps_refs_and_rejects_unknown(self):
        from core import voice_casting as vc
        cands = self._cands()
        good = json.dumps({"narrator": {"voice": "V1", "stability": 0.4, "speed": 1.08},
                           "characters": {"Lila": {"voice": "V2"}, "Fantôme": {"voice": "V99"}}})
        with patch("core.claude_bridge.ClaudeBridge.query", return_value="Voici : " + good):
            r = vc.ai_cast("Nino : salut", [{"name": "Lila"}], "Stickman", "fr", cands)
        self.assertEqual(r["narrator"]["voice"]["voice_id"], "fr_m")
        self.assertEqual(r["characters"]["Lila"]["voice"]["voice_id"], "fr_f")
        self.assertNotIn("Fantôme", r["characters"])
        with patch("core.claude_bridge.ClaudeBridge.query", return_value='{"narrator": {"voice": "V42"}}'):
            self.assertIsNone(vc.ai_cast("x", [], "", "fr", cands))

    def test_settings_are_clamped(self):
        from core.voice_casting import _settings
        st = _settings({"stability": 0.05, "style": 2, "speed": 3})
        self.assertEqual(st["stability"], 0.25)
        self.assertEqual(st["style"], 0.6)
        self.assertEqual(st["speed"], 1.15)

    def test_heuristic_prefers_native_language_and_gender(self):
        from core.voice_casting import heuristic_pick
        cands = self._cands()
        self.assertEqual(heuristic_pick(cands, "fr", "une histoire")["voice_id"], "fr_m")
        self.assertEqual(heuristic_pick(cands, "fr", "une histoire", female=True)["voice_id"], "fr_f")

    def test_library_voice_added_once_then_reused(self):
        from core import voice_casting as vc
        with tempfile.TemporaryDirectory() as td:
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"voice_id": "added_1"}
            with patch.object(vc, "ADDED_FILE", Path(td) / "added.json"), patch.object(vc, "library_add_allowed", return_value=True), \
                 patch("core.voice_casting.requests.post", return_value=resp) as post:
                self.assertEqual(vc.resolve_voice_id("k", dict(self.CANDS[0])), "added_1")
                self.assertEqual(vc.resolve_voice_id("k", dict(self.CANDS[0])), "added_1")
                self.assertEqual(post.call_count, 1)
            self.assertEqual(vc.resolve_voice_id("k", dict(self.CANDS[2])), "JBFqnCBsd6RMkjVDRZzb")

    def test_cast_voices_falls_back_without_ai(self):
        from core import voice_casting as vc
        sub = MagicMock(status_code=200)
        sub.json.return_value = {"tier": "creator"}
        with patch("core.voice_casting.requests.get", return_value=sub), \
             patch.object(vc, "build_candidates", return_value=self._cands()), \
             patch.object(vc, "ai_cast", return_value=None), \
             patch.object(vc, "resolve_voice_id", side_effect=lambda k, v: v["voice_id"]):
            r = vc.cast_voices("k", "Dans ma ville, une histoire de nuit.", [{"key": "lila", "name": "Lila", "female": True}])
        self.assertEqual(r["narrator"]["voice_id"], "fr_m")
        self.assertEqual(r["characters"]["lila"]["voice_id"], "fr_f")
        self.assertFalse(r["by_ai"])

    def test_generate_voice_auto_el_uses_cast_voice_and_settings(self):
        from core.voice_engine import VoiceEngine
        cast = {"narrator": {"voice_id": "fr_m", "name": "Hugo", "settings": {"stability": 0.35, "style": 0.3, "speed": 1.08, "similarity_boost": 0.78}},
                "characters": {}}
        with tempfile.TemporaryDirectory() as td, \
             patch("core.voice_engine.AUDIO_DIR", Path(td)), \
             patch.object(VoiceEngine, "get_elevenlabs_key", return_value="k"), \
             patch.object(VoiceEngine, "_cast_voices", return_value=cast), \
             patch.object(VoiceEngine, "_generate_elevenlabs") as gen, \
             patch("core.voice_engine.subprocess.run"):
            out = VoiceEngine.generate_voice("Bonjour à tous.", "t1", voice="auto_el")
        args, kwargs = gen.call_args
        self.assertEqual(args[3], "fr_m")
        self.assertEqual(kwargs["settings"]["speed"], 1.08)
        self.assertEqual(out["provider"], "elevenlabs")
        self.assertIn("casting", out)


class TestProgressTicker(unittest.TestCase):
    def test_eased_never_reaches_end(self):
        from core.progress_ticker import eased
        self.assertEqual(eased(60, 86, 0, 100), 60)
        vals = [eased(60, 86, t, 100) for t in (10, 50, 100, 300, 10000)]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual(vals[-1], 85)

    def test_monotone_and_ticks_during_long_step(self):
        from core.progress_ticker import MonotoneProgress, ticking
        seen = []
        prog = MonotoneProgress(lambda p, m: seen.append((p, m)))
        prog(50, "a")
        prog(40, "b")
        self.assertEqual(seen[-1][0], 50)
        with ticking(prog, 61, 86, 0.2, "Rendu", every=0.03):
            time.sleep(0.25)
        ticks = [p for p, m in seen if m.startswith("Rendu ·")]
        self.assertGreaterEqual(len(ticks), 3)
        self.assertGreater(ticks[-1], 61)
        self.assertLess(ticks[-1], 86)

    def test_ticker_stays_quiet_while_step_reports_itself(self):
        from core.progress_ticker import MonotoneProgress, ticking
        seen = []
        prog = MonotoneProgress(lambda p, m: seen.append((p, m)))
        with ticking(prog, 61, 86, 1, "Rendu", every=0.03, quiet_after=5):
            prog(70, "image 100/500")
            time.sleep(0.2)
        self.assertFalse([m for p, m in seen if m.startswith("Rendu ·") and p >= 70])

    def test_blender_frame_signal_is_valid_python(self):
        from core.blender_engine import BlenderEngine
        compile(BlenderEngine.FRAME_SIGNAL_EXPR, "<expr>", "exec")
        self.assertIn("flush=True", BlenderEngine.FRAME_SIGNAL_EXPR)


if __name__ == "__main__":
    unittest.main()
