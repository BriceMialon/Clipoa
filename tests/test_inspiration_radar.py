import unittest

from core import inspiration_radar as ir


class TestInspirationRadar(unittest.TestCase):
    def test_score_rewards_views_speed_and_engagement(self):
        slow = ir.viral_score(200_000, 4_000, 100, 30)
        fast = ir.viral_score(200_000, 4_000, 100, 2)
        engaged = ir.viral_score(200_000, 30_000, 2_000, 2)
        self.assertLess(slow, fast)
        self.assertLess(fast, engaged)
        self.assertEqual(ir.viral_score(0, 0, 0, 1), 0)
        self.assertLessEqual(ir.viral_score(10**9, 10**8, 10**7, 0.5), 100)

    def test_ai_hints(self):
        self.assertTrue(ir._looks_ai({"title": "Dans ma ville… #roblox #ia", "description": "", "tags": [], "channel": ""}))
        self.assertTrue(ir._looks_ai({"title": "story", "description": "made with Kling AI", "tags": [], "channel": ""}))
        self.assertFalse(ir._looks_ai({"title": "Ma routine du matin", "description": "vlog", "tags": ["vlog"], "channel": "julie"}))

    def test_routes_and_page(self):
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        r = c.get("/api/inspiration")
        self.assertEqual(r.status_code, 200)
        self.assertIn("scanning", r.get_json())
        html = c.get("/").get_data(as_text=True)
        self.assertIn('id="insp-wall"', html)
        self.assertNotIn('id="an-engine"', html)


if __name__ == "__main__":
    unittest.main()
