import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class TestWorkspace(unittest.TestCase):
    def test_belongs(self):
        from core import workspace as ws
        with mock.patch.object(ws, "load_settings", return_value={"workspace": {"id": "youtube:A", "legacy": "youtube:A"}}):
            self.assertTrue(ws.belongs({"account": {"id": "youtube:A"}}, "youtube:A"))
            self.assertFalse(ws.belongs({"account": {"id": "tiktok:B"}}, "youtube:A"))
            self.assertTrue(ws.belongs({}, "youtube:A"))      # anciennes vidéos → premier espace
            self.assertFalse(ws.belongs({}, "tiktok:B"))
            self.assertTrue(ws.belongs({"account": {"id": "tiktok:B"}}, None))

    def test_routes_and_header(self):
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        self.assertEqual(c.get("/api/workspace").status_code, 200)
        self.assertEqual(c.post("/api/workspace/select", json={"id": "nope:x"}).status_code, 400)
        html = c.get("/").get_data(as_text=True)
        self.assertIn('id="ws-switch"', html)
        self.assertIn('class="brand-logo"', html)
        self.assertNotIn("touche / pour écrire", html)
        self.assertNotIn("Clipoa installe et prépare", html)


class TestRemake(unittest.TestCase):
    def test_remake_request_without_clipoa_copies_style(self):
        from core import channel_stats as cs
        data = {"videos": [{"id": "abcDEF12345", "title": "Les miroirs", "url": "https://www.youtube.com/shorts/abcDEF12345",
                            "views": 10, "score": 20, "why": "accroche lente.", "next": "commencer par la peur.", "duration": 46}]}
        with mock.patch.object(cs, "load", return_value=data), mock.patch.object(cs, "render_for_video", return_value=""):
            req = cs.remake_request("abcDEF12345")
        self.assertEqual(req["route"], "/api/make-like")
        self.assertIn("accroche lente", req["payload"]["topic"])
        self.assertEqual(req["payload"]["target_duration_sec"], 46)
        with mock.patch.object(cs, "load", return_value=data):
            with self.assertRaises(ValueError):
                cs.remake_request("zzz")

    def test_remake_route_validates_id(self):
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        self.assertEqual(c.post("/api/channel-stats/!!/remake", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
