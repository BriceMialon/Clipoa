import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from config import BASE_DIR
from core import crash_report as cr


class CrashReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [
            mock.patch.object(cr, "STORAGE_DIR", self.tmp),
            mock.patch.object(cr, "SUPPORT_DIR", self.tmp / "support"),
            mock.patch.object(cr, "INCIDENTS_FILE", self.tmp / "support" / "incidents.json"),
            mock.patch.object(cr, "OUTBOX_DIR", self.tmp / "support" / "outbox"),
        ]
        for p in self.patches:
            p.start()
        (self.tmp / "settings.json").write_text(json.dumps({
            "anthropic_api_key": "sk-ant-api03-SUPERSECRETVALUE1234567890",
            "elevenlabs": {"api_key": "a1b2c3d4e5f6weirdformat99"},
            "theme": "dark",
        }), encoding="utf-8")
        (self.tmp / "social_accounts.json").write_text(json.dumps({
            "youtube": {"access_token": "opaque.Token.Value-42", "channel_name": "Ma chaîne"},
        }), encoding="utf-8")
        cr._LOG_RING.clear()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_known_secrets_reads_storage_files(self):
        secrets = cr.known_secrets()
        self.assertIn("a1b2c3d4e5f6weirdformat99", secrets)
        self.assertIn("opaque.Token.Value-42", secrets)
        self.assertNotIn("dark", secrets)
        self.assertNotIn("Ma chaîne", secrets)

    def test_scrub_removes_keys_tokens_emails_paths(self):
        secrets = cr.known_secrets()
        raw = ("clé a1b2c3d4e5f6weirdformat99 jeton opaque.Token.Value-42 "
               "sk-ant-api03-OTHERKEY12345678901234 sk_0123456789abcdef0123456789abcdef "
               "mail jean.dupont@example.com chemin /Users/jean/Videos ip 82.64.10.20 "
               "Authorization: Bearer abcdefgh12345678")
        out = cr.scrub(raw, secrets)
        for leaked in ("a1b2c3d4e5f6weirdformat99", "opaque.Token.Value-42", "OTHERKEY", "0123456789abcdef0123",
                       "jean.dupont@example.com", "/Users/jean", "82.64.10.20", "abcdefgh12345678"):
            self.assertNotIn(leaked, out)
        self.assertIn("/Users/[USER]/Videos", out)

    def test_incident_dedup_and_pending(self):
        a = cr.record_incident("job", "Blender a planté", step="Décor 3D", job_kind="make", job_id="job_1")
        b = cr.record_incident("job", "Blender a planté")
        self.assertEqual(a, b)
        pend = cr.pending_incidents()
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["count"], 2)
        cr._mark(a, dismissed=True)
        self.assertEqual(cr.pending_incidents(), [])

    def test_build_report_is_scrubbed(self):
        cr._LOG_RING.append("12:00:00 appel avec sk-ant-api03-SUPERSECRETVALUE1234567890")
        inc = cr.record_incident("server", "KeyError avec a1b2c3d4e5f6weirdformat99", tb="Traceback /Users/brice/x.py")
        rep = cr.build_report(kind="crash", incident_id=inc, message="ça plante", contact_email="moi@exemple.fr")
        dump = json.dumps(rep, ensure_ascii=False)
        self.assertNotIn("SUPERSECRETVALUE", dump)
        self.assertNotIn("weirdformat99", dump)
        self.assertNotIn("/Users/brice", dump)
        self.assertEqual(rep["contact_email"], "moi@exemple.fr")
        self.assertEqual(rep["schema"], 1)
        self.assertIn("version", rep["app"])
        self.assertEqual(rep["incident"]["source"], "server")
        no_logs = cr.build_report(kind="contact", message="question", include_logs=False, contact_email="pas-un-mail")
        self.assertNotIn("logs", no_logs)
        self.assertNotIn("contact_email", no_logs)

    def test_send_failure_keeps_report_in_outbox(self):
        with mock.patch.object(cr, "support_url", return_value="https://relay.example/support/report"), \
                mock.patch("requests.post", side_effect=OSError("offline")):
            res = cr.send_report(cr.build_report(kind="contact", message="hello"))
        self.assertFalse(res["ok"])
        self.assertTrue((self.tmp / "support" / "outbox" / res["saved"]).exists())

    def test_send_success_marks_incident(self):
        inc = cr.record_incident("thread", "boom")
        fake = mock.Mock(status_code=200, headers={"content-type": "application/json"})
        fake.json.return_value = {"ok": True, "id": "R-20261126-ABCDEF12"}
        with mock.patch.object(cr, "support_url", return_value="https://relay.example/support/report"), \
                mock.patch("requests.post", return_value=fake) as post:
            res = cr.send_report(cr.build_report(incident_id=inc), incident_id=inc)
        self.assertTrue(res["ok"])
        self.assertEqual(res["report_id"], "R-20261126-ABCDEF12")
        self.assertNotIn("sk-ant", json.dumps(post.call_args.kwargs["json"]))
        self.assertEqual(cr.pending_incidents(), [])

    def test_flask_routes_and_unhandled_errors(self):
        app = Flask(__name__)
        cr.register(app)

        @app.route("/api/boom")
        def boom():
            raise RuntimeError("explosion a1b2c3d4e5f6weirdformat99")

        c = app.test_client()
        r = c.get("/api/boom")
        self.assertEqual(r.status_code, 500)
        inc_id = r.get_json()["incident_id"]
        self.assertTrue(inc_id.startswith("inc_"))
        self.assertEqual(c.get("/nope").status_code, 404)
        pend = c.get("/api/support/incidents").get_json()["incidents"]
        self.assertEqual([p["id"] for p in pend], [inc_id])
        prev = c.post("/api/support/preview", json={"incident_id": inc_id}).get_json()["report"]
        self.assertNotIn("weirdformat99", json.dumps(prev))
        self.assertEqual(c.post("/api/support/send", json={"kind": "contact", "message": "  "}).status_code, 400)
        c.post("/api/support/dismiss", json={"incident_id": inc_id})
        self.assertEqual(c.get("/api/support/incidents").get_json()["incidents"], [])

    def test_support_js_syntax(self):
        node = shutil.which("node") or str(BASE_DIR / "runtime" / "node" / "bin" / "node")
        if not Path(node).exists():
            self.skipTest("node absent")
        res = subprocess.run([node, "--check", str(BASE_DIR / "static" / "js" / "clipoa_support.js")],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)


if __name__ == "__main__":
    unittest.main()
