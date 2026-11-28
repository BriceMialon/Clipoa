import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as clipoa_app  # noqa: E402
from core.style_plugins import StylePluginStore  # noqa: E402


class TestSecurityApp(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        clipoa_app._RATE_LIMITER.reset()
        self.client = clipoa_app.app.test_client()

    def test_dot_render_id_blocked_everywhere(self):
        self.assertFalse(clipoa_app._is_safe_id("."))
        self.assertFalse(clipoa_app._is_safe_id(".."))
        self.assertFalse(clipoa_app._is_safe_id(".hidden"))
        self.assertTrue(clipoa_app._is_safe_id("make_12345_abc"))

        self.assertEqual(self.client.delete("/api/videos/.").status_code, 400)
        self.assertEqual(self.client.delete("/api/videos/%2e").status_code, 400)
        self.assertEqual(self.client.post("/api/videos/./validate", json={}).status_code, 400)
        self.assertEqual(self.client.get("/stream/.").status_code, 400)
        self.assertEqual(self.client.get("/download/.").status_code, 400)

    def test_csrf_blocks_null_origin_and_empty_referer(self):
        r1 = self.client.post("/api/presets", json={"label": "x"}, headers={"Origin": "null"})
        self.assertEqual(r1.status_code, 403)
        r2 = self.client.post("/api/presets", json={"label": "x"}, headers={"Referer": "about:blank"})
        self.assertEqual(r2.status_code, 403)

    def test_oauth_start_requires_lan_token_and_relay_done_post_only(self):
        orig = clipoa_app._LAN_ACCESS_TOKEN
        try:
            clipoa_app._LAN_ACCESS_TOKEN = "lan-secret-xyz"
            r = self.client.get("/oauth/youtube/start", environ_base={"REMOTE_ADDR": "192.168.1.99"})
            self.assertEqual(r.status_code, 401)
            r_get = self.client.get("/oauth/youtube/relay-done?nonce=abc")
            self.assertEqual(r_get.status_code, 405)
        finally:
            clipoa_app._LAN_ACCESS_TOKEN = orig

    def test_svg_sheet_served_as_attachment_with_sandbox_csp(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td) / "plugins"
            pdir.mkdir()
            with patch("core.style_plugins.PLUGINS_DIR", pdir), patch(
                "core.style_plugins.PLUGINS_INDEX_FILE", pdir / "plugins.json"
            ):
                created = StylePluginStore.create_plugin({"name": "SvgTest", "da_prompt": "test"})
                pid = created["id"]
                svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
                up = self.client.post(
                    f"/api/plugins/{pid}/sheets",
                    data={"role": "reference", "files": (io.BytesIO(svg_bytes), "xss.svg")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(up.status_code, 200)
                fname = up.get_json()["plugin"]["model_sheets"][0]["filename"]
                res = self.client.get(f"/api/plugins/{pid}/sheets/{fname}")
                self.assertEqual(res.status_code, 200)
                self.assertIn("attachment", res.headers.get("Content-Disposition", "").lower())
                self.assertEqual(res.headers.get("Content-Security-Policy"), "sandbox")
                res.close()


if __name__ == "__main__":
    unittest.main()
