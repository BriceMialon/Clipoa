import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as clipoa_app  # noqa: E402
from core import edition, license as lic, night_factory  # noqa: E402


class TestPublicEditionGuards(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        clipoa_app._RATE_LIMITER.reset()
        self.client = clipoa_app.app.test_client()

    def test_public_edition_license_gate_covers_all_creation_and_ai_routes(self):
        tmp = tempfile.mkdtemp()
        try:
            with patch.object(edition, "EDITION", "public"), patch.object(
                clipoa_app, "LICENSE", lic.LicenseManager(tmp, "https://example.invalid", "")
            ):
                for path in (
                    "/api/make",
                    "/api/make-from-script",
                    "/api/fabrique/generate-script",
                    "/api/week",
                    "/api/cut",
                    "/api/revise",
                    "/api/script-lab/generate",
                    "/api/script/optimize-retention",
                    "/api/channel-stats/audit",
                    "/api/voice/preview",
                    "/api/social/publish",
                    "/api/jobs/job123/resume",
                    "/api/social/queue/post123/publish-now",
                    "/api/channel-stats/abcdefghijk/remake",
                ):
                    r = self.client.post(path, json={})
                    self.assertEqual(r.status_code, 402, f"Expected 402 for POST {path}, got {r.status_code}")
                    self.assertTrue(r.get_json().get("license_required"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_public_edition_blocks_browser_session_and_filters_heavy_plugins(self):
        tmp = tempfile.mkdtemp()
        try:
            with patch.object(edition, "EDITION", "public"), patch.object(
                clipoa_app, "LICENSE", lic.LicenseManager(tmp, "https://example.invalid", "")
            ):
                r = self.client.post("/api/social/connect", json={"platform": "tiktok", "access_token": "browser_session:tiktok"})
                self.assertEqual(r.status_code, 403)
                plugins = self.client.get("/api/plugins").get_json()["plugins"]
                self.assertFalse(any(p.get("heavy") for p in plugins))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_night_factory_blocked_in_public_and_iso_z_handled(self):
        orig = night_factory.NightFactory._worker_started
        try:
            night_factory.NightFactory._worker_started = False
            with patch.object(edition, "EDITION", "public"):
                night_factory.NightFactory.start_worker()
                self.assertFalse(night_factory.NightFactory._worker_started)
        finally:
            night_factory.NightFactory._worker_started = orig

        res = night_factory.next_free_slot("2020-01-01T18:00:00Z")
        self.assertRegex(res, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")

    def test_license_deactivate_offline_and_permissions(self):
        tmp = tempfile.mkdtemp()
        try:
            lm = lic.LicenseManager(tmp, "https://example.invalid", "")
            lm._save({"key": "CLIPOA-ABCD-EFGH-JKLM", "token": "tok"})
            mode = stat.S_IMODE(Path(lm.path).stat().st_mode)
            self.assertEqual(mode, 0o600)
            with patch.object(lm, "_post", side_effect=RuntimeError("offline")):
                with self.assertRaises(RuntimeError):
                    lm.deactivate(force=False)
                st = lm.deactivate(force=True)
                self.assertEqual(st["state"], "perso")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
