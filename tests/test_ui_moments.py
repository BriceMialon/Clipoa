"""Micro-interactions « UI moments » : suivi par étapes et maintenir pour confirmer."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js" / "cliproll_moments.js"
CSS = ROOT / "static" / "css" / "cliproll-moments.css"
INDEX = ROOT / "templates" / "index.html"


def _node():
    bundled = ROOT / "runtime" / "node" / "bin" / "node"
    if bundled.exists():
        return str(bundled)
    return shutil.which("node")


class UiMomentsTest(unittest.TestCase):
    def setUp(self):
        self.html = INDEX.read_text(encoding="utf-8")

    def test_assets_are_loaded(self):
        self.assertIn("/static/js/cliproll_moments.js", self.html)
        self.assertIn("/static/css/cliproll-moments.css", self.html)
        self.assertTrue(CSS.exists())

    def test_mit_notice_kept(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2026 guanmo-ai", notice)
        self.assertIn("guanmo-ai/ui-moments", JS.read_text(encoding="utf-8"))

    def test_deletions_use_hold_confirm(self):
        # Les suppressions ne passent plus par la fenêtre confirm() du navigateur.
        for line in self.html.splitlines():
            if re.search(r"(?<![\w.])confirm\(", line):
                self.assertNotRegex(line, r"Supprimer|Retirer", line.strip())
        self.assertGreaterEqual(self.html.count("ClipRollMoments.holdConfirm("), 7)

    def test_publish_now_is_hold_button(self):
        self.assertIn("ClipRollMoments.holdify(document.getElementById('btn-pub-now')", self.html)

    def test_old_step_pills_replaced(self):
        self.assertNotIn("2. Voix & Whisper", self.html)
        self.assertIn("ClipRollMoments.stepsHtml(job)", self.html)

    def _run_steps(self, job):
        node = _node()
        if not node:
            self.skipTest("node introuvable")
        script = (
            "global.window = global; global.document = {};"
            f"require({json.dumps(str(JS))});"
            f"process.stdout.write(JSON.stringify(window.ClipRollMoments.computeSteps({json.dumps(job)})));"
        )
        out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
        return json.loads(out.stdout)

    def test_js_syntax(self):
        node = _node()
        if not node:
            self.skipTest("node introuvable")
        proc = subprocess.run([node, "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_steps_follow_step_marker(self):
        steps = self._run_steps({"progress": 70, "step": "🧊 [3/4] Rendu Blender en cours… image 10/40"})
        self.assertEqual([s["state"] for s in steps], ["done", "done", "active", "todo"])
        self.assertAlmostEqual(steps[2]["fill"], (70 - 55) / 40, places=3)

    def test_steps_fallback_on_percentage(self):
        steps = self._run_steps({"progress": 45, "step": "Calage des sous-titres"})
        self.assertEqual([s["state"] for s in steps], ["done", "active", "todo", "todo"])

    def test_clone_has_five_steps(self):
        steps = self._run_steps({"progress": 46, "step": "🧠 [3/5] Le Cloneur extrait la recette virale...", "kind": "clone"})
        self.assertEqual(len(steps), 5)
        self.assertEqual(steps[2]["state"], "active")

    def test_finished_job_all_done(self):
        steps = self._run_steps({"progress": 100, "step": "✅ Short prêt !"})
        self.assertTrue(all(s["state"] == "done" for s in steps))


if __name__ == "__main__":
    unittest.main()
