import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as clipoa_app
from core.style_plugins import StylePluginStore


class TestStylePluginsAndCleanRemoval(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        self.client = clipoa_app.app.test_client()
        clipoa_app._RATE_LIMITER.reset()

    def test_no_docteur_shark_references_in_html_or_routes(self):
        # Isolate social accounts file so personal OAuth channel names don't mask template checks
        with tempfile.TemporaryDirectory() as td:
            with patch("core.social_publisher.ACCOUNTS_FILE", Path(td) / "social_accounts.json"):
                r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        low = html.lower()
        self.assertNotIn("docteur shark", low)
        self.assertNotIn("docshark", low)
        self.assertNotIn("shark-3d-wrap", low)
        self.assertIn("view-plugins", html)
        self.assertIn("modal-plugin-editor", html)
        self.assertIn("ai-taskbar", html)
        self.assertIn("3D Roblox", html)
        self.assertIn("2D × Monde 3D", html)
        self.assertIn("Fête en folie", html)
        self.assertIn("roblox_3d.jpg", html)
        self.assertIn("2d_monde_3d.jpg", html)
        self.assertIn("fete_en_folie.jpg", html)

        # Old Docteur Shark route must be gone
        r_old = self.client.post("/api/docshark/create", json={"topic": "test"})
        self.assertEqual(r_old.status_code, 404)

    def test_starter_styles_ready_with_images_and_metrics(self):
        from core.style_plugins import duration_to_word_range, estimate_plugin_cost_and_time

        r = self.client.get("/api/plugins")
        self.assertEqual(r.status_code, 200)
        plugins = r.get_json()["plugins"]
        self.assertEqual(len(plugins), 3)

        for pid, expected_img, expected_phrase in (
            ("roblox_3d", "roblox_3d.jpg", "avatars Roblox classiques (R6)"),
            ("2d_monde_3d", "2d_monde_3d.jpg", "Conte cartoon 2D dans un monde 3D"),
            ("fete_en_folie", "fete_en_folie.jpg", "La Tour des Riches"),
        ):
            pl = next((p for p in plugins if p["id"] == pid), None)
            self.assertIsNotNone(pl, f"Missing starter plugin {pid}")
            self.assertEqual(pl["status"], "ready")
            self.assertTrue(pl["has_da"])
            self.assertTrue(pl["cover_url"].endswith(expected_img))
            self.assertEqual(pl["est_base_duration_sec"], 60)
            self.assertGreater(pl["est_total_tokens"], 1500)
            self.assertTrue(pl["est_time_label"])

            img_res = self.client.get(pl["cover_url"])
            self.assertEqual(img_res.status_code, 200)
            self.assertGreater(len(img_res.data), 5000)
            img_res.close()

            ctx = StylePluginStore.build_da_context(pid, preserve_user_script=True)
            self.assertIn(expected_phrase, ctx)
            self.assertIn("SON PROPRE SCRIPT", ctx)

        # Duration scaling check (30s < 60s < 120s)
        w30 = duration_to_word_range(30)
        w60 = duration_to_word_range(60)
        w120 = duration_to_word_range(120)
        self.assertLess(w30["max_words"], w60["min_words"])
        self.assertLess(w60["max_words"], w120["min_words"])
        m30 = estimate_plugin_cost_and_time(plugins[0], sheets_count=1, duration_sec=30)
        m120 = estimate_plugin_cost_and_time(plugins[0], sheets_count=1, duration_sec=120)
        self.assertLess(m30["est_time_sec"], m120["est_time_sec"])
        self.assertLess(m30["est_total_tokens"], m120["est_total_tokens"])

    def test_assistant_help_taskbar_endpoint(self):
        # 1. When neither provider is connected -> clean needs_connection response
        with patch("core.claude_bridge.ClaudeBridge.check_status", return_value={"connected": False, "model": "opus"}), patch(
            "core.gemini_studio.GeminiStudio.get_status", return_value={"connected": False, "model": "gemini-3-flash-preview"}
        ):
            r = self.client.post("/api/assistant/help", json={"message": "Comment créer un short ?", "provider": "auto"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data["ok"])
        self.assertTrue(data["needs_connection"])

        # 2. When Claude is connected & user chooses Claude Haiku -> routes to ClaudeBridge.query with model="haiku"
        with patch("core.claude_bridge.ClaudeBridge.check_status", return_value={"connected": True, "model": "opus"}), patch(
            "core.gemini_studio.GeminiStudio.get_status", return_value={"connected": False, "model": "gemini-3-flash-preview"}
        ), patch("core.claude_bridge.ClaudeBridge.query", return_value="Va dans Fabrique et clique sur Fabriquer.") as mock_cq:
            r = self.client.post(
                "/api/assistant/help",
                json={"message": "Comment créer ?", "provider": "claude", "model": "haiku", "current_view": "accueil"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["provider"], "claude")
        self.assertEqual(data["model"], "haiku")
        self.assertIn("Fabrique", data["reply"])
        self.assertEqual(mock_cq.call_args.kwargs.get("model"), "haiku")

        # 3. When Gemini is connected & user chooses Gemini -> routes to GeminiStudio.chat_text
        with patch("core.claude_bridge.ClaudeBridge.check_status", return_value={"connected": False, "model": "opus"}), patch(
            "core.gemini_studio.GeminiStudio.get_status", return_value={"connected": True, "model": "gemini-3-flash-preview"}
        ), patch("core.gemini_studio.GeminiStudio.chat_text", return_value="Choisis un style dans Plugins DA.") as mock_gq:
            r = self.client.post(
                "/api/assistant/help",
                json={"message": "Où sont les styles ?", "provider": "gemini", "model": "gemini-3-flash-preview"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["provider"], "gemini")
        self.assertIn("Plugins DA", data["reply"])
        mock_gq.assert_called_once()

    def test_plugins_crud_sheets_and_script_upload_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td) / "plugins"
            pdir.mkdir()
            with patch("core.style_plugins.PLUGINS_DIR", pdir), patch(
                "core.style_plugins.PLUGINS_INDEX_FILE", pdir / "plugins.json"
            ):
                # 1. Create custom plugin
                r_create = self.client.post(
                    "/api/plugins",
                    json={
                        "name": "Style Manga Noir",
                        "category": "Anime / Manga",
                        "icon": "🖋️",
                        "gradient": "anime",
                        "tagline": "Noir et blanc à fort contraste.",
                        "da_prompt": "Style manga encre noire, trames dynamiques et angles dramatiques.",
                    },
                )
                self.assertEqual(r_create.status_code, 200)
                pid = r_create.get_json()["plugin"]["id"]

                # 2. Upload valid PNG model sheet
                fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
                r_up = self.client.post(
                    f"/api/plugins/{pid}/sheets",
                    data={"role": "personnages", "files": (io.BytesIO(fake_png), "heros_planche.png")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(r_up.status_code, 200)
                pl = r_up.get_json()["plugin"]
                self.assertEqual(pl["sheets_count"], 1)
                self.assertTrue(pl["cover_url"])
                self.assertEqual(pl["status"], "ready")

                # 3. Reject disallowed sheet extension
                r_bad = self.client.post(
                    f"/api/plugins/{pid}/sheets",
                    data={"files": (io.BytesIO(b"print(1)"), "malware.py")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(r_bad.status_code, 400)

                # 4. Upload generator script file
                r_sc = self.client.post(
                    f"/api/plugins/{pid}/script",
                    data={"file": (io.BytesIO(b"# render manga\nprint('ok')\n"), "render_manga.py")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(r_sc.status_code, 200)
                self.assertTrue(r_sc.get_json()["plugin"]["has_script"])

                # 5. Path traversal on sheet endpoint blocked
                self.assertIn(self.client.get(f"/api/plugins/{pid}/sheets/..%2F..%2Fetc%2Fpasswd").status_code, (400, 404))

                # 6. Delete plugin
                r_del = self.client.delete(f"/api/plugins/{pid}")
                self.assertEqual(r_del.status_code, 200)
                self.assertTrue(r_del.get_json()["deleted"])


if __name__ == "__main__":
    unittest.main()
