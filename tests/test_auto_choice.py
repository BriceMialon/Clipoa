import unittest

from core.auto_choice import suggest_style
from core import onboarding

PLUGINS = [
    {"id": "roblox_3d", "name": "3D Roblox"},
    {"id": "2d_monde_3d", "name": "Stickman"},
    {"id": "fete_en_folie", "name": "Fête en folie"},
    {"id": "explainer_2d", "name": "Explainer 2D pastel"},
    {"id": "conte_blocs_melancolique", "name": "Conte Blocs Mélancolique"},
    {"id": "roblox_cine", "name": "Roblox 3D Ciné", "heavy": True},
]


class AutoChoiceTest(unittest.TestCase):
    def pick(self, topic):
        return suggest_style(topic, PLUGINS)["plugin_id"]

    def test_keywords(self):
        self.assertEqual(self.pick("Pourquoi les pieuvres ont 3 cœurs"), "explainer_2d")
        self.assertEqual(self.pick("Un noob sur Roblox trouve un trésor"), "roblox_3d")
        self.assertEqual(self.pick("Mon anniversaire tourne mal"), "fete_en_folie")
        self.assertEqual(self.pick("Dans ma ville, plus t'es riche plus ta maison est haute"), "2d_monde_3d")
        self.assertEqual(self.pick("50% des gens se trompent"), "explainer_2d")

    def test_custom_style_by_name_and_default(self):
        self.assertEqual(self.pick("Un conte mélancolique"), "conte_blocs_melancolique")
        self.assertEqual(self.pick("xyz"), "2d_monde_3d")

    def test_never_heavy_and_empty(self):
        self.assertNotEqual(self.pick("roblox ciné 3d haute qualité"), "roblox_cine")
        self.assertIsNone(suggest_style("roblox", [{"id": "roblox_cine", "heavy": True}]))

    def test_next_step_publish_first_video(self):
        tools = {"tools": {k: {"ok": True} for k in ("ffmpeg", "whisper", "voice", "blender")}}
        social = {"youtube": {"short_name": "YouTube", "auto_api": True}}
        res = onboarding.compute(tools, True, 1, 0, social, {}, {"status": "done"},
                                 published_count=0, first_video="r1")
        self.assertEqual(res["next"]["action"], "publish")
        self.assertEqual(res["next"]["video"], "r1")


if __name__ == "__main__":
    unittest.main()
