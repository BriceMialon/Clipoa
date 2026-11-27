"""Nom du compte TikTok (plus de « TikTok connecté » générique) et styles livrés en lecture seule."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as clipoa_app
from core import social_publisher as sp
from core.social_publisher import FreeSocialPublisher, SAVED_KEY
from core.style_plugins import STARTER_PLUGINS, is_builtin_style


class TestTikTokNames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        td = Path(self.tmp.name)
        self.patches = [
            patch("core.social_publisher.ACCOUNTS_FILE", td / "social_accounts.json"),
            patch("core.social_publisher.OAUTH_APPS_FILE", td / "oauth_apps.json"),
            patch("core.social_publisher.QUEUE_FILE", td / "publish_queue.json"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _tt(self, open_id, name):
        return FreeSocialPublisher.save_account("tiktok", {
            "access_token": "tok_" + open_id, "refresh_token": "rt", "expires_at": int(time.time()) + 3600,
            "open_id": open_id, "username": name, "via_relay": True,
        })

    def test_legacy_placeholder_entry_is_hidden(self):
        self._tt("OPEN_1", "@drshark")
        raw = FreeSocialPublisher.load_accounts()
        raw[SAVED_KEY]["tiktok"]["TikTok (Connecté)"] = {"access_token": "old", "username": "TikTok (Connecté)"}
        with patch("core.social_publisher.FreeSocialPublisher.load_accounts", return_value=raw):
            st = FreeSocialPublisher.get_public_accounts_status()["tiktok"]
        self.assertEqual([a["label"] for a in st["accounts"]], ["@drshark"])

    def test_display_name_falls_back_without_profile_scope(self):
        denied = MagicMock(status_code=401)
        ok = MagicMock(status_code=200)
        ok.json.return_value = {"data": {"user": {"open_id": "x", "display_name": "Dr Shark"}}}
        with patch("core.social_publisher.requests.get", side_effect=[denied, ok]) as g:
            self.assertEqual(sp._tiktok_display_name("tok"), "Dr Shark")
        self.assertIn("username", g.call_args_list[0].args[0])
        self.assertNotIn("username", g.call_args_list[1].args[0])

    def test_refresh_renames_generic_account_and_keeps_tokens(self):
        self._tt("OPEN_1", "Compte TikTok")
        with patch("core.social_publisher._tiktok_display_name", return_value="Dr Shark"):
            self.assertEqual(FreeSocialPublisher.refresh_tiktok_names(), 1)
        st = FreeSocialPublisher.get_public_accounts_status()["tiktok"]
        self.assertEqual(st["label"], "Dr Shark")
        self.assertEqual(len(st["accounts"]), 1)
        raw = FreeSocialPublisher.load_accounts()
        self.assertEqual(raw["tiktok"]["access_token"], "tok_OPEN_1")
        self.assertEqual(raw["tiktok"]["open_id"], "OPEN_1")


class TestBuiltinStylesLocked(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        self.client = clipoa_app.app.test_client()
        with clipoa_app._RATE_LOCK:
            clipoa_app._RATE_BUCKETS.clear()

    def test_builtin_styles_cannot_be_changed(self):
        pid = STARTER_PLUGINS[0]["id"]
        self.assertTrue(is_builtin_style(pid))
        self.assertFalse(is_builtin_style("mon_style_perso"))
        with patch("app.StylePluginStore.update_plugin") as up, patch("app.StylePluginStore.delete_plugin") as de:
            self.assertEqual(self.client.put(f"/api/plugins/{pid}", json={"name": "x"}).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/plugins/{pid}").status_code, 403)
            self.assertEqual(self.client.post(f"/api/plugins/{pid}/script", json={"script_content": "x"}).status_code, 403)
            self.assertEqual(self.client.delete(f"/api/plugins/{pid}/sheets/a.png").status_code, 403)
            up.assert_not_called()
            de.assert_not_called()


if __name__ == "__main__":
    unittest.main()
