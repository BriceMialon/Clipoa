import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as clipoa_app
from core.social_publisher import FreeSocialPublisher, SAVED_KEY


class TestMultiAccounts(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        self.client = clipoa_app.app.test_client()
        self.tmp = tempfile.TemporaryDirectory()
        td = Path(self.tmp.name)
        self.acc_file = td / "social_accounts.json"
        self.patches = [
            patch("core.social_publisher.ACCOUNTS_FILE", self.acc_file),
            patch("core.social_publisher.OAUTH_APPS_FILE", td / "oauth_apps.json"),
            patch("core.social_publisher.QUEUE_FILE", td / "publish_queue.json"),
        ]
        for p in self.patches:
            p.start()
        with clipoa_app._RATE_LOCK:
            clipoa_app._RATE_BUCKETS.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _yt(self, cid, name, tok, rt):
        return FreeSocialPublisher.save_account("youtube", {
            "access_token": tok, "refresh_token": rt, "expires_at": int(time.time()) + 3600,
            "channel_id": cid, "channel_name": name,
        })

    def test_two_channels_kept_separately_and_switch(self):
        self._yt("UC_A", "Chaîne A", "tokA", "rtA")
        st = self._yt("UC_B", "Chaîne B", "tokB", "rtB")
        self.assertEqual(st["label"], "Chaîne B")
        self.assertEqual({a["key"] for a in st["accounts"]}, {"UC_A", "UC_B"})

        # Disk file must have encrypted tokens (never plaintext on disk)
        raw_disk = json.loads(self.acc_file.read_text())
        self.assertTrue(raw_disk[SAVED_KEY]["youtube"]["UC_A"]["refresh_token"].startswith("enc:v1:"))
        raw = FreeSocialPublisher.load_accounts()
        self.assertEqual(raw[SAVED_KEY]["youtube"]["UC_A"]["refresh_token"], "rtA")
        self.assertEqual(raw[SAVED_KEY]["youtube"]["UC_B"]["access_token"], "tokB")

        r = self.client.post("/api/social/switch-account", json={"platform": "youtube", "account_key": "UC_A"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["account"]["label"], "Chaîne A")
        raw = FreeSocialPublisher.load_accounts()
        self.assertEqual(raw["youtube"]["access_token"], "tokA")

    def test_new_channel_never_inherits_other_refresh_token(self):
        self._yt("UC_A", "Chaîne A", "tokA", "rtA")
        FreeSocialPublisher.save_account("youtube", {
            "access_token": "tokB", "refresh_token": "rtA", "channel_id": "UC_B", "channel_name": "Chaîne B",
        })
        raw = FreeSocialPublisher.load_accounts()
        self.assertNotEqual(raw[SAVED_KEY]["youtube"]["UC_B"].get("refresh_token"), "rtA")
        self.assertEqual(raw[SAVED_KEY]["youtube"]["UC_A"]["refresh_token"], "rtA")

    def test_token_refresh_on_inactive_account_does_not_change_active(self):
        self._yt("UC_A", "Chaîne A", "tokA", "rtA")
        self._yt("UC_B", "Chaîne B", "tokB", "rtB")
        FreeSocialPublisher.save_account("youtube", {"access_token": "tokA2"}, account_key="UC_A")
        raw = FreeSocialPublisher.load_accounts()
        self.assertEqual(raw["youtube"]["access_token"], "tokB")
        self.assertEqual(raw[SAVED_KEY]["youtube"]["UC_A"]["access_token"], "tokA2")

    def test_post_remembers_account_active_when_created(self):
        self._yt("UC_A", "Chaîne A", "tokA", "rtA")
        self._yt("UC_B", "Chaîne B", "tokB", "rtB")
        keys = FreeSocialPublisher._active_account_keys(["youtube"])
        self.assertEqual(keys, {"youtube": "UC_B"})
        cfg = FreeSocialPublisher.get_account_config("youtube", "UC_A")
        self.assertEqual(cfg["access_token"], "tokA")
        self.assertEqual(cfg["_account_key"], "UC_A")

    def test_disconnect_active_falls_back_to_other_account(self):
        self._yt("UC_A", "Chaîne A", "tokA", "rtA")
        self._yt("UC_B", "Chaîne B", "tokB", "rtB")
        r = self.client.post("/api/social/disconnect", json={"platform": "youtube"})
        acc = r.get_json()["account"]
        self.assertTrue(acc["connected"])
        self.assertEqual(acc["label"], "Chaîne A")
        self.assertEqual([a["key"] for a in acc["accounts"]], ["UC_A"])

    def test_legacy_single_account_file_is_migrated(self):
        self.acc_file.write_text(json.dumps({"youtube": {
            "access_token": "old", "channel_id": "UC_OLD", "channel_name": "Ancienne", "connected": True}}))
        st = FreeSocialPublisher.get_public_accounts_status()["youtube"]
        self.assertEqual([a["key"] for a in st["accounts"]], ["UC_OLD"])
        self.assertTrue(st["accounts"][0]["active"])

    def test_google_always_asks_which_account(self):
        FreeSocialPublisher.save_oauth_app("youtube", "123-abc.apps.googleusercontent.com", "GOCSPX-x")
        r = self.client.get("/oauth/youtube/start?from=auto")
        self.assertIn("select_account", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
