import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import production_method as pm
from core.sound_designer import SoundDesigner, SFX_LIBRARY, _music_expr
from core.video_composer import VideoComposer
from core.blender_engine import BlenderEngine

SCRIPT = (
    "Dans ma ville, Docteur Shark double ton argent. Et il ne garde jamais rien pour lui. "
    "La boulangère lui a confié 100 euros. Un mois plus tard, elle en a reçu deux cents. "
    "Mais chez nous, on n'avait presque rien. Donc maman lui a tout donné. "
    "La maison était vide. Il ne restait que le carnet. C'était la liste de nos peurs. "
    "Abonne-toi pour ne plus te faire avoir. Toi, tu lui aurais fait confiance ?"
)


def fake_words(text, w_dur=0.32):
    words, t = [], 0.0
    for w in text.split():
        words.append({"word": w, "start": round(t, 2), "end": round(t + w_dur - 0.04, 2)})
        t += w_dur + (0.35 if w.endswith((".", "?", "!")) else 0.0)
    return words, t + 0.3


class TestProductionMethod(unittest.TestCase):
    def setUp(self):
        self.words, self.dur = fake_words(SCRIPT)

    def test_mood_detection(self):
        self.assertEqual(pm.detect_mood("La nuit, le fantôme hurle dans le silence de l'hôpital"), "dark")
        self.assertEqual(pm.detect_mood("Une astuce facile pour gagner du temps"), "upbeat")
        self.assertEqual(pm.detect_mood("Recette de cuisine"), "calm")

    def test_shots_rhythm_2_to_4s_cover_full_duration(self):
        shots = [{"timestamp_approx": "0-3s", "visual": "ville"}, {"timestamp_approx": "3-25s", "visual": "maison vide"}]
        segs = pm.align_shots(shots, self.words, self.dur)
        self.assertEqual(segs[0]["start"], 0.0)
        self.assertAlmostEqual(segs[-1]["end"], round(self.dur, 2), places=1)
        for a, b in zip(segs, segs[1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=2)
        self.assertTrue(all(s["end"] - s["start"] <= 4.6 for s in segs))
        self.assertTrue(all(s["end"] - s["start"] >= 1.5 for s in segs))

    def test_shots_anchor_on_spoken_text(self):
        shots = [{"text": "Dans ma ville", "visual": "a"}, {"text": "La boulangère lui", "visual": "b"}]
        segs = pm.align_shots(shots, self.words, self.dur, max_len=99)
        boul = next(w for w in self.words if w["word"] == "boulangère")
        # « La » précède « boulangère »
        self.assertAlmostEqual(segs[1]["start"], self.words[self.words.index(boul) - 1]["start"], places=2)

    def test_plan_rules(self):
        plan = pm.build_plan({"full_spoken_script": SCRIPT, "twist_text": "C'était la liste"}, self.words, self.dur, [])
        self.assertIsNotNone(plan["twist_t"])
        sfx = plan["sfx"]
        self.assertLessEqual(len(sfx), 20)
        kinds = [e["kind"] for e in sfx]
        self.assertIn("drop", kinds)
        self.assertIn("pop", kinds)  # CTA « Abonne-toi »
        # Silence avant le twist : aucun autre bruitage dans les 0,8 s qui précèdent
        tw = plan["twist_t"]
        self.assertFalse([e for e in sfx if e["kind"] != "drop" and tw - 0.8 < e["at"] < tw + 0.4])
        # Jamais le même bruitage deux fois en moins de 4 s
        for i, a in enumerate(sfx):
            for b in sfx[i + 1:]:
                if a["kind"] == b["kind"]:
                    self.assertGreaterEqual(abs(a["at"] - b["at"]), 4.0)
        kw = plan["keywords"]
        self.assertIn("shark", kw["yellow"])
        self.assertIn("100", kw["yellow"])
        self.assertIn("peurs", kw["red"])
        self.assertIn("double", kw["green"])

    def test_style_overrides(self):
        plan = pm.build_plan({"full_spoken_script": SCRIPT, "production": {"music_db": -20, "mood": "dark"}}, self.words, self.dur, [])
        self.assertEqual(plan["mood"], "dark")
        self.assertEqual(plan["music"]["db"], -20.0)

    def test_notes_at_phrase(self):
        script = {"full_spoken_script": SCRIPT, "on_screen_notes": [{"text": "100 € → 200 €", "at_phrase": "Un mois plus"}]}
        plan = pm.build_plan(script, self.words, self.dur, [])
        self.assertEqual(len(plan["notes"]), 1)
        self.assertGreater(plan["notes"][0]["start"], 3.0)

    def test_sound_designer_command_graph(self):
        plan = pm.build_plan({"full_spoken_script": SCRIPT}, self.words, self.dur, [])
        cmd = SoundDesigner._build_cmd("/tmp/v.wav", "/tmp/o.wav", plan, self.dur, True, True)
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("sidechaincompress", graph)
        self.assertIn("[outa]", graph)
        if plan["twist_t"] is not None:
            self.assertIn("volume=enable='between(t,", graph)
        nomus = SoundDesigner._build_cmd("/tmp/v.wav", "/tmp/o.wav", plan, self.dur, False, True)
        self.assertNotIn("aevalsrc='(", " ".join(nomus))
        for mood in ("dark", "tension", "upbeat", "calm"):
            expr, lp = _music_expr(mood)
            self.assertNotIn("'", expr)
            self.assertGreater(lp, 0)
        self.assertTrue({"whoosh", "coins", "drop", "pop", "impact"} <= set(SFX_LIBRARY))

    def test_ass_keywords_and_notes(self):
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            VideoComposer.generate_ass_subtitles(
                [{"word": "Docteur", "start": 0.1, "end": 0.4}, {"word": "peur.", "start": 0.4, "end": 0.9}],
                ass, hook_text="HOOK",
                keywords={"yellow": ["docteur"], "red": ["peur"], "green": []},
                notes=[{"text": "100 € → 200 €", "start": 1.0, "end": 2.0}],
            )
            content = Path(ass).read_text(encoding="utf-8")
            self.assertIn("Style: Note", content)
            self.assertIn("100 € → 200 €", content)
            self.assertIn("&H003C4CE7", content)  # rouge danger

    def test_blender_timed_shots_compile(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "scene.py")
            timed = [{"start": 0.0, "end": 2.5, "desc": "ville la nuit"}, {"start": 2.5, "end": 5.0, "desc": "visage gros plan"},
                     {"start": 5.0, "end": 8.0, "desc": "ville la nuit", "sub": 1}]
            BlenderEngine.create_roblox_3d_scene("TEST", path, "texte", frames=96, audio_duration_sec=8.0, timed_shots=timed)
            code = Path(path).read_text(encoding="utf-8")
            compile(code, path, "exec")
            self.assertIn("(1, 30, 'drone')", code)
            self.assertIn("(31, 60, 'closeup')", code)
            self.assertIn("'BEZIER'", code)
            self.assertIn("scene.render.fps = 12", code)
            self.assertIn("scene.render.resolution_x = 540", code)


class TestStylesProduction(unittest.TestCase):
    def test_sanitize_and_starter_production(self):
        from core.style_plugins import sanitize_production, StylePluginStore
        clean = sanitize_production({"shot_max_s": "99", "caption_mode": "ONE_WORD", "keyword_colors": "false", "evil": 1, "mood": "x"})
        self.assertEqual(clean, {"shot_max_s": 12.0, "caption_mode": "one_word", "keyword_colors": False})
        for pid, key, val in (("fete_en_folie", "caption_mode", "one_word"), ("2d_monde_3d", "character_style", "flat2d"), ("roblox_3d", "shot_max_s", 3.5)):
            pl = StylePluginStore.get_plugin(pid, include_script_body=False)
            if pl:
                self.assertEqual(pl["production"][key], val)

    def test_plan_honours_style(self):
        words, dur = fake_words(SCRIPT)
        plan = pm.build_plan({"full_spoken_script": SCRIPT}, words, dur, [], style_overrides={"caption_mode": "one_word", "keyword_colors": False, "shot_max_s": 3.0, "character_style": "flat2d"})
        self.assertEqual(plan["captions"]["mode"], "one_word")
        self.assertFalse(plan["captions"]["keyword_colors"])
        self.assertEqual(plan["character_style"], "flat2d")
        self.assertLessEqual(plan["stats"]["max_shot_s"], 3.3)

    def test_one_word_captions(self):
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            words = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.35} for i, w in enumerate("un deux trois".split())]
            VideoComposer.generate_ass_subtitles(words, ass, caption_mode="one_word")
            lines = [l for l in Path(ass).read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue: 0")]
            self.assertEqual(len(lines), 3)
            self.assertFalse(any("DEUX" in l and "TROIS" in l for l in lines))

    def test_whisper_fragments_merged_and_hook_escape(self):
        w = VideoComposer._extract_word_list({"segments": [{"words": [
            {"word": "ce", "start": 0, "end": 0.1}, {"word": "n", "start": 0.1, "end": 0.2}, {"word": "'était", "start": 0.2, "end": 0.4},
            {"word": "abonne", "start": 0.5, "end": 0.7}, {"word": "-toi", "start": 0.7, "end": 0.8}, {"word": "?", "start": 0.8, "end": 0.9}]}]}, "", 1.0)
        self.assertEqual([x["word"] for x in w], ["ce", "n'était", "abonne-toi?"])
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            VideoComposer.generate_ass_subtitles([], ass, hook_text="PERSONNE NE SORT APRÈS MINUIT DANS MA VILLE")
            hook = [l for l in Path(ass).read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue: 1")][0]
            self.assertIn("\\N", hook)
            self.assertNotIn("\\\\N", hook)

    def test_flat2d_and_ai_script_hardening(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "scene.py")
            BlenderEngine.create_roblox_3d_scene("T", path, "nuit", frames=96, audio_duration_sec=8.0, character_style="flat2d", mood="calm")
            code = Path(path).read_text(encoding="utf-8")
            compile(code, path, "exec")
            self.assertIn("FLAT2D = True", code)
            self.assertIn("IS_MELANCHOLY = False", code)
            ai = os.path.join(td, "ai.py")
            Path(ai).write_text("import bpy\nbpy.ops.mesh.primitive_cone_add(vertices=6, radius=1.2, depth=2)\nbpy.ops.mesh.primitive_cylinder_add(radius1=0.3, depth=1)\nscene = bpy.context.scene\nscene.render.image_settings.file_format = 'FFMPEG'\n", encoding="utf-8")
            BlenderEngine._patch_blender5_compat(ai)
            BlenderEngine.enforce_render_settings(ai, 240, fps=12)
            fixed = Path(ai).read_text(encoding="utf-8")
            compile(fixed, ai, "exec")
            self.assertIn("radius1=1.2", fixed)
            self.assertIn("primitive_cylinder_add(radius=0.3", fixed)
            self.assertIn("_cs.render.fps = 12", fixed)
            self.assertIn("_cs.frame_end = 240", fixed)


class TestMethodRender(unittest.TestCase):
    def test_bright_themes_render(self):
        from config import FFMPEG_PATH, RENDERS_DIR
        with tempfile.TemporaryDirectory() as td:
            wav = os.path.join(td, "a.wav")
            subprocess.run([FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1.0", wav], check=True, capture_output=True)
            for theme in ("cinema_gold", "pop_flat"):
                sess = f"test_theme_{theme}"
                try:
                    mp4 = VideoComposer.compose_short(sess, wav, {"title": "T", "full_spoken_script": "ok"}, theme=theme)
                    self.assertTrue(os.path.exists(mp4))
                finally:
                    shutil.rmtree(RENDERS_DIR / sess, ignore_errors=True)

    def test_full_mix_and_two_mp4(self):
        from config import FFMPEG_PATH, RENDERS_DIR
        sess = "test_method_smoke"
        words, dur = fake_words("Dans ma ville. Personne ne sort. Abonne-toi.", 0.3)
        with tempfile.TemporaryDirectory() as td:
            voice = os.path.join(td, "voice.wav")
            subprocess.run([FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "sine=f=220:r=24000", "-t", f"{dur:.2f}", "-ac", "1", voice],
                           check=True, capture_output=True)
            plan = pm.build_plan({"full_spoken_script": "Dans ma ville. Personne ne sort. Abonne-toi."}, words, dur, [])
            mixed, nomus = os.path.join(td, "mixed.wav"), os.path.join(td, "nomus.wav")
            out = SoundDesigner.mix_ambient_and_sfx(voice, mixed, plan=plan, output_no_music_wav=nomus)
            self.assertEqual(out, mixed)
            self.assertTrue(os.path.exists(nomus))
            try:
                mp4 = VideoComposer.compose_short(
                    output_name=sess, audio_path=mixed,
                    script_data={"title": "T", "hook_screen_text": "HOOK", "full_spoken_script": "Dans ma ville"},
                    transcript_data=None, plan=plan, audio_premixed=True, alt_audio_path=nomus,
                )
                self.assertTrue(os.path.exists(mp4))
                self.assertTrue((Path(mp4).parent / "final_short_sans_musique.mp4").exists())
                self.assertTrue((Path(mp4).parent / "production_plan.json").exists())
            finally:
                shutil.rmtree(RENDERS_DIR / sess, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class TestAIRoutingAndScriptPrompt(unittest.TestCase):
    def test_script_routes_use_claude(self):
        from unittest.mock import patch
        import app as clipoa_app
        client = clipoa_app.app.test_client()
        fake_md = "## 1. Fiche projet\n| Champ | Valeur |\n|---|---|\n| Titre | Test |\n"
        with patch("core.claude_bridge.ClaudeBridge.query", return_value=fake_md) as cq, \
             patch("core.claude_bridge.ClaudeBridge.stream_query", return_value=iter([fake_md])) as cs:
            r = client.post("/api/fabrique/generate-script", json={"topic": "Une idée", "engine": "claude", "model": "claude-opus-5-5-medium"})
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            self.assertEqual(cq.call_args.kwargs.get("model"), "opus")
            r = client.post("/api/fabrique/generate-script/stream", json={"topic": "Une idée", "engine": "claude", "model": "claude-opus-5-5-medium"})
            body = r.get_data(as_text=True)
            self.assertIn("event: done", body)
            self.assertTrue(cs.called)
            r = client.post("/api/fabrique/refine-script", json={"current_script": fake_md, "instruction": "plus court", "engine": "claude", "model": "claude-opus-5-5-medium"})
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def test_frontend_only_claude_engine(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("antigravity", html.lower())
        self.assertIn("let reqEngine = 'claude';", html)

    def test_script_prompt_originality_and_full_da(self):
        from core.script_template import build_script_generation_prompt
        long_da = "DA " + ("x" * 5000) + " REGLES_NARRATIVES_FIN"
        sys_p, user_p = build_script_generation_prompt("Un chat qui parle", 60, long_da, avoid_titles=["Dans ma ville, les miroirs sont couverts"])
        self.assertIn("REGLES_NARRATIVES_FIN", user_p)
        self.assertIn("les miroirs sont couverts", user_p)
        self.assertIn("NE PAS les refaire", user_p)
        self.assertIn("exemples de STYLE", sys_p)
        self.assertIn("2 à 4 s", user_p)


class TestLegacyEngineParams(unittest.TestCase):
    def test_old_page_claude_jobs_go_to_claude(self):
        import app as clipoa_app
        norm = clipoa_app._normalize_engine_params
        # anciennes tâches enregistrées avec un moteur retiré : elles repassent toutes sur Claude
        self.assertEqual(norm({"engine": "old_engine", "engine_model": "claude-opus-5-5-medium"})["engine"], "claude")
        self.assertEqual(norm({"engine": "old_engine", "engine_choice": "old_engine"})["engine"], "claude")
        self.assertEqual(norm({"engine": "claude"})["engine"], "claude")

    def test_build_endpoint_and_banner(self):
        import app as clipoa_app
        client = clipoa_app.app.test_client()
        self.assertEqual(client.get("/api/build").get_json()["build"], clipoa_app.APP_BUILD)
        html = client.get("/").get_data(as_text=True)
        self.assertIn("stale-build-banner", html)
        self.assertIn(clipoa_app.APP_BUILD, html)


class TestScriptOriginality(unittest.TestCase):
    def test_da_context_and_write_script_anti_repetition(self):
        from unittest.mock import patch
        from core.style_plugins import StylePluginStore
        from agents.team import LeScenariste
        ctx = StylePluginStore.build_da_context("roblox_3d")
        if ctx:
            self.assertIn("RÈGLE D'ORIGINALITÉ", ctx)
        with patch("core.script_template.recent_video_titles", return_value=["Dans ma ville, on couvre les miroirs quand il neige"]), \
             patch("agents.team.ClaudeBridge.query", return_value='{"title": "x", "full_spoken_script": "y"}') as cq:
            LeScenariste.write_script(topic="vidéo qui fait peur", da_context=ctx or None)
            sent = cq.call_args.args[0]
            self.assertIn("on couvre les miroirs quand il neige", sent)
            self.assertIn("NE PAS les refaire", sent)


class TestSceneDesignerAndKit(unittest.TestCase):
    PLAN = {"mood": "calm", "shots": [{"index": i, "start": i * 2.0, "end": i * 2.0 + 2.0, "desc": d}
                                       for i, d in enumerate(["ville vue de haut", "boutique de fleurs", "gros plan", "maison salon"])]}
    SCRIPT = {"title": "T", "full_spoken_script": "Dans ma ville, elle ouvre une boutique de fleurs. Pourtant tout change."}

    def test_sanitize_rejects_garbage_and_fills_all_shots(self):
        from core import scene_designer as sd
        raw = {"time_of_day": "midnight", "palette": {"sky": "blue", "ground": "#00FF00"},
               "characters": [{"id": "Léa!", "model": "unknown", "shirt": "#zzz"}],
               "locations": [{"id": "shop", "type": "volcano", "props": [{"kind": "rocket"}, {"kind": "tree", "count": 99}]}],
               "shots": [{"i": 0, "camera": "close", "location": "nowhere", "focus": "x", "action": "dance"}]}
        spec = sd._sanitize(raw, 4)
        self.assertEqual(spec["time_of_day"], "day")
        self.assertIsNone(spec["palette"]["sky"])
        self.assertEqual(spec["palette"]["ground"], "#00FF00")
        self.assertEqual(spec["characters"][0]["model"], "villageois_01")
        self.assertEqual(spec["locations"][0]["type"], "street")
        self.assertEqual(spec["locations"][0]["props"], [{"kind": "tree", "count": 6, "color": None, "text": ""}])
        self.assertEqual(len(spec["shots"]), 4)
        self.assertEqual(spec["shots"][0]["action"], "idle")
        for a, b in zip(spec["shots"], spec["shots"][1:]):
            self.assertNotEqual(a["camera"], b["camera"])

    def test_design_scene_falls_back_without_ai(self):
        from unittest.mock import patch
        from core import scene_designer as sd
        with patch("core.claude_bridge.ClaudeBridge.query", side_effect=RuntimeError("quota")):
            spec = sd.design_scene(self.SCRIPT, self.PLAN, style="explainer2d", engine="claude")
        self.assertEqual(spec["_source"], "storyboard")
        self.assertEqual(len(spec["shots"]), 4)
        with patch("core.claude_bridge.ClaudeBridge.query", return_value='```json\n{"characters":[{"id":"lea","model":"villageois_10"}],"locations":[{"id":"shop","type":"shop"}],"shots":[{"i":0,"location":"shop","camera":"wide","focus":"lea"}]}\n```') as aq:
            spec = sd.design_scene(self.SCRIPT, self.PLAN, style="roblox", engine="claude")
        self.assertTrue(aq.called)
        self.assertEqual(spec["_source"], "ia")
        self.assertEqual(spec["characters"][0]["model"], "villageois_10")

    def test_kit_scripts_compile_for_every_style(self):
        from core import scene_designer as sd
        for style in ("roblox", "paper2d", "flat_vector", "explainer2d"):
            spec = sd.heuristic_spec(self.SCRIPT, self.PLAN, style)
            with tempfile.TemporaryDirectory() as td:
                path = os.path.join(td, "s.py")
                BlenderEngine.create_scene_from_spec(spec, self.PLAN["shots"], path, 8.0, style=style)
                code = Path(path).read_text(encoding="utf-8")
                compile(code, path, "exec")
                # haute qualité (défaut) : aplats en Workbench 720x1280 ; roblox/paper2d partent de 540x960 puis EEVEE passe en 720x1280
                hq_res = "720" if style in ("flat_vector", "explainer2d") else "540"
                self.assertIn("scene.render.resolution_x = " + hq_res, code)
                self.assertIn("scene.render.fps = 12", code)
                BlenderEngine.create_scene_from_spec(spec, self.PLAN["shots"], path, 8.0, style=style, quality="fast")
                fast = Path(path).read_text(encoding="utf-8")
                self.assertIn("scene.render.resolution_x = 540", fast)
                self.assertNotIn("_clipoa_hq()", fast)
                self.assertIn("BLENDER_WORKBENCH", code)
                self.assertIn('"_style": "%s"' % style, code.replace("\\\\", "\\").replace('\\"', '"'))
                if style == "explainer2d":
                    self.assertIn('cam_d.type = "ORTHO"', code)

    def test_styles_route_to_blender_and_explainer_exists(self):
        from core.pipeline import ShortCrewPipeline
        from core.style_plugins import StylePluginStore
        self.assertEqual(ShortCrewPipeline.visual_style_for({"production": {"visual_style": "flat_vector"}, "render_mode": "motion"}), "flat_vector")
        self.assertEqual(ShortCrewPipeline.visual_style_for({"production": {"character_style": "flat2d"}, "render_mode": "blender3d"}), "paper2d")
        self.assertIsNone(ShortCrewPipeline.visual_style_for({"production": {}, "render_mode": "motion"}))
        ex = StylePluginStore.get_plugin("explainer_2d", include_script_body=False)
        self.assertIsNotNone(ex)
        self.assertEqual(ex["production"]["visual_style"], "explainer2d")
        # réf. @rosoai : sous-titres par groupes + carton-titre crème
        self.assertEqual(ex["production"]["caption_mode"], "chunk")
        self.assertEqual(ex["production"].get("note_look"), "card")

    def test_drawn_styles_use_2d_characters_and_textures(self):
        with tempfile.TemporaryDirectory() as td:
            spec = {"locations": [{"id": "a", "type": "village"}], "characters": [{"id": "hero", "hair": "#553322", "accessory": "glasses"}],
                    "shots": [{"location": "a", "focus": "hero", "camera": "close", "emotion": "happy", "show": {"kind": "text", "text": "INTERDIT", "color": "#FF0000"}}]}
            for style in ("paper2d", "explainer2d"):
                path = os.path.join(td, style + ".py")
                BlenderEngine.create_scene_from_spec(spec, [{"start": 0.0, "end": 3.0}], path, 3.0, style=style)
                code = Path(path).read_text(encoding="utf-8")
                compile(code, path, "exec")
                self.assertIn("def make_char_2d", code)
                self.assertIn("def build_face_2d", code)
                self.assertIn("def show_item", code)
                self.assertIn("INTERDIT", code)
            paper = Path(os.path.join(td, "paper2d.py")).read_text(encoding="utf-8")
            self.assertIn("p2_apply_textures", paper)
            self.assertIn("LOCKED_TRACK", paper)
            roblox = os.path.join(td, "roblox.py")
            BlenderEngine.create_scene_from_spec(spec, [{"start": 0.0, "end": 3.0}], roblox, 3.0, style="roblox")
            self.assertNotIn("def make_char_2d", Path(roblox).read_text(encoding="utf-8"))

    def test_style_preview_reference_and_example(self):
        import json as _json
        from unittest import mock
        import core.style_plugins as sp
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            refs = tdp / "style_refs"
            refs.mkdir()
            with mock.patch.object(sp, "PLUGINS_DIR", tdp / "plugins"), mock.patch.object(sp, "PLUGINS_INDEX_FILE", tdp / "plugins" / "plugins.json"), \
                    mock.patch.object(sp, "REMOVED_STARTERS_FILE", tdp / "plugins" / "removed.json"), mock.patch.object(sp, "STYLE_REFS_DIR", refs):
                store = sp.StylePluginStore
                self.assertEqual(store.style_preview("roblox_3d", tdp / "renders")["kind"], "none")
                # un lien seul n'est jamais montré (pas de renvoi vers le site d'origine)
                store.update_plugin("roblox_3d", {"reference_url": "https://www.tiktok.com/@x/video/7708402726627052832"})
                self.assertEqual(store.style_preview("roblox_3d", tdp / "renders")["kind"], "none")
                # un rendu fait dans ce style devient l'exemple
                rd = tdp / "renders" / "make_1"
                rd.mkdir(parents=True)
                (rd / "final_short.mp4").write_bytes(b"x")
                (rd / "metadata.json").write_text(_json.dumps({"plugin_id": "roblox_3d"}), encoding="utf-8")
                pv = store.style_preview("roblox_3d", tdp / "renders")
                self.assertEqual((pv["kind"], pv["url"]), ("video", "/stream/make_1"))
                self.assertNotIn("source_url", pv)
                # la vidéo livrée avec ClipRoll passe avant tout
                (refs / "roblox_3d.mp4").write_bytes(b"0")
                pv = store.style_preview("roblox_3d", tdp / "renders")
                self.assertEqual(pv["url"], "/api/plugins/roblox_3d/reference-video")
                # les rendus d'avant la refonte du style ne servent pas d'exemple
                rd2 = tdp / "renders" / "make_2"
                rd2.mkdir()
                (rd2 / "final_short.mp4").write_bytes(b"x")
                (rd2 / "metadata.json").write_text(_json.dumps({"plugin_id": "2d_monde_3d"}), encoding="utf-8")
                os.utime(rd2 / "final_short.mp4", (1000, 1000))
                self.assertEqual(store.style_preview("2d_monde_3d", tdp / "renders")["kind"], "none")
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        self.assertEqual(c.post("/api/plugins/roblox_3d/reference-video", json={"url": "https://e.com"}).status_code, 405)
        html = c.get("/").get_data(as_text=True)
        self.assertNotIn('data-splaque="3d"', html)
        self.assertNotIn('data-splaque="broll"', html)
        self.assertNotIn("ap-ref-file", html)

    def test_starter_updates_only_replace_untouched_values(self):
        import json as _json
        from unittest import mock
        import core.style_plugins as sp
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td) / "plugins"
            tdp.mkdir()
            idx = tdp / "plugins.json"
            idx.write_text(_json.dumps([
                {"id": "roblox_3d", "name": "3D Roblox", "subtitle_style": "submagic_yellow", "da_prompt": "# STYLE BIBLE — « In this town / Dans ma ville » ancien"},
                {"id": "2d_monde_3d", "name": "2D", "subtitle_style": "neon_green"},
            ]), encoding="utf-8")
            with mock.patch.object(sp, "PLUGINS_DIR", tdp), mock.patch.object(sp, "PLUGINS_INDEX_FILE", idx), mock.patch.object(sp, "REMOVED_STARTERS_FILE", tdp / "r.json"):
                rob = sp.StylePluginStore.get_plugin("roblox_3d", include_script_body=False)
                self.assertEqual(rob["subtitle_style"], "clean_white")
                self.assertIn("Conte en blocs", rob["da_prompt"])
                self.assertEqual(sp.StylePluginStore.get_plugin("2d_monde_3d", include_script_body=False)["subtitle_style"], "neon_green")

    def test_two_words_captions_and_new_subtitle_styles(self):
        from core.video_composer import SUBTITLE_STYLES
        self.assertIn("clean_white", SUBTITLE_STYLES)
        self.assertIn("warm_cream", SUBTITLE_STYLES)
        words = [{"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate("un deux trois quatre cinq".split())]
        chunks = VideoComposer._chunk_words(words, max_words=2)
        self.assertTrue(all(len(c) <= 2 for c in chunks))
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            VideoComposer.generate_ass_subtitles(words, ass, caption_mode="two_words", notes=[{"text": "1770", "start": 0.0, "end": 1.0}],
                                                 note_color="#3B2A20", note_look="card")
            content = Path(ass).read_text(encoding="utf-8")
            self.assertIn(",NoteCard,", content)
        plan = pm.build_plan({"full_spoken_script": SCRIPT}, words, 2.0, [], style_overrides={"caption_mode": "two_words", "note_look": "card"})
        self.assertEqual(plan["captions"]["mode"], "two_words")
        self.assertEqual(plan["captions"]["note_look"], "card")

    def test_caption_none_keeps_only_labels(self):
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            VideoComposer.generate_ass_subtitles([{"word": "Bonjour", "start": 0.1, "end": 0.5}], ass, caption_mode="none",
                                                 notes=[{"text": "PRÈS DE 80 %", "start": 1.0, "end": 2.0}], note_color="#D9406E")
            content = Path(ass).read_text(encoding="utf-8")
            self.assertNotIn("BONJOUR", content)
            self.assertIn("PRÈS DE 80 %", content)
            self.assertIn("&H6E40D9&", content)


class TestStyleFromReference(unittest.TestCase):
    def test_measure_and_sheets(self):
        from config import FFMPEG_PATH
        from core.style_analyzer import measure_video, make_sheets, _parse
        with tempfile.TemporaryDirectory() as td:
            mp4 = os.path.join(td, "v.mp4")
            subprocess.run([FFMPEG_PATH, "-y", "-f", "lavfi", "-i", "color=c=red:s=180x320:d=2", "-f", "lavfi", "-i", "color=c=blue:s=180x320:d=2",
                            "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-r", "12", mp4], check=True, capture_output=True)
            st = measure_video(mp4)
            self.assertAlmostEqual(st["duration_s"], 4.0, delta=0.3)
            self.assertEqual(st["shots"], 2)
            sheets = make_sheets(mp4, Path(td) / "a", st["duration_s"])
            self.assertEqual(len(sheets), 2)
            self.assertTrue((Path(td) / "a" / "cover.jpg").exists())
        self.assertEqual(_parse('bla ```json\n{"name": "X"}\n``` fin'), {"name": "X"})

    def test_create_style_from_reference_registers_blender_style(self):
        from unittest.mock import patch
        from core import style_analyzer
        from core.style_plugins import StylePluginStore
        fake = {"analysis": {"name": "Pastel Test Unique", "icon": "🌷", "tagline": "t", "renderer": "explainer2d",
                             "tool_guess": "After Effects", "da_prompt": "# DA\nvectoriel", "narrative_rules": "1. accroche",
                             "production": {"caption_mode": "none", "shot_max_s": 5, "note_color": "#D9406E"}},
                "stats": {"duration_s": 40, "shots": 8, "avg_shot_s": 5.0}, "sheets": [], "cover": "", "meta": {"uploader": "x"},
                "vision": True, "words_per_s": 2.6, "source_url": "https://example.com/v"}
        pid = None
        try:
            from core import custom_engine
            with patch.object(style_analyzer, "analyze_reference", return_value=fake), \
                    patch.object(custom_engine, "design_style_engine", side_effect=RuntimeError("hors ligne")):
                made = style_analyzer.create_style_from_reference("https://example.com/v")
            pid = made["plugin"]["id"]
            pl = StylePluginStore.get_plugin(pid, include_script_body=False)
            self.assertEqual(pl["render_mode"], "blender3d")
            self.assertEqual(pl["production"]["visual_style"], "explainer2d")
            self.assertEqual(pl["production"]["caption_mode"], "none")
            self.assertIn("After Effects", pl["da_prompt"])
        finally:
            if pid:
                StylePluginStore.delete_plugin(pid)

    def test_clone_uses_custom_engine_when_written(self):
        from unittest.mock import patch
        from core import style_analyzer, custom_engine
        from core.style_plugins import StylePluginStore
        fake = {"analysis": {"name": "Toon Test Unique", "icon": "🎈", "tagline": "t", "renderer_scores": {"explainer2d": 9, "paper2d": 3},
                             "tool_guess": "Blender toon", "da_prompt": "# DA\ncartoon", "narrative_rules": "1. accroche",
                             "palette": {"sky": "#4DA3FF"}, "time_of_day": "day", "production": {}},
                "stats": {"duration_s": 30, "shots": 8, "avg_shot_s": 3.0}, "sheets": [], "cover": "", "meta": {"uploader": "x"},
                "vision": True, "words_per_s": 2.6, "source_url": "https://example.com/v2", "words": []}
        pid = None
        try:
            with patch.object(style_analyzer, "analyze_reference", return_value=fake), \
                    patch.object(custom_engine, "design_style_engine", return_value={"tool": "html", "why": "toon"}):
                made = style_analyzer.create_style_from_reference("https://example.com/v2", hidden=True)
            pid = made["plugin"]["id"]
            raw = StylePluginStore.get_plugin(pid, include_script_body=False)
            self.assertEqual(raw["production"]["visual_style"], "custom")
            self.assertEqual(raw["production"]["fallback_style"], "explainer2d")
            self.assertEqual(raw["production"]["palette"], {"sky": "#4DA3FF"})
            self.assertNotIn(pid, [p["id"] for p in StylePluginStore.list_plugins()])
        finally:
            if pid:
                StylePluginStore.delete_plugin(pid)

    def test_make_like_validation(self):
        import app as clipoa_app
        c = clipoa_app.app.test_client()
        self.assertEqual(c.post("/api/make-like", json={"topic": "x"}).status_code, 400)
        self.assertEqual(c.post("/api/make-like", json={"url": "https://youtube.com/shorts/abc"}).status_code, 400)
        self.assertEqual(c.post("/api/plugins/from-reference", json={"url": "https://youtube.com/shorts/abc"}).status_code, 403)
        # Le formulaire n'apparaît qu'une fois Claude connecté : on simule une IA connectée
        # (sur la CI aucune IA n'est branchée).
        from unittest.mock import patch
        real_status = clipoa_app.ClaudeBridge.check_status(live_probe=False)
        with patch.object(clipoa_app.ClaudeBridge, "check_status", return_value={**real_status, "connected": True}):
            html = c.get("/").get_data(as_text=True)
        self.assertIn('id="fab-ref-url"', html)
        self.assertNotIn('data-splaque="new_plugin"', html)
        self.assertIn("syncRefUrlLock", html)


class TestCloneAccuracy(unittest.TestCase):
    def test_renderer_picked_from_scores(self):
        from core.style_analyzer import pick_renderer
        self.assertEqual(pick_renderer({"renderer": "paper2d", "renderer_scores": {"paper2d": 4, "explainer2d": 8, "roblox": 1}}), "explainer2d")
        self.assertEqual(pick_renderer({"renderer": "roblox"}), "roblox")
        self.assertEqual(pick_renderer({}), "explainer2d")

    def test_production_keeps_palette_light_and_hud(self):
        from core.style_plugins import sanitize_production
        out = sanitize_production({"palette": {"sky": "4da3ff", "ground": "#zzzzzz"}, "time_of_day": "day", "hud": "true", "hud_color": "#ffd23f"})
        self.assertEqual(out["palette"], {"sky": "#4DA3FF"})
        self.assertEqual((out["time_of_day"], out["hud"], out["hud_color"]), ("day", True, "#FFD23F"))

    def test_hud_timeline_and_ass(self):
        words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("ils décollent du balcon puis montent très haut".split())]
        script = {"hud": [{"at_phrase": "ils décollent", "lines": ["ALTITUDE : 5 M"]}, {"at_phrase": "montent très", "lines": ["ALTITUDE : 9 000 M", "VITESSE : MACH 8"]}]}
        hud = pm.plan_hud(script, 4.0, words)
        self.assertEqual(len(hud), 2)
        self.assertEqual(hud[0]["end"], hud[1]["start"])
        self.assertEqual(hud[1]["end"], 4.0)
        with tempfile.TemporaryDirectory() as td:
            ass = os.path.join(td, "s.ass")
            VideoComposer.generate_ass_subtitles(words, ass, hud=hud, hud_color="#FFD23F")
            content = Path(ass).read_text(encoding="utf-8")
            self.assertIn(",Hud,", content)
            self.assertIn("ALTITUDE : 9 000 M", content)

    def test_shot_show_sanitized(self):
        from core.scene_designer import _sanitize_show
        self.assertEqual(_sanitize_show({"kind": "car", "color": "#ff0000"})["kind"], "car")
        self.assertEqual(_sanitize_show({"kind": "fusée", "text": "décollage"})["text"], "DÉCOLLAGE")
        self.assertIsNone(_sanitize_show({"kind": "text"}))

