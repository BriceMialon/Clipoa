import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp_server"))

from core import agent_team, edition  # noqa: E402


class TestAgentTeamConfirmation(unittest.TestCase):
    """L'équipe d'agents ne lance jamais une fabrication sans confirmation explicite."""

    def _run(self, message, **kw):
        calls = {"week": 0, "make": 0, "remake": 0}

        def week(topics, **_):
            calls["week"] += 1
            return len(topics)

        def make(**_):
            calls["make"] += 1

        def remake(*_a, **_k):
            calls["remake"] += 1

        plan = [{"titre": f"Sujet {i}"} for i in range(5)]
        with patch("agents.team.LeStratege.plan_weekly_shorts", return_value=plan):
            out = agent_team.run_mission(message, enqueue_week_fn=week, make_video_fn=make,
                                         remake_video_fn=remake, **kw)
        return out, calls

    def test_week_phrase_does_not_enqueue_without_confirmation(self):
        out, calls = self._run("Fais un point sur ma semaine")
        self.assertEqual(out["action"], "needs_confirmation")
        self.assertEqual(calls["week"], 0)
        confirm = [a for a in out["actions"] if a.get("confirm")][0]
        self.assertEqual(len(confirm["topics"]), 5)

    def test_week_confirmed_enqueues_the_shown_topics(self):
        out, calls = self._run("Génère mes 5 vidéos pour la semaine", confirmed=True, topics=["A", "B"])
        self.assertEqual(calls["week"], 1)
        self.assertEqual(out["data"]["created"], 2)

    def test_make_video_needs_confirmation(self):
        out, calls = self._run("Crée une vidéo sur les requins")
        self.assertEqual(out["action"], "needs_confirmation")
        self.assertEqual(calls["make"], 0)
        out, calls = self._run("Crée une vidéo sur les requins", confirmed=True)
        self.assertEqual(calls["make"], 1)

    def test_remake_needs_confirmation(self):
        stats = {"videos": [{"id": "abcdefghijk", "title": "T", "score": 10}]}
        with patch("core.channel_stats.load", return_value=stats):
            out, calls = self._run("Refais ma pire vidéo")
            self.assertEqual(out["action"], "needs_confirmation")
            self.assertEqual(calls["remake"], 0)
            out, calls = self._run("Refais ma pire vidéo", confirmed=True)
            self.assertEqual(calls["remake"], 1)


class TestPublicEditionCuts(unittest.TestCase):
    def test_agent_team_and_tiktok_handle_blocked_in_public(self):
        with patch.object(edition, "EDITION", "public"):
            self.assertTrue(edition.is_blocked_path("/api/agent-team/run"))
            self.assertTrue(edition.is_blocked_path("/api/agent-team/roster"))
            self.assertTrue(edition.is_blocked_path("/api/channel-stats/tiktok-handle"))
            self.assertFalse(edition.is_blocked_path("/api/channel-stats/sync"))

    def test_tiktok_ytdlp_fallback_off_in_public(self):
        from core import channel_stats
        with patch.object(edition, "EDITION", "public"), \
                patch("core.social_publisher.FreeSocialPublisher.get_account_config", return_value={}), \
                patch.object(channel_stats, "_find_ytdlp") as find:
            with self.assertRaises(RuntimeError):
                channel_stats.fetch_tiktok_videos(fallback_name="someone")
            find.assert_not_called()


class TestMcpLocalOnly(unittest.TestCase):
    def test_remote_url_is_refused(self):
        mcp = importlib.import_module("cliproll_mcp")
        self.assertEqual(mcp._local_url("https://evil.example.com"), "http://127.0.0.1:8080")
        self.assertEqual(mcp._local_url("http://localhost:9000"), "http://localhost:9000")
        self.assertEqual(mcp._local_url(""), "http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()
