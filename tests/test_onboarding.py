import json
import tempfile
import unittest
from pathlib import Path

from core import onboarding

TOOLS_OK = {"tools": {k: {"ok": True} for k in ("ffmpeg", "whisper", "voice", "blender", "yt_dlp")}}
SOCIAL = {"youtube": {"short_name": "YouTube", "oauth_provider": "youtube", "auto_api": False},
          "tiktok": {"short_name": "TikTok", "oauth_provider": "tiktok", "auto_api": False}}
OAUTH = {"youtube": {"configured": True}, "tiktok": {"configured": False}}


def calc(**kw):
    args = dict(tools_status=TOOLS_OK, claude_connected=True, renders_count=1, unvalidated_count=0,
                social_accounts=SOCIAL, oauth_apps=OAUTH, state={"status": "new"})
    args.update(kw)
    return onboarding.compute(**args)


class OnboardingTest(unittest.TestCase):
    def test_next_action_order(self):
        bad = {"tools": {"ffmpeg": {"ok": True}, "blender": {"ok": False, "auto": True}}}
        self.assertEqual(calc(tools_status=bad)["next"]["action"], "guide:tools")
        self.assertEqual(calc(claude_connected=False)["next"]["action"], "guide:claude")
        self.assertEqual(calc(renders_count=0)["next"]["action"], "create")
        self.assertEqual(calc(unvalidated_count=2)["next"]["text"], "2 vidéos t'attendent.")
        self.assertEqual(calc()["next"]["text"], "Connecte YouTube pour publier en un clic.")
        done = dict(SOCIAL, youtube=dict(SOCIAL["youtube"], auto_api=True))
        self.assertEqual(calc(social_accounts=done)["next"]["text"], "Fabrique ta prochaine vidéo.")

    def test_no_social_suggestion_when_oauth_not_ready(self):
        self.assertEqual(calc(oauth_apps={})["next"]["action"], "create")

    def test_tools_step_hides_cine_and_offers_blender_install(self):
        st = {"tools": dict(TOOLS_OK["tools"], blender={"ok": False, "auto": True},
                            cine={"ok": False, "optional": True})}
        tools = calc(tools_status=st)["steps"][0]
        self.assertFalse(tools["done"])
        self.assertNotIn("cine", [i["id"] for i in tools["items"]])
        self.assertTrue(next(i for i in tools["items"] if i["id"] == "blender")["can_install"])

    def test_texts_never_mention_hidden_features(self):
        blob = json.dumps(calc(), ensure_ascii=False).lower()
        js = (Path(__file__).resolve().parent.parent / "static/js/clipoa_onboarding.js").read_text(encoding="utf-8").lower()
        for word in ("gemini", "ciné", "cine", "antigravity"):
            self.assertNotIn(word, blob)
            self.assertNotIn(word, js)

    def test_state_skip_restart_and_auto_open(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "onboarding.json"
            self.assertEqual(onboarding.load_state(p)["status"], "new")
            self.assertEqual(onboarding.apply_action("skip", p)["status"], "skipped")
            self.assertFalse(calc(state=onboarding.load_state(p))["auto_open"])
            onboarding.apply_action("restart", p)
            self.assertTrue(calc(state=onboarding.load_state(p))["auto_open"])
            onboarding.apply_action("video_started", p)
            self.assertTrue(calc(renders_count=0, state=onboarding.load_state(p))["steps"][3]["done"])
            with self.assertRaises(ValueError):
                onboarding.apply_action("rm -rf", p)


if __name__ == "__main__":
    unittest.main()
