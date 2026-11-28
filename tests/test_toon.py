"""Style « Dessin à compteur » : découpe en images, mise en scène IA nettoyée, dessin SVG valide, sous-titres toon."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import toon_kit as K  # noqa: E402
from core import toon_engine as T  # noqa: E402


def _words(n=40, step=0.32):
    return [{"word": f"mot{i}", "start": round(0.1 + i * step, 3), "end": round(0.1 + i * step + 0.25, 3)} for i in range(n)]


class TestPanels(unittest.TestCase):
    def test_panels_cover_duration_and_are_short(self):
        ws = _words()
        dur = ws[-1]["end"] + 0.4
        panels = T.build_panels(ws, dur, [4.0, 8.0])
        self.assertEqual(panels[0]["start"], 0.0)
        self.assertAlmostEqual(panels[-1]["end"], dur, places=2)
        for a, b in zip(panels, panels[1:]):
            self.assertAlmostEqual(a["end"], b["start"], places=3)
        lens = [p["end"] - p["start"] for p in panels]
        self.assertTrue(all(0.4 <= l <= 1.6 for l in lens), lens)
        self.assertTrue(any(abs(p["start"] - 4.0) < 0.4 for p in panels))

    def test_fast_mode_draws_fewer_images(self):
        ws = _words(60)
        hq = T.build_panels(ws, 20.0)
        fast = T.build_panels(ws, 20.0, **T.FAST_PANEL_TIMING)
        self.assertLess(len(fast), len(hq) * 0.75, (len(fast), len(hq)))
        self.assertAlmostEqual(fast[-1]["end"], 20.0, places=2)

    def test_long_silence_is_split(self):
        ws = [{"word": "a", "start": 0.1, "end": 0.3}, {"word": "b", "start": 6.0, "end": 6.3}]
        panels = T.build_panels(ws, 7.0)
        self.assertTrue(all(p["end"] - p["start"] <= T.PANEL_MAX_S + 0.01 for p in panels))


class TestSanitize(unittest.TestCase):
    def test_garbage_returns_none(self):
        self.assertIsNone(T.sanitize({}, 3))
        self.assertIsNone(T.sanitize({"panels": "x"}, 3))

    def test_unknown_values_are_dropped_and_count_matches(self):
        raw = {
            "header": {"title": "<script>alert(1)</script>Ici", "counter_label": "Score", "accent": "rouge"},
            "cast": [{"id": "hero", "skin": "not-a-color", "hair_style": "mohawk", "cap": "#123456", "glasses": 1}],
            "locations": [{"id": "x", "kind": "volcano"}],
            "panels": [{"i": 0, "f": "zoom", "c": [{"id": "hero", "e": "evil", "p": "dab", "n": "12", "g": 5}], "k": "abc"},
                       {"i": 1, "f": "close", "c": [{"id": "ghost"}]}],
        }
        spec = T.sanitize(raw, 4)
        self.assertEqual(len(spec["panels"]), 4)
        self.assertNotIn("<", spec["header"]["title"])
        self.assertEqual(spec["header"]["accent"], K.PINK)
        hero = spec["cast"]["hero"]
        self.assertTrue(hero["skin"].startswith("#"))
        self.assertEqual(hero["hair_style"], "short")
        self.assertEqual(spec["locations"]["x"]["kind"], "park_day")
        p0 = spec["panels"][0]
        self.assertEqual(p0["frame"], "medium")
        self.assertEqual(p0["chars"][0]["expr"], "neutral")
        self.assertEqual(p0["chars"][0]["pose"], "idle")
        self.assertEqual(p0["chars"][0]["counter"], "12")
        self.assertLessEqual(p0["chars"][0]["ghost"], 0.8)
        self.assertIsNone(p0["counter"])
        # perso inconnu -> remplacé par le héros, jamais d'image vide
        self.assertEqual(spec["panels"][1]["chars"][0]["id"], "hero")

    def test_card_without_cards_falls_back(self):
        spec = T.sanitize({"panels": [{"i": 0, "f": "card", "card": "nope"}]}, 1)
        self.assertEqual(spec["panels"][0]["frame"], "close")

    def test_heuristic_spec(self):
        panels = T.build_panels(_words(20), 7.0)
        spec = T.heuristic_spec({"title": "Mon titre"}, panels)
        self.assertEqual(len(spec["panels"]), len(panels))
        self.assertEqual(spec["header"]["title"], "Mon titre")

    def test_prompt_lists_every_panel(self):
        panels = T.build_panels(_words(20), 7.0)
        prompt = T.build_prompt({"title": "t"}, panels)
        self.assertIn(f"EXACTEMENT {len(panels)} entrées", prompt)


class TestDrawing(unittest.TestCase):
    cast = {"a": {"skin": "#F6D3B3", "cap": "#F4B63F", "glasses": True, "hair_style": "curly"},
            "b": {"skin": "#8D5A3B", "cap": None, "hair_style": "long", "top_style": "vest"}}

    def _valid(self, svg):
        ET.fromstring(K.wrap_svg(svg))

    def test_every_expression_pose_and_style_is_valid_svg(self):
        for e in K.EXPRESSIONS:
            for p in K.POSES:
                self._valid(K.character(self.cast["a"], e, p, "10 min", ghost=0.5))
        for hs in K.HAIR_STYLES:
            for ts in K.TOP_STYLES:
                self._valid(K.character({"hair_style": hs, "top_style": ts, "cap": None}))

    def test_every_location_frame_and_prop(self):
        for loc in K.LOCATIONS:
            for fr in ("close", "medium", "wide"):
                pnl = {"frame": fr, "crowd": 4, "_unit": "min",
                       "chars": [{"id": "a", "expr": "laugh", "pose": "wave", "counter": "3", "say": "Oh <là>"},
                                 {"id": "b", "expr": "sad", "pose": "idle"}]}
                self._valid(K.panel_svg(pnl, self.cast, {"kind": loc, "label": "Dortoir & co"}))
        for pr in K.PROPS:
            self._valid(K.panel_svg({"frame": "object", "prop": pr, "prop_label": "Oui"}, self.cast, {"kind": "plain"}))
        card = {"title": "Règlement", "items": [["Article 1", "Tout <le> monde"], ["Article 2", "x"]], "hi": 1, "sign": "Moi"}
        self._valid(K.panel_svg({"frame": "card", "card": card}, self.cast, {}))

    def test_header_escapes_text(self):
        svg = K.header_svg({"title": "A <b> & C", "subtitle": "x", "counter_label": "Score", "counter_unit": "pts"}, 7)
        self._valid(svg)
        self.assertIn("SCORE : 7 PTS", svg)
        self.assertNotIn("<b>", svg)


class TestStyleAndCaptions(unittest.TestCase):
    def test_starter_style_registered(self):
        from core.style_plugins import STARTER_PLUGINS, STARTER_PRODUCTION, sanitize_production
        self.assertIn("compteur_toon", [p["id"] for p in STARTER_PLUGINS])
        prod = STARTER_PRODUCTION["compteur_toon"]
        self.assertEqual(sanitize_production(prod)["visual_style"], "toon_svg")
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "assets", "style_covers", "compteur_toon.jpg")))

    def test_plan_uses_toon_look(self):
        from core import production_method as pm
        from core.style_plugins import STARTER_PRODUCTION
        ws = _words(20)
        plan = pm.build_plan({"title": "t", "full_spoken_script": "x"}, ws, 7.0, None, style_overrides=STARTER_PRODUCTION["compteur_toon"])
        self.assertEqual(plan["captions"]["look"], "toon")
        self.assertEqual(plan["grade"], "clean")

    def test_toon_subtitles_have_no_hook_and_use_toon_style(self):
        from core.video_composer import VideoComposer
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.ass")
            VideoComposer.generate_ass_subtitles(_words(8), p, style_name="toon_pink", hook_text="ACCROCHE",
                                                 notes=[{"text": "NOTE", "start": 0, "end": 1}], look="toon")
            txt = open(p, encoding="utf-8").read()
        self.assertNotIn("ACCROCHE", txt)
        self.assertNotIn(",Note", txt)
        self.assertIn(",Toon,,", txt)
        self.assertIn("pos(540,1500)", txt)
        self.assertIn("&H008C50F0", txt)


if __name__ == "__main__":
    unittest.main()


class TestParable(unittest.TestCase):
    """Parabole à 3 destins : plans longs calés sur les phrases, chapitres, objets qui apparaissent, carton final."""

    def _sentence_words(self):
        text = ("Imagine trois amis. Chacun reçoit cent euros le même jour. Le premier dépense tout très vite. "
                "Le deuxième garde tout dans sa tirelire. Le troisième plante des graines et attend. Et toi, tu fais quoi ?")
        ws, t = [], 0.2
        for w in text.split():
            ws.append({"word": w, "start": round(t, 2), "end": round(t + 0.3, 2)})
            t += 0.42
        return ws, t + 0.5

    def test_panels_are_long_and_cut_on_sentences(self):
        ws, dur = self._sentence_words()
        mp = T.mode_params("parable")
        panels = T.build_panels(ws, dur, [], target=mp["target"], min_len=mp["min"], max_len=mp["max"])
        lens = [p["end"] - p["start"] for p in panels]
        self.assertTrue(all(l <= mp["max"] + 0.01 for l in lens), lens)
        self.assertGreater(sum(lens) / len(lens), 2.0)
        for p in panels[:-1]:
            self.assertRegex(p["text"], r"[.!?]$")

    def test_sanitize_keeps_chapters_pops_and_forces_final_card(self):
        raw = {"cast": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
               "choices": {"items": [{"prop": "plate", "label": "Manger"}, {"prop": "piggy", "label": "<b>Garder"},
                                     {"prop": "volcano", "label": "x"}]},
               "panels": [{"i": 0, "f": "medium", "ch": "N°1 : IL DÉPENSE", "c": [{"id": "a"}],
                           "pops": [{"prop": "coin", "at": "nowhere"}, {"prop": "dragon"}, {"prop": "plant", "at": "left"}]},
                          {"i": 1, "f": "close", "c": [{"id": "b"}]}]}
        spec = T.sanitize(raw, 2, "parable")
        p0, p1 = spec["panels"]
        self.assertEqual(p0["chapter"], "N°1 : IL DÉPENSE")
        self.assertEqual([p["prop"] for p in p0["pops"]], ["coin"])
        self.assertEqual(p0["pops"][0]["at"], "top")
        self.assertEqual(p1["frame"], "choices")
        self.assertEqual(len(p1["choices"]["items"]), 2)
        self.assertNotIn("<", p1["choices"]["items"][1]["label"])
        # mode compteur : rien de tout ça
        self.assertNotIn("chapter", T.sanitize(raw, 2)["panels"][0])

    def test_choices_without_items_falls_back(self):
        spec = T.sanitize({"panels": [{"i": 0, "f": "choices"}]}, 1, "parable")
        self.assertEqual(spec["panels"][0]["frame"], "medium")

    def test_heuristic_and_prompt(self):
        ws, dur = self._sentence_words()
        panels = T.build_panels(ws, dur, [], target=4.2, min_len=2.4, max_len=6.5)
        spec = T.heuristic_spec({"title": "t"}, panels, "parable")
        self.assertEqual(spec["panels"][-1]["frame"], "choices")
        self.assertTrue(any(p["chapter"].startswith("N°") for p in spec["panels"]))
        prompt = T.build_prompt({"title": "t"}, panels, mode="parable")
        self.assertIn(f"EXACTEMENT {len(panels)} entrées", prompt)
        self.assertIn("ET TOI ?", prompt)

    def test_drawing_is_valid_svg(self):
        cast = {"a": {"skin": "#F6D3B3"}}
        for fr in ("close", "medium", "wide"):
            pnl = {"frame": fr, "chars": [{"id": "a", "expr": "happy", "pose": "idle"}],
                   "pops": [{"prop": pr, "label": "1 & 2", "at": at} for pr, at in (("coin", "top"), ("plant", "left"))]}
            ET.fromstring(K.wrap_svg(K.panel_svg(pnl, cast, {"kind": "street"})))
        ch = {"title": "Et <toi> ?", "items": [{"prop": p, "label": "A&B"} for p in ("gift", "piggy", "plant")]}
        ET.fromstring(K.wrap_svg(K.panel_svg({"frame": "choices", "choices": ch}, cast, {})))
        ET.fromstring(K.wrap_svg(K.chapter_svg("N°1 : <il> & co")))

    def test_style_registered(self):
        from core.style_plugins import STARTER_PLUGINS, STARTER_PRODUCTION, sanitize_production
        from core.video_composer import SUBTITLE_STYLES
        self.assertIn("parabole_3_destins", [p["id"] for p in STARTER_PLUGINS])
        prod = sanitize_production(STARTER_PRODUCTION["parabole_3_destins"])
        self.assertEqual(prod["visual_style"], "toon_svg")
        self.assertEqual(prod["toon_mode"], "parable")
        self.assertEqual(prod["caption_mode"], "one_word")
        sub = next(p for p in STARTER_PLUGINS if p["id"] == "parabole_3_destins")["subtitle_style"]
        self.assertIn(sub, SUBTITLE_STYLES)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(__file__), "..", "assets", "style_covers", "parabole_3_destins.jpg")))


class ToonFramingTest(unittest.TestCase):
    def test_wide_poses_fit_inside_frame(self):
        for pose in K.ARM_POSES:
            for x in (240.0, 375.0, 540.0, 705.0, 840.0):
                ext = K._pose_extent(pose)
                nx, sc = K.fit_in_frame(x, 1.45, ext)
                self.assertGreaterEqual(nx - ext[0] * sc, K.EDGE_MARGIN - 0.01, pose)
                self.assertLessEqual(nx + ext[1] * sc, K.W - K.EDGE_MARGIN + 0.01, pose)

    def test_close_shrug_is_scaled_down(self):
        svg = K.panel_svg({"frame": "close", "chars": [{"id": "a", "pose": "shrug"}]}, {"a": {}}, {"type": "camp"})
        self.assertNotIn("scale(2.550)", svg)
