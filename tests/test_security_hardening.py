import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import app as clipoa_app
from config import BASE_DIR, STORAGE_DIR, VIDEOS_DIR
from core.security import (
    BoundedRateLimiter,
    JobConcurrencyGuard,
    cleanup_temp_storage,
    harden_sensitive_files,
    is_allowed_host_header,
    redact_sensitive_text,
    validate_cookie_browser,
    validate_local_media_path,
    validate_public_http_url,
    validate_relay_url,
)
from core.vault import (
    ENC_PREFIX,
    decrypt_secret,
    decrypt_sensitive_fields,
    encrypt_secret,
    encrypt_sensitive_fields,
)


class TestSecurityHardening(unittest.TestCase):
    def setUp(self):
        clipoa_app._RATE_LIMITER.reset()
        self.client = clipoa_app.app.test_client()

    def test_public_url_blocks_ssrf_and_flag_injection(self):
        bad_urls = [
            "",
            "--exec=touch /tmp/pwn",
            "file:///etc/passwd",
            "http://127.0.0.1:8080/api/status",
            "http://localhost:8080/",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/admin",
            "http://10.0.0.1/internal",
            "http://user:pass@youtube.com/watch?v=1",
            "https://example.com/\nnewline",
        ]
        for bad in bad_urls:
            with self.subTest(url=bad):
                with self.assertRaises(ValueError):
                    validate_public_http_url(bad)

        good = validate_public_http_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(good, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_local_media_path_confinement(self):
        with self.assertRaises(ValueError):
            validate_local_media_path("/etc/passwd", [STORAGE_DIR])

        with tempfile.TemporaryDirectory(dir=str(VIDEOS_DIR)) as tmpdir:
            bad_ext = Path(tmpdir) / "evil.py"
            bad_ext.write_text("print(1)", encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_local_media_path(str(bad_ext), [STORAGE_DIR])

            good_mp4 = Path(tmpdir) / "clip.mp4"
            good_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            resolved = validate_local_media_path(str(good_mp4), [STORAGE_DIR])
            self.assertEqual(resolved, good_mp4.resolve())

    def test_relay_url_requires_https_for_remote(self):
        with self.assertRaises(ValueError):
            validate_relay_url("http://evil.example.com")
        with self.assertRaises(ValueError):
            validate_relay_url("https://192.168.1.50")
        with self.assertRaises(ValueError):
            validate_relay_url("ftp://clipoa.example.com")

        self.assertEqual(
            validate_relay_url("https://clipoa-oauth.clipoa-studio.workers.dev/"),
            "https://clipoa-oauth.clipoa-studio.workers.dev",
        )
        self.assertEqual(validate_relay_url("http://localhost:8787/"), "http://localhost:8787")

    def test_cookie_browser_allowlist(self):
        self.assertEqual(validate_cookie_browser("Chrome"), "chrome")
        self.assertIsNone(validate_cookie_browser(""))
        with self.assertRaises(ValueError):
            validate_cookie_browser("chrome;id")

    def test_bounded_rate_limiter_enforces_and_prunes(self):
        rl = BoundedRateLimiter(max_buckets=120)
        ok1, _ = rl.allow("ip1", 2, 60)
        ok2, _ = rl.allow("ip1", 2, 60)
        ok3, retry = rl.allow("ip1", 2, 60)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertFalse(ok3)
        self.assertGreaterEqual(retry, 1)

        # Simulate DDoS with many unique IPs — bucket count must stay bounded
        for i in range(400):
            rl.allow(f"attacker:{i}", 5, 60)
        self.assertLessEqual(len(rl._buckets), 125)

    def test_job_concurrency_guard_caps_queue(self):
        guard = JobConcurrencyGuard(max_concurrent=1, max_queued=2)
        self.assertTrue(guard.try_reserve())
        self.assertTrue(guard.try_reserve())
        self.assertFalse(guard.try_reserve())
        guard.cancel_reservation()
        guard.cancel_reservation()
        self.assertEqual(guard.stats()["inflight"], 0)

    def test_api_blocks_arbitrary_file_read_and_ssrf(self):
        # /api/make background_video outside storage
        r = self.client.post("/api/make", json={"topic": "test", "background_video": "/etc/passwd"})
        self.assertEqual(r.status_code, 400)

        # /api/cut local file outside storage
        r = self.client.post("/api/cut", json={"source": "/etc/passwd"})
        self.assertEqual(r.status_code, 400)

        # /api/cut SSRF
        r = self.client.post("/api/cut", json={"source": "http://169.254.169.254/latest/meta-data/"})
        self.assertEqual(r.status_code, 400)

        # /api/scan SSRF & flag injection
        r = self.client.post("/api/scan", json={"url": "http://127.0.0.1:8080/"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/scan", json={"url": "--exec=id"})
        self.assertEqual(r.status_code, 400)

        # /api/clone SSRF
        r = self.client.post("/api/clone", json={"url": "http://10.0.0.1/video", "topic": "test"})
        self.assertEqual(r.status_code, 400)

        # /api/social/relay-config plaintext HTTP
        r = self.client.post("/api/social/relay-config", json={"url": "http://insecure.example.com"})
        self.assertEqual(r.status_code, 400)

    def test_system_health_and_cleanup_endpoints(self):
        r = self.client.get("/api/system/health")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("storage", data)
        self.assertIn("jobs_guard", data)
        self.assertEqual(data["security"]["bind_host"], "127.0.0.1")

        # Cleanup on isolated temp directories
        with tempfile.TemporaryDirectory() as tmp:
            dl = Path(tmp) / "downloads"
            au = Path(tmp) / "audio"
            dl.mkdir()
            au.mkdir()
            old_file = dl / "old.mp4"
            old_file.write_bytes(b"12345")
            old_ts = os.path.getmtime(old_file) - 10 * 86400
            os.utime(old_file, (old_ts, old_ts))
            fresh_file = au / "fresh.wav"
            fresh_file.write_bytes(b"12345")

            res = cleanup_temp_storage(dl, au, max_age_days=7)
            self.assertEqual(res["removed_items"], 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(fresh_file.exists())

    def test_lan_token_guard_blocks_unauthenticated_remote_ip(self):
        orig_token = clipoa_app._LAN_ACCESS_TOKEN
        try:
            clipoa_app._LAN_ACCESS_TOKEN = "secret-lan-token-123"
            # Non-loopback without token -> 401
            r = self.client.get("/api/system/health", environ_base={"REMOTE_ADDR": "192.168.1.42"})
            self.assertEqual(r.status_code, 401)

            # Non-loopback with header token -> 200
            r = self.client.get(
                "/api/system/health",
                headers={"X-Clipoa-Token": "secret-lan-token-123"},
                environ_base={"REMOTE_ADDR": "192.168.1.42"},
            )
            self.assertEqual(r.status_code, 200)

            # Non-loopback with ?token=... sets HttpOnly cookie
            r = self.client.get(
                "/api/system/health?token=secret-lan-token-123",
                environ_base={"REMOTE_ADDR": "192.168.1.42"},
            )
            self.assertEqual(r.status_code, 200)
            self.assertIn("HttpOnly", r.headers.get("Set-Cookie", ""))

            # Loopback always allowed without token
            r = self.client.get("/api/system/health", environ_base={"REMOTE_ADDR": "127.0.0.1"})
            self.assertEqual(r.status_code, 200)
        finally:
            clipoa_app._LAN_ACCESS_TOKEN = orig_token

    @unittest.skipIf(os.name == "nt", "droits Unix 600 : sans objet sous Windows")
    def test_harden_sensitive_files_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            sdir = Path(tmp)
            acc = sdir / "social_accounts.json"
            acc.write_text("{}", encoding="utf-8")
            os.chmod(acc, 0o644)
            harden_sensitive_files(sdir)
            mode = stat.S_IMODE(os.stat(acc).st_mode)
            self.assertEqual(mode, 0o600)

    def test_oauth_relay_worker_js_syntax(self):
        node_bin = BASE_DIR / "runtime" / "node" / "bin" / "node"
        if not node_bin.exists():
            self.skipTest("Portable node not installed")
        worker_js = BASE_DIR / "oauth_relay_worker.js"
        res = subprocess.run([str(node_bin), "--check", str(worker_js)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_vault_encrypts_and_decrypts_tokens_and_proxies(self):
        raw = {
            "youtube": {
                "access_token": "ya29.super-secret-token-12345",
                "refresh_token": "1//0g-refresh-secret-67890",
                "channel_name": "Studio Créateur",
            },
            "_saved": {
                "youtube": {
                    "UC123": {
                        "access_token": "ya29.saved-token-abc",
                        "proxy_url": "http://client:superpass@1.2.3.4:8080",
                    }
                }
            },
        }
        enc = encrypt_sensitive_fields(raw)
        self.assertTrue(enc["youtube"]["access_token"].startswith(ENC_PREFIX))
        self.assertNotIn("super-secret-token", enc["youtube"]["access_token"])
        self.assertTrue(enc["_saved"]["youtube"]["UC123"]["proxy_url"].startswith(ENC_PREFIX))
        self.assertEqual(enc["youtube"]["channel_name"], "Studio Créateur")

        dec = decrypt_sensitive_fields(enc)
        self.assertEqual(dec, raw)

        # Tampered ciphertext must fail closed (return empty string)
        tampered = enc["youtube"]["access_token"][:-2] + ("AA" if not enc["youtube"]["access_token"].endswith("AA") else "BB")
        self.assertEqual(decrypt_secret(tampered), "")

        # Legacy plaintext stays readable
        self.assertEqual(decrypt_secret("legacy-plain-token"), "legacy-plain-token")
        # UI sentinel preserved
        self.assertEqual(encrypt_secret("same_browser:tiktok"), "same_browser:tiktok")

    def test_redact_sensitive_text_scrubs_tokens_proxies_ips_and_paths(self):
        msg = (
            "Failed proxy http://alice:MyP@ssw0rd@82.64.12.99:8080 "
            "with Authorization: Bearer ya29.abcdef12345678901234567890 "
            "key sk-ant-api03-secretvalue1234567890 in /Users/brice/secret.json"
        )
        red = redact_sensitive_text(msg, mask_ips=True)
        self.assertNotIn("MyP@ssw0rd", red)
        self.assertNotIn("alice:", red)
        self.assertNotIn("82.64.12.99", red)
        self.assertNotIn("ya29.abcdef", red)
        self.assertNotIn("sk-ant-api03", red)
        self.assertNotIn("/Users/brice/", red)
        self.assertIn("82.64.***.***", red)
        self.assertIn("/Users/[USER]/", red)

    def test_dns_rebinding_and_cross_site_fetch_blocked(self):
        self.assertTrue(is_allowed_host_header("localhost:8080"))
        self.assertTrue(is_allowed_host_header("127.0.0.1:8080"))
        self.assertFalse(is_allowed_host_header("evil.com:8080"))

        r = self.client.get("/api/social/accounts", headers={"Host": "evil.com:8080"})
        self.assertEqual(r.status_code, 403)

        r = self.client.get("/api/social/accounts", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
