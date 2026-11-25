import unittest

from core import timing_tracker as tt


class TestStyleBenchmark(unittest.TestCase):
    def test_styles_have_different_estimates(self):
        est = tt.style_estimates([])
        self.assertNotEqual(est["roblox_cine"]["claude"]["sec_60s"], est["explainer_2d"]["claude"]["sec_60s"])
        self.assertLess(est["roblox_3d"]["antigravity"]["pct_60s"], est["roblox_3d"]["claude"]["pct_60s"])
        self.assertFalse(est["roblox_3d"]["claude"]["measured"])

    def test_measurements_move_the_estimate(self):
        rows = [{"key": "style:explainer_2d:claude", "normalized_60s": 100.0, "pct_60s": 1.0} for _ in range(6)]
        est = tt.style_estimates(rows)["explainer_2d"]["claude"]
        self.assertTrue(est["measured"])
        self.assertEqual(est["samples"], 6)
        self.assertLess(est["sec_60s"], 150)
        self.assertLess(est["pct_60s"], 2.0)

    def test_style_key(self):
        self.assertEqual(tt.style_key("roblox_3d"), "roblox_3d")
        self.assertEqual(tt.style_key("mon_style_copie_x"), "_copy")
        self.assertEqual(tt.style_key(""), "_motion")
        self.assertEqual(tt.style_key("roblox_3d", copied=True), "_copy")


class TestToolsSetup(unittest.TestCase):
    def test_status_lists_tools(self):
        from core import tools_setup
        st = tools_setup.status()
        for k in ("ffmpeg", "yt_dlp", "whisper", "voice", "blender"):
            self.assertIn(k, st["tools"])
        self.assertTrue(st["tools"]["ffmpeg"]["ok"])

    def test_routes(self):
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        self.assertEqual(c.get("/api/tools").status_code, 200)
        self.assertEqual(c.get("/api/channel-stats").status_code, 200)
        html = c.get("/").get_data(as_text=True)
        self.assertNotIn("Réglages avancés ▾", html)
        self.assertNotIn('class="ai-tb-status"', html)
        self.assertNotIn('id="tools-list"', html)   # carte « outils de fabrication » retirée de l'interface


if __name__ == "__main__":
    unittest.main()
