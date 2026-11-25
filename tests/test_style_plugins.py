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
        self.assertIn("Stickman", html)
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
        # les 4 styles de départ sont toujours là (l'utilisateur peut en avoir créé d'autres depuis une vidéo)
        starters = {"roblox_3d", "2d_monde_3d", "fete_en_folie", "explainer_2d"}
        self.assertEqual(len([p for p in plugins if p["id"] in starters]), 4)

        for pid, expected_img, expected_phrase in (
            ("roblox_3d", "roblox_3d.jpg", "avatars Roblox classiques (R6)"),
            ("2d_monde_3d", "2d_monde_3d.jpg", "Stickman 2.5D"),
            ("fete_en_folie", "fete_en_folie.jpg", "La Tour des Riches"),
            ("explainer_2d", "explainer_2d.jpg", "Explainer 2D pastel"),
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
        ), patch("core.antigravity_bridge.AntigravityBridge.check_status", return_value={"connected": False, "model": "", "models": []}):
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

    def test_antigravity_bridge_blender_validation_and_routes(self):
        from core.antigravity_bridge import AntigravityBridge

        good_bpy = "import bpy\nimport math\nbpy.ops.wm.read_factory_settings(use_empty=True)\n"
        bad_bpy = "import bpy\nimport subprocess\nsubprocess.run(['id'])\n"
        self.assertTrue(AntigravityBridge.validate_blender_script(good_bpy))
        self.assertFalse(AntigravityBridge.validate_blender_script(bad_bpy))
        self.assertFalse(AntigravityBridge.validate_blender_script("print('no bpy')"))

        r_st = self.client.get("/api/antigravity/status")
        self.assertEqual(r_st.status_code, 200)
        st = r_st.get_json()
        self.assertIn("models", st)
        self.assertTrue(len(st["models"]) >= 1)

        with patch("core.antigravity_bridge.AntigravityBridge.check_status", return_value={"connected": True, "model": "gemini-3.1-pro-preview", "models": []}), patch(
            "core.antigravity_bridge.AntigravityBridge.query", return_value="Sélectionne Antigravity et 3D Blender dans la Fabrique."
        ) as mock_aq:
            r_help = self.client.post(
                "/api/assistant/help",
                json={"message": "Comment faire une scène Blender ?", "provider": "antigravity", "model": "gemini-3.1-pro-preview"},
            )
        self.assertEqual(r_help.status_code, 200)
        hdata = r_help.get_json()
        self.assertTrue(hdata["ok"])
        self.assertEqual(hdata["provider"], "antigravity")
        self.assertIn("Blender", hdata["reply"])
        mock_aq.assert_called_once()

    def test_video_script_template_extract_and_routes(self):
        from core.script_template import (
            extract_spoken_script_from_template,
            extract_title_from_template,
        )

        sample_md = """## 1. Fiche projet
| Champ | Valeur |
|---|---|
| Titre | La Tour des Riches |

## 3. Le script
| Temps | Scène | Action | Qui parle | Texte | Façon de le dire | Émotions | Effets sonores | Musique |
|---|---|---|---|---|---|---|---|---|
| 0:00–0:04 | Décharge | Il regarde en haut | Narrateur (VO) | « Dans cette ville, plus t'es riche, plus tu vis haut. » | Calme | Curiosité 3/5 | SFX-01 : vent | MUS-01 : début |
| 0:04–0:07 | Tours | Caméra monte | — | — | — | — | SFX-02 : whoosh | MUS-01 : continue |
| 0:07–0:10 | Décharge | Il sourit | Le garçon | « Et moi j'habite tout en bas. » | Ironique | Malaise 3/5 | — | MUS-01 : continue |
"""
        self.assertEqual(extract_title_from_template(sample_md), "La Tour des Riches")
        spoken = extract_spoken_script_from_template(sample_md)
        self.assertIn("Dans cette ville, plus t'es riche, plus tu vis haut.", spoken)
        self.assertIn("Et moi j'habite tout en bas.", spoken)
        self.assertNotIn("SFX-01", spoken)
        self.assertNotIn("|", spoken)

        with patch("core.antigravity_bridge.AntigravityBridge.check_status", return_value={"connected": True, "model": "gemini-4-neon-medium", "models": []}), patch(
            "core.antigravity_bridge.AntigravityBridge.query", return_value=sample_md
        ):
            r_gen = self.client.post(
                "/api/fabrique/generate-script",
                json={"topic": "La tour des riches", "engine": "antigravity", "model": "gemini-4-neon-medium", "target_duration_sec": 60},
            )
            self.assertEqual(r_gen.status_code, 200)
            g = r_gen.get_json()
            self.assertTrue(g["ok"])
            self.assertEqual(g["title"], "La Tour des Riches")
            self.assertIn("## 3. Le script", g["template_script"])

            r_ref = self.client.post(
                "/api/fabrique/refine-script",
                json={"current_script": sample_md, "instruction": "Rends la fin plus sombre", "engine": "antigravity", "model": "gemini-4-neon-medium"},
            )
            self.assertEqual(r_ref.status_code, 200)
            self.assertTrue(r_ref.get_json()["ok"])

    def test_plugins_crud_sheets_and_script_upload_isolated(self):
        with tempfile.TemporaryDirectory() as td:
            pdir = Path(td) / "plugins"
            pdir.mkdir()
            with patch("core.style_plugins.PLUGINS_DIR", pdir), patch(
                "core.style_plugins.PLUGINS_INDEX_FILE", pdir / "plugins.json"
            ):
                # 0. La création de styles par l'utilisateur est désactivée
                self.assertEqual(self.client.post("/api/plugins", json={"name": "X"}).status_code, 403)
                # 1. Create custom plugin (côté serveur seulement)
                created = StylePluginStore.create_plugin({
                        "name": "Style Manga Noir",
                        "category": "Anime / Manga",
                        "icon": "🖋️",
                        "gradient": "anime",
                        "tagline": "Noir et blanc à fort contraste.",
                        "da_prompt": "Style manga encre noire, trames dynamiques et angles dramatiques.",
                })
                pid = created["id"]
                StylePluginStore.set_hidden(pid, True)
                self.assertNotIn(pid, [p["id"] for p in StylePluginStore.list_plugins()])
                self.assertIsNotNone(StylePluginStore.get_plugin(pid))
                StylePluginStore.set_hidden(pid, False)

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

    def test_timings_custom_templates_sound_and_ui_updates(self):
        from core.timing_tracker import record_actual_timing, get_learned_estimates, estimate_job_seconds
        from core.script_template import extract_shots_from_template

        # 1. Self-learning timing tracker (isolated)
        with tempfile.TemporaryDirectory() as td:
            tfile = Path(td) / "timing_history.json"
            with patch("core.timing_tracker.TIMING_FILE", tfile):
                record_actual_timing("antigravity", "blender3d", 95.0, 60)
                est = get_learned_estimates()
                self.assertIn("antigravity:blender3d", est["baselines_60s"])
                sec = estimate_job_seconds("antigravity", "blender3d", 60)
                self.assertGreater(sec, 20)

        # 2. Custom script templates CRUD (isolated)
        with tempfile.TemporaryDirectory() as td:
            tpl_file = Path(td) / "script_templates.json"
            with patch("core.script_template.CUSTOM_TEMPLATES_FILE", tpl_file):
                r_list = self.client.get("/api/script-templates")
                self.assertEqual(r_list.status_code, 200)
                self.assertTrue(any(t["id"] == "default" for t in r_list.get_json()["templates"]))

                r_add = self.client.post(
                    "/api/script-templates",
                    json={"name": "Template Thriller", "content": "## 1. Hook\n## 2. Scènes\n| Temps | Scène | Texte |\n|---|---|---|\n| 0:00–0:05 | Intro | Salut |"},
                )
                self.assertEqual(r_add.status_code, 200)
                tid = r_add.get_json()["template"]["id"]
                r_del = self.client.delete(f"/api/script-templates/{tid}")
                self.assertEqual(r_del.status_code, 200)

        # 3. Extract shots from template table
        md_shots = """
## 3. Le script
| Temps | Scène | Action | Qui parle | Texte |
|---|---|---|---|---|
| 0:00–0:05 | Village enneigé | Neige tombe | Elias | Bonjour |
| 0:05–0:11 | Miroir couvert | Drap blanc | Elias | Sans un mot |
"""
        shots = extract_shots_from_template(md_shots)
        self.assertEqual(len(shots), 2)
        self.assertEqual(shots[0]["start_s"], 0.0)
        self.assertEqual(shots[1]["end_s"], 11.0)

        # 4. /api/timings + UI HTML verification
        r_tim = self.client.get("/api/timings")
        self.assertEqual(r_tim.status_code, 200)
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("top-el-text", html)
        self.assertNotIn("top-claude-text", html)
        self.assertNotIn("Avec un style", html)
        self.assertNotIn("Dossier créatif local", html)
        self.assertNotIn("Sauvegarder un Preset", html)
        self.assertIn("fab-enable-music", html)
        self.assertIn("fab-enable-sfx", html)
        self.assertIn("reg-quota-7d-right", html)
        self.assertIn("reg-agy-quota-7d-right", html)
        self.assertIn("switchElevenLabsAccount()", html)
        self.assertIn("switchAntigravityAccount()", html)


if __name__ == "__main__":
    unittest.main()
