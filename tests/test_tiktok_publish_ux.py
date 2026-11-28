"""Règles TikTok Content Posting API (Direct Post) : choix de l'utilisateur transmis tels quels."""
import os
import tempfile
import unittest
from unittest import mock

from core import social_publisher as sp
from core.social_publisher import FreeSocialPublisher, clean_tiktok_options, tiktok_options_error


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class TikTokOptionsValidation(unittest.TestCase):
    def test_privacy_required(self):
        self.assertIn("voir", tiktok_options_error({"consent": True}))

    def test_unknown_privacy_dropped(self):
        self.assertEqual(clean_tiktok_options({"privacy_level": "EVERYONE"})["privacy_level"], "")

    def test_commercial_needs_a_choice(self):
        err = tiktok_options_error({"privacy_level": "PUBLIC_TO_EVERYONE", "commercial": True, "consent": True})
        self.assertIn("promotion", err)

    def test_branded_content_not_private(self):
        err = tiktok_options_error({
            "privacy_level": "SELF_ONLY", "commercial": True, "brand_content": True, "consent": True,
        })
        self.assertIn("Moi uniquement", err)

    def test_consent_required(self):
        self.assertIn("musique", tiktok_options_error({"privacy_level": "SELF_ONLY"}))

    def test_valid(self):
        self.assertEqual(tiktok_options_error({"privacy_level": "SELF_ONLY", "consent": True}), "")

    def test_brand_flags_ignored_without_commercial(self):
        o = clean_tiktok_options({"privacy_level": "SELF_ONLY", "brand_content": True})
        self.assertFalse(o["brand_content"])


class TikTokPublishUsesUserChoices(unittest.TestCase):
    def test_init_payload(self):
        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.write(fd, b"0" * 1024)
        os.close(fd)
        self.addCleanup(os.remove, path)
        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append((url, json))
            if url.endswith("creator_info/query/"):
                return _Resp(200, {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"]}})
            if url.endswith("video/init/"):
                return _Resp(200, {"data": {"upload_url": "https://up", "publish_id": ""}})
            return _Resp(200, {"data": {}})

        opts = {"privacy_level": "SELF_ONLY", "allow_comment": True, "allow_duet": False,
                "allow_stitch": False, "commercial": True, "brand_organic": True, "consent": True}
        with mock.patch.object(FreeSocialPublisher, "_ensure_tiktok_token", return_value="tok"), \
                mock.patch.object(sp.requests, "post", side_effect=fake_post), \
                mock.patch.object(sp.requests, "put", return_value=_Resp(201, {})):
            res = FreeSocialPublisher._publish_tiktok({}, path, "t", "c", opts)
        self.assertTrue(res["ok"])
        init = next(j for u, j in calls if u.endswith("/post/publish/video/init/"))
        info = init["post_info"]
        self.assertEqual(info["privacy_level"], "SELF_ONLY")
        self.assertFalse(info["disable_comment"])
        self.assertTrue(info["disable_duet"])
        self.assertTrue(info["disable_stitch"])
        self.assertTrue(info["brand_organic_toggle"])
        self.assertFalse(info["brand_content_toggle"])

    def test_privacy_no_longer_allowed(self):
        def fake_post(url, headers=None, json=None, timeout=None):
            return _Resp(200, {"data": {"privacy_level_options": ["SELF_ONLY"]}})

        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.write(fd, b"0" * 10)
        os.close(fd)
        self.addCleanup(os.remove, path)
        with mock.patch.object(FreeSocialPublisher, "_ensure_tiktok_token", return_value="tok"), \
                mock.patch.object(sp.requests, "post", side_effect=fake_post):
            res = FreeSocialPublisher._publish_tiktok(
                {}, path, "t", "c", {"privacy_level": "PUBLIC_TO_EVERYONE", "consent": True})
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
