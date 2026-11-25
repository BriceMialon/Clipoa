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
        for pid, key, val in (("fete_en_folie", "caption_mode", "one_word"), ("2d_monde_3d", "character_style", "flat2d"), ("roblox_3d", "shot_max_s", 3.0)):
            pl = StylePluginStore.get_plugin(pid, include_script_body=False)
            if pl:
                self.assertEqual(pl["production"][key], val)

    def test_plan_honours_style(self):
        words, dur = fake_words(SCRIPT)
        plan = pm.build_plan({"full_spoken_script": SCRIPT}, words, dur, [], style_overrides={"caption_mode": "one_word", "keyword_colors": False, "shot_max_s": 3.0, "character_style": "flat2d"})
        self.assertEqual(plan["captions"], {"mode": "one_word", "keyword_colors": False})
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
