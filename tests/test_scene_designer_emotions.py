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
