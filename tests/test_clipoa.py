import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as clipoa_app
from core.blender_engine import BlenderEngine
from core.video_composer import VideoComposer
from core.voice_engine import VoiceEngine
from core.settings_store import load_settings, save_settings, reset_claude_quota_counter, SETTINGS_FILE
from core.social_publisher import FreeSocialPublisher
from core.analytics_engine import AnalyticsEngine


class TestClipoaSecurityAndRoutes(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        self.client = clipoa_app.app.test_client()
        # Clear rate-limit buckets between tests
        with clipoa_app._RATE_LOCK:
            clipoa_app._RATE_BUCKETS.clear()

    def test_index_and_pwa_routes(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("ClipRoll", html)
        self.assertIn("Créer", html)
        # Verify security headers
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("X-Robots-Tag"), "noindex, nofollow, noarchive")

        self.assertEqual(self.client.get("/manifest.json").status_code, 200)
        self.assertEqual(self.client.get("/icon.svg").status_code, 200)
        robots = self.client.get("/robots.txt")
        self.assertEqual(robots.status_code, 200)
        self.assertIn("Disallow: /", robots.get_data(as_text=True))

    def test_scraper_user_agent_blocked(self):
        for ua in ("HTTrack/3.0", "Scrapy/2.11", "Wget/1.21"):
            r = self.client.get("/", headers={"User-Agent": ua})
            self.assertEqual(r.status_code, 403, f"Expected 403 for {ua}")

    def test_csrf_cross_origin_blocked(self):
        r = self.client.post(
            "/api/make",
            json={"topic": "test"},
            headers={"Origin": "https://evil-plagiarist.example.com"},
        )
        self.assertEqual(r.status_code, 403)

    def test_path_traversal_blocked(self):
        self.assertIn(self.client.get("/stream/..%2Fetc%2Fpasswd").status_code, (400, 404))
        self.assertEqual(self.client.get("/stream/..").status_code, 400)
        self.assertEqual(self.client.get("/download/bad$id").status_code, 400)
        self.assertEqual(self.client.delete("/api/videos/..").status_code, 400)
        r_pub = self.client.post(
            "/api/social/publish",
            json={"render_id": "../secret", "platforms": ["youtube"]},
        )
        self.assertEqual(r_pub.status_code, 400)
        r_rev = self.client.post(
            "/api/revise",
            json={"session_id": "../secret", "feedback": "change"},
        )
        self.assertEqual(r_rev.status_code, 400)

    def test_thumb_proxy_ssrf_blocked(self):
        # Spoofed suffix domain must be rejected
        r1 = self.client.get("/api/thumb?url=https://ytimg.com.evil.com/x.jpg")
        self.assertEqual(r1.status_code, 403)
        # Non-HTTPS rejected
        r2 = self.client.get("/api/thumb?url=http://127.0.0.1:8080/")
        self.assertEqual(r2.status_code, 400)

    def test_scan_input_validation(self):
        r = self.client.post("/api/scan", json={"url": "https://youtube.com/@test", "threshold": "not_a_num"})
        self.assertEqual(r.status_code, 400)

    def test_oauth_error_redirect_url_encoded(self):
        r = self.client.get("/oauth/youtube/callback?error=bad%20err%26injected=1")
        self.assertEqual(r.status_code, 302)
        loc = r.headers.get("Location", "")
        self.assertNotIn("&injected=1", loc)
        self.assertIn("oauth_error=", loc)

    def test_double_resume_prevented(self):
        jid = clipoa_app._create_job("make", "Test Job", params={"topic": "hello"})
        try:
            r = self.client.post(f"/api/jobs/{jid}/resume")
            self.assertEqual(r.status_code, 409)
        finally:
            self.client.delete(f"/api/jobs/{jid}")

    def test_api_read_endpoints_ok(self):
        for ep in (
            "/api/status",
            "/api/videos",
            "/api/jobs",
            "/api/presets",
            "/api/social/accounts",
            "/api/social/queue",
            "/api/night/tasks",
            "/api/analytics/internal",
            "/api/analytics/external",
            "/api/drive/status",
            "/api/drive/ideas",
        ):
            r = self.client.get(ep)
            self.assertEqual(r.status_code, 200, f"Endpoint {ep} failed with {r.status_code}")
            self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_presets_crud_and_week_validation(self):
        r_bad = self.client.post("/api/presets", json={"label": ""})
        self.assertEqual(r_bad.status_code, 400)

        r_create = self.client.post(
            "/api/presets",
            json={"label": "Test Preset", "engine": "gemini", "render": "motion", "retention_boost": True},
        )
        self.assertEqual(r_create.status_code, 200)
        pid = r_create.get_json()["preset"]["id"]
        try:
            r_list = self.client.get("/api/presets")
            ids = [p["id"] for p in r_list.get_json()["presets"]]
            self.assertIn(pid, ids)
        finally:
            r_del = self.client.delete(f"/api/presets/{pid}")
            self.assertEqual(r_del.status_code, 200)
            self.assertTrue(r_del.get_json()["deleted"])

        self.assertEqual(self.client.post("/api/week", json={"niche": ""}).status_code, 400)


class TestClipoaCoreFixes(unittest.TestCase):
    def test_blender_script_escaping_and_mp4_output(self):
        with tempfile.TemporaryDirectory() as td:
            script_path = os.path.join(td, "scene.py")
            tricky_title = 'L\'argent "secret"\nprint("pwned")'
            BlenderEngine.create_sample_3d_script(tricky_title, script_path)
            code = Path(script_path).read_text(encoding="utf-8")
            # Must compile cleanly as valid Python
            compile(code, script_path, "exec")
            self.assertIn("file_format = 'FFMPEG'", code)
            self.assertIn("format = 'MPEG4'", code)

    def test_ass_subtitle_generation(self):
        with tempfile.TemporaryDirectory() as td:
            ass_file = os.path.join(td, "sub.ass")
            words = [
                {"word": "Bonjour", "start": 0.1, "end": 0.5},
                {"word": "ClipRoll!", "start": 0.5, "end": 1.0},
            ]
            VideoComposer.generate_ass_subtitles(words, ass_file, hook_text="ACCROCHE ÉLÉGANTE")
            content = Path(ass_file).read_text(encoding="utf-8")
            self.assertIn("ACCROCHE ÉLÉGANTE", content)
            self.assertIn("CLIPROLL!", content)

    def test_voice_engine_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            VoiceEngine.generate_voice("   ", "test_empty")

    def test_settings_permissions_and_quota_reset(self):
        before = load_settings()
        try:
            save_settings({"claude": {"live_quota": {"util_5h": 0.9, "resets_5h": 9999999999}}})
            mode = stat.S_IMODE(os.stat(SETTINGS_FILE).st_mode)
            self.assertEqual(mode, 0o600)
            reset_claude_quota_counter()
            after = load_settings()
            self.assertEqual(after["claude"]["live_quota"], {})
        finally:
            save_settings(before)

    def test_social_publisher_missing_file_error_shape(self):
        with patch.object(FreeSocialPublisher, "load_queue", return_value=[{
            "id": "post_test_missing",
            "video_path": "/nonexistent/clip.mp4",
            "platforms": ["youtube"],
            "title": "Test",
            "caption": "",
            "status": "publishing",
            "results": {},
        }]), patch.object(FreeSocialPublisher, "save_queue"):
            res = FreeSocialPublisher.execute_post("post_test_missing")
            self.assertEqual(res["status"], "failed")
            self.assertIsInstance(res["results"]["file"], dict)
            self.assertFalse(res["results"]["file"]["ok"])
            self.assertIn("introuvable", res["results"]["file"]["message"])

    def test_video_composer_retention_boost_ffmpeg_render(self):
        from config import FFMPEG_PATH, RENDERS_DIR
        import shutil
        sess_name = "test_retention_smoke"
        with tempfile.TemporaryDirectory() as td:
            wav_path = os.path.join(td, "sample.wav")
            subprocess.run(
                [FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1.2", wav_path],
                check=True,
                capture_output=True,
            )
            try:
                mp4 = VideoComposer.compose_short(
                    output_name=sess_name,
                    audio_path=wav_path,
                    script_data={"title": "Test", "hook_screen_text": "TEST HOOK", "full_spoken_script": "Bonjour ClipRoll"},
                    transcript_data=None,
                    theme="dark_luxury",
                    subtitle_style="submagic_yellow",
                    retention_boost=True,
                )
                self.assertTrue(os.path.exists(mp4))
                self.assertGreater(os.path.getsize(mp4), 10000)
            finally:
                shutil.rmtree(RENDERS_DIR / sess_name, ignore_errors=True)

    def test_frontend_js_syntax_valid(self):
        clipoa_app.app.config["TESTING"] = True
        html = clipoa_app.app.test_client().get("/").get_data(as_text=True)
        self.assertIn("fab-gen-script-btn", html)
        self.assertIn("modal-week", html)
        self.assertIn("modal-cmdk", html)
        scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html)
        self.assertTrue(scripts, "No inline <script> found in index.html")
        node_bin = ROOT / "runtime" / "node" / "bin" / "node"
        if not node_bin.exists():
            self.skipTest("Bundled node runtime not found")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write("\n".join(scripts))
            js_path = f.name
        try:
            proc = subprocess.run([str(node_bin), "--check", js_path], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"JS syntax error:\n{proc.stderr}")
        finally:
            os.unlink(js_path)


class TestSocialOAuthAndDirectPublish(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        self.client = clipoa_app.app.test_client()
        self.tmp_dir = tempfile.TemporaryDirectory()
        td = Path(self.tmp_dir.name)
        self.p_acc = patch("core.social_publisher.ACCOUNTS_FILE", td / "social_accounts.json")
        self.p_oa = patch("core.social_publisher.OAUTH_APPS_FILE", td / "oauth_apps.json")
        self.p_q = patch("core.social_publisher.QUEUE_FILE", td / "publish_queue.json")
        self.p_acc.start()
        self.p_oa.start()
        self.p_q.start()
        with clipoa_app._RATE_LOCK:
            clipoa_app._RATE_BUCKETS.clear()

    def tearDown(self):
        self.p_acc.stop()
        self.p_oa.stop()
        self.p_q.stop()
        self.tmp_dir.cleanup()

    def test_oauth_start_and_csrf_state_flow(self):
        FreeSocialPublisher.save_oauth_app("youtube", "123456-abc.apps.googleusercontent.com", "GOCSPX-testsecret")
        r = self.client.get("/oauth/youtube/start?from=auto")
        self.assertEqual(r.status_code, 302)
        loc = r.headers["Location"]
        self.assertIn("accounts.google.com/o/oauth2/v2/auth", loc)
        self.assertIn("state=", loc)

        # Forged callback without valid state must be rejected cleanly
        forged = self.client.get("/oauth/youtube/callback?code=fakecode&state=forged_nonce")
        self.assertEqual(forged.status_code, 302)
        self.assertIn("oauth_error=", forged.headers["Location"])

        # Valid POST relay-done with valid nonce saves real OAuth account and redirects to Diffusion
        nonce = FreeSocialPublisher.create_oauth_state("tiktok", target="tiktok", return_view="auto")
        r_done = self.client.post(
            "/oauth/tiktok/relay-done",
            data={
                "access_token": "act_tt_123",
                "refresh_token": "rft_tt_456",
                "expires_in": "86400",
                "open_id": "oid_789",
                "name": "@brice_clips",
                "nonce": nonce,
                "target": "tiktok",
            },
        )
        self.assertEqual(r_done.status_code, 302)
        self.assertIn("view=auto", r_done.headers["Location"])
        self.assertIn("connected=tiktok", r_done.headers["Location"])
        status = FreeSocialPublisher.get_public_accounts_status()["tiktok"]
        self.assertTrue(status["auto_api"])
        self.assertEqual(status["label"], "@brice_clips")

    def test_meta_multipage_ig_discovery_and_switch(self):
        pages = [
            {"id": "p1", "name": "Page Sans IG", "access_token": "tok_p1"},
            {
                "id": "p2",
                "name": "Page Avec IG",
                "access_token": "tok_p2",
                "instagram_business_account": {"id": "ig_999", "username": "clipoa.officiel"},
            },
        ]
        res = FreeSocialPublisher._save_meta_pages_and_accounts("user_ll_tok", pages, target="instagram")
        self.assertIn("instagram", res["connected_platforms"])
        pub = FreeSocialPublisher.get_public_accounts_status()
        self.assertTrue(pub["instagram"]["auto_api"])
        self.assertEqual(pub["instagram"]["ig_user_id"], "ig_999")
        self.assertEqual(pub["instagram"]["label"], "@clipoa.officiel")
        # Public status must never leak raw page access tokens
        self.assertNotIn("tok_p2", json.dumps(pub))

    def test_instagram_and_facebook_direct_binary_reels_publish(self):
        mp4_path = Path(self.tmp_dir.name) / "reel.mp4"
        mp4_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1024)

        class FakeResp:
            def __init__(self, status_code, payload, headers=None):
                self.status_code = status_code
                self._payload = payload
                self.headers = headers or {}
                self.text = json.dumps(payload)

            def json(self):
                return self._payload

        # 1. Instagram Reels resumable binary upload (no public_video_url needed!)
        with patch("core.social_publisher.time.sleep"), patch("core.social_publisher.requests.post") as m_post, patch(
            "core.social_publisher.requests.get"
        ) as m_get:
            m_post.side_effect = [
                FakeResp(200, {"id": "cont_1", "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/cont_1"}),
                FakeResp(200, {"success": True}),
                FakeResp(200, {"id": "ig_media_77"}),
            ]
            m_get.side_effect = [
                FakeResp(200, {"status_code": "FINISHED"}),
                FakeResp(200, {"permalink": "https://www.instagram.com/reel/ABC123/"}),
            ]
            ig_res = FreeSocialPublisher._publish_instagram(
                {"ig_user_id": "ig_999", "access_token": "tok_ig"},
                video_path=str(mp4_path),
                caption="Mon Reel #Reels",
            )
            self.assertTrue(ig_res["ok"])
            self.assertEqual(ig_res["url"], "https://www.instagram.com/reel/ABC123/")

        # 2. Facebook Reels 3-phase upload
        with patch("core.social_publisher.requests.post") as m_post_fb:
            m_post_fb.side_effect = [
                FakeResp(200, {"video_id": "fb_vid_42", "upload_url": "https://rupload.facebook.com/video-upload/v21.0/fb_vid_42"}),
                FakeResp(200, {"success": True}),
                FakeResp(200, {"success": True}),
            ]
            fb_res = FreeSocialPublisher._publish_facebook(
                {"page_id": "p2", "access_token": "tok_p2"},
                video_path=str(mp4_path),
                title="Mon Reel FB",
                caption="Description FB",
            )
            self.assertTrue(fb_res["ok"])
            self.assertEqual(fb_res["url"], "https://www.facebook.com/reel/fb_vid_42")

    def test_upload_short_and_schedule_requires_auto_api(self):
        from config import FFMPEG_PATH, RENDERS_DIR
        import io
        import shutil

        sample_mp4 = Path(self.tmp_dir.name) / "tiny.mp4"
        subprocess.run(
            [
                FFMPEG_PATH, "-y",
                "-f", "lavfi", "-i", "color=c=black:s=360x640:d=0.6",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(sample_mp4),
            ],
            check=True,
            capture_output=True,
        )
        uploaded_id = None
        try:
            r_up = self.client.post(
                "/api/videos/upload",
                data={"video": (io.BytesIO(sample_mp4.read_bytes()), "mon_short_test.mp4")},
                content_type="multipart/form-data",
            )
            self.assertEqual(r_up.status_code, 200)
            uploaded_id = r_up.get_json()["video"]["id"]

            # Shortcut mode ('same_browser:') must NOT allow unattended scheduled publishing
            FreeSocialPublisher.save_account("youtube", {"access_token": "same_browser:youtube", "channel_name": "@test"})
            r_sched_fail = self.client.post(
                "/api/social/publish",
                json={
                    "render_id": uploaded_id,
                    "platforms": ["youtube"],
                    "title": "Test",
                    "scheduled_at": "2030-01-01T12:00",
                    "publish_now": False,
                },
            )
            self.assertEqual(r_sched_fail.status_code, 400)

            # Real OAuth token allows scheduled publishing
            FreeSocialPublisher.save_account("youtube", {"access_token": "ya29.real_oauth_token", "channel_name": "@test"})
            r_sched_ok = self.client.post(
                "/api/social/publish",
                json={
                    "render_id": uploaded_id,
                    "platforms": ["youtube"],
                    "title": "Test Programmé",
                    "scheduled_at": "2030-01-01T12:00",
                    "publish_now": False,
                },
            )
            self.assertEqual(r_sched_ok.status_code, 200)
            self.assertEqual(r_sched_ok.get_json()["post"]["status"], "scheduled")

            # Video validation toggle persists to metadata.json and blocks path traversal
            self.assertEqual(self.client.post("/api/videos/../secret/validate", json={}).status_code, 404)
            self.assertEqual(self.client.post("/api/videos/bad$id/validate", json={}).status_code, 400)
            r_val1 = self.client.post(f"/api/videos/{uploaded_id}/validate", json={})
            self.assertEqual(r_val1.status_code, 200)
            self.assertTrue(r_val1.get_json()["validated"])

            r_val2 = self.client.post(f"/api/videos/{uploaded_id}/validate", json={})
            self.assertEqual(r_val2.status_code, 200)
            self.assertFalse(r_val2.get_json()["validated"])

            # Verify Dark Liquid Glass sidebar, 9:16 style plaques, Theater modal & Connexions bento render
            html = self.client.get("/").get_data(as_text=True)
            for marker in ("sidebar-nav-wrap", "style-plaques-strip", "conn-opt-plaque", "modal-theater", 'data-theme="dark"'):
                self.assertIn(marker, html)
        finally:
            if uploaded_id:
                shutil.rmtree(RENDERS_DIR / uploaded_id, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
