import unittest

from core.scene_designer import CAMERAS, _sanitize, emotion_for_text, heuristic_spec


class SceneDesignerEmotionTests(unittest.TestCase):
    def test_sanitize_keeps_emotion_weather_and_new_cameras(self):
        raw = {
            "weather": "snow",
            "characters": [{"id": "hero", "model": "villageois_01"}],
            "locations": [{"id": "salon", "type": "house", "props": [{"kind": "sofa"}, {"kind": "pancakes"}, {"kind": "laser"}]}],
            "shots": [{"i": 0, "location": "salon", "camera": "face", "focus": "hero", "emotion": "cry"},
                      {"i": 1, "location": "salon", "camera": "back", "focus": "hero", "emotion": "bizarre"}],
        }
        spec = _sanitize(raw, 2)
        self.assertEqual(spec["weather"], "snow")
        self.assertEqual([p["kind"] for p in spec["locations"][0]["props"]], ["sofa", "pancakes"])
        self.assertEqual(spec["shots"][0]["emotion"], "cry")
        self.assertEqual(spec["shots"][1]["emotion"], "neutral")
        self.assertEqual(spec["shots"][0]["camera"], "face")
        self.assertIn("back", CAMERAS)

    def test_emotion_from_text(self):
        self.assertEqual(emotion_for_text("Elle s'est mise à pleurer"), "cry")
        self.assertEqual(emotion_for_text("J'avais tellement peur"), "scared")
        self.assertEqual(emotion_for_text("On a mangé"), "neutral")

    def test_heuristic_detects_snow(self):
        spec = heuristic_spec({"full_spoken_script": "Cet hiver-là, la neige recouvrait tout."},
                              {"shots": [{"index": 0, "desc": "rue sous la neige"}, {"index": 1, "desc": "elle pleure"}]}, "roblox")
        self.assertEqual(spec["weather"], "snow")
        self.assertEqual(spec["shots"][1]["emotion"], "cry")


if __name__ == "__main__":
    unittest.main()


class CineDirectorTests(unittest.TestCase):
    def test_timeline_from_whisper_words(self):
        from core.cine_director import build_timeline
        words = [{"word": "Dans", "start": 0.1, "end": 0.3}, {"word": "ma", "start": 0.3, "end": 0.5},
                 {"word": "ville,", "start": 0.5, "end": 1.0}, {"word": "tout", "start": 1.0, "end": 1.4},
                 {"word": "brille.", "start": 1.4, "end": 2.0}, {"word": "Fin.", "start": 2.2, "end": 2.6}]
        tl = build_timeline(words, 3.0)
        self.assertEqual([L["id"] for L in tl["lines"]], ["L1", "L2"])
        self.assertEqual(len(tl["lines"][0]["chunks"]), 2)
        self.assertEqual(tl["lines"][0]["start"], 0.0)
        self.assertEqual(tl["lines"][-1]["end"], 3.0)

    def test_extract_js_requires_buildshots(self):
        from core.cine_director import _extract_js
        self.assertIn("buildShots", _extract_js("```js\nexport function buildShots(ctx) { return []; }\n```"))
        with self.assertRaises(ValueError):
            _extract_js("bonjour")

    def test_cine_starter_is_heavy(self):
        from core.style_plugins import STARTER_PRODUCTION
        self.assertEqual(STARTER_PRODUCTION["roblox_cine"]["visual_style"], "cine3d")
