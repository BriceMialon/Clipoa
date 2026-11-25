import json
import tempfile
import unittest
from pathlib import Path

from core import custom_engine as ce

MINI = """<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<canvas id="stage" width="720" height="1280"></canvas>
<script>
const c = document.getElementById('stage').getContext('2d');
window.renderFrame = function (t) {
  c.fillStyle = '#4DA3FF'; c.fillRect(0, 0, 720, 1280);
  const s = (window.CLIPOA.shots || []).find(x => t >= x.start && t < x.end) || {};
  c.fillStyle = '#FFD23F'; c.fillRect(100 + t * 50, 600, 200, 200);
  c.fillStyle = '#000'; c.font = '40px Arial'; c.fillText(s.text || '', 40, 200);
};
window.__ready = true;
</script></body></html>"""


class TestCustomEngine(unittest.TestCase):
    def test_parse_head_and_extract(self):
        raw = '{"tool": "html", "why": "dessin animé toon"}\n```html\n' + MINI + '\n```'
        self.assertEqual(ce._parse_head(raw)["tool"], "html")
        self.assertIn("renderFrame", ce._extract(raw, "html"))
        with self.assertRaises(ValueError):
            ce._extract("```html\n<div></div>\n```", "html")
        bad_py = '{"tool": "blender"}\n```python\nimport bpy\nimport subprocess\n```'
        self.assertEqual(ce._parse_head(bad_py)["tool"], "blender")
        with self.assertRaises(ValueError):
            ce._extract(bad_py, "blender")

    def test_timeline_follows_voice(self):
        words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("Le chef retient. Les pigeons décollent du balcon.".split())]
        plan = {"shots": [{"start": 0.0, "end": 1.5}, {"start": 1.5, "end": 4.0}]}
        tl = ce.build_timeline(words, 4.0, plan, [{"show": {"kind": "text", "text": "DÉCOLLAGE"}}, {}], title="T")
        self.assertEqual(len(tl["shots"]), 2)
        self.assertTrue(tl["shots"][0]["text"].startswith("Le chef"))
        self.assertEqual(tl["shots"][0]["show"]["text"], "DÉCOLLAGE")
        self.assertTrue(tl["lines"])

    def test_contract_mentions_both_tools(self):
        txt = ce.contracts()
        self.assertIn("renderFrame", txt)
        self.assertIn("import bpy", txt)

    def test_html_engine_renders_frames(self):
        try:
            import playwright  # noqa: F401
            from core.cine_setup import find_chrome, _state
            if not (find_chrome() or _state().get("chromium")):
                self.skipTest("aucun navigateur pour le rendu")
        except Exception:
            self.skipTest("playwright absent")
        with tempfile.TemporaryDirectory() as td:
            ep = Path(td) / "ep"
            tl = {"duration": 2.0, "title": "T", "lines": [], "shots": [{"start": 0, "end": 2, "text": "bonjour"}], "palette": {}}
            rep = ce._preview("html", ep, MINI, tl, n=2)
            self.assertEqual(rep["problems"], [])
            self.assertEqual(len(rep["images"]), 2)

    def test_styles_accept_custom_engine(self):
        from core.style_plugins import sanitize_production
        out = sanitize_production({"visual_style": "custom", "fallback_style": "explainer2d"})
        self.assertEqual(out, {"visual_style": "custom", "fallback_style": "explainer2d"})


if __name__ == "__main__":
    unittest.main()
