import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import analytics_engine, channel_stats, edition, inspiration_radar, settings_store  # noqa: E402
from core.code_guard import check_bpy_code  # noqa: E402
from core.drive_client import DriveClient  # noqa: E402
from core.security import (  # noqa: E402
    is_allowed_host_header,
    redact_sensitive_text,
    validate_public_http_url,
    validate_relay_url,
)
from core.vault import ENC_PREFIX  # noqa: E402


class TestSecurityCore(unittest.TestCase):
    def test_security_host_noncanonical_ips_relay_and_redaction(self):
        self.assertFalse(is_allowed_host_header(""))
        self.assertFalse(is_allowed_host_header("   "))
        self.assertTrue(is_allowed_host_header("localhost:8081"))

        for bad in (
            "http://2130706433/secret",
            "http://0x7f000001/secret",
            "http://127.1/secret",
            "http://0177.0.0.1/secret",
            "http://169.254.169.254/latest/meta-data",
        ):
            with self.subTest(url=bad):
                with self.assertRaises(ValueError):
                    validate_public_http_url(bad)

        for bad_relay in (
            "https://mybox.local/relay",
            "https://service.internal/relay",
            "http://example.com/relay",
        ):
            with self.subTest(relay=bad_relay):
                with self.assertRaises(ValueError):
                    validate_relay_url(bad_relay)

        scrubbed = redact_sensitive_text(
            "el=sk_abcdef12345678901234567890 lic=CLIPOA-AB12-CD34-EF56-GH78 ex=CLIPOA-XXXX-XXXX-XXXX"
        )
        self.assertNotIn("sk_abcdef", scrubbed)
        self.assertNotIn("CLIPOA-AB12", scrubbed)
        self.assertIn("CLIPOA-XXXX-XXXX-XXXX", scrubbed)

    def test_code_guard_blocks_aliasing_and_submodule_escapes(self):
        bad_snippets = [
            "f = open\nf('/etc/passwd')",
            "e = eval\ne('1+1')",
            "g = getattr\ng(object, '__subclasses__')",
            "getattr(*[object, '__class__'])",
            "import operator\noperator.attrgetter('__class__')(object)",
            "import numpy.ctypeslib\n",
            "from bpy.ops import wm\n",
            "import bpy\no = bpy.ops\no.wm.save_as_mainfile(filepath='/tmp/x')",
            "from math import *\n",
        ]
        for code in bad_snippets:
            with self.subTest(code=code):
                self.assertTrue(check_bpy_code(code), f"Expected rejection for: {code}")

        good_code = (
            "import bpy\nimport math\nfrom mathutils import Vector\n"
            "class Helper:\n    def __init__(self):\n        super().__init__()\n"
            "bpy.ops.mesh.primitive_cube_add(size=2)\n"
        )
        self.assertEqual(check_bpy_code(good_code), [])

    def test_settings_store_never_writes_plaintext_secrets_on_quota_or_preset(self):
        with tempfile.TemporaryDirectory() as td:
            sf = Path(td) / "settings.json"
            uf = Path(td) / "claude_usage.json"
            with patch.object(settings_store, "SETTINGS_FILE", sf), patch.object(settings_store, "CLAUDE_USAGE_FILE", uf):
                settings_store.save_settings({
                    "claude": {"api_key": "sk-ant-api03-supersecretkey1234567890"},
                    "elevenlabs": {"api_key": "sk_elevenlabs_secret_value_1234567890"},
                })
                raw1 = sf.read_text(encoding="utf-8")
                self.assertIn(ENC_PREFIX, raw1)
                self.assertNotIn("sk-ant-api03-supersecretkey", raw1)

                settings_store.reset_claude_quota_counter()
                raw2 = sf.read_text(encoding="utf-8")
                self.assertIn(ENC_PREFIX, raw2)
                self.assertNotIn("sk-ant-api03-supersecretkey", raw2)
                self.assertNotIn("sk_elevenlabs_secret_value", raw2)

                p = settings_store.save_custom_preset({"label": "SecTest", "engine": "claude"})
                raw3 = sf.read_text(encoding="utf-8")
                self.assertNotIn("sk-ant-api03-supersecretkey", raw3)
                self.assertNotIn("sk_elevenlabs_secret_value", raw3)

                self.assertTrue(settings_store.delete_custom_preset(p["id"]))
                raw4 = sf.read_text(encoding="utf-8")
                self.assertNotIn("sk-ant-api03-supersecretkey", raw4)
                self.assertNotIn("sk_elevenlabs_secret_value", raw4)

    def test_edition_blocks_risky_prefixes_in_public(self):
        with patch.object(edition, "EDITION", "public"):
            for path in (
                "/api/analyze-short",
                "/api/analytics/internal/summary",
                "/api/drive/sync",
                "/api/competitors",
            ):
                self.assertTrue(edition.is_blocked_path(path), msg=f"Expected blocked in public: {path}")

    def test_drive_sync_confines_directory(self):
        with self.assertRaises(ValueError):
            DriveClient.sync_from_local_folder("/etc")
        with self.assertRaises(ValueError):
            DriveClient.sync_from_local_folder(str(Path.home()))

    def test_analytics_blocks_ytdlp_flag_injection_and_gemini_in_public(self):
        with self.assertRaises(ValueError):
            analytics_engine.AnalyticsEngine.fetch_video_metrics("--exec=id")

        with patch.object(edition, "EDITION", "public"):
            with patch("core.claude_bridge.ClaudeBridge.check_status", return_value={"connected": False}), patch(
                "core.gemini_studio.GeminiStudio.query"
            ) as gq:
                self.assertEqual(inspiration_radar._default_ai_query("hi", "sys"), "")
                gq.assert_not_called()

    def test_channel_stats_remake_routes_to_make_in_public(self):
        sample_stats = {"videos": [{"id": "ytvid123456", "title": "Test", "duration": 30, "url": "https://youtu.be/ytvid123456"}]}
        with patch.object(edition, "EDITION", "public"), patch.object(channel_stats, "load", return_value=sample_stats), patch.object(
            channel_stats, "render_for_video", return_value=""
        ):
            req = channel_stats.remake_request("ytvid123456")
            self.assertEqual(req["route"], "/api/make")


if __name__ == "__main__":
    unittest.main()
