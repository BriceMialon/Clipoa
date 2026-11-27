import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from core import night_factory as nf
from core.night_factory import NightFactory, week_slots, next_free_slot


class NightFactoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.renders = root / "renders"
        self.renders.mkdir()
        self.p1 = mock.patch.object(nf, "NIGHT_QUEUE_FILE", root / "night.json")
        self.p2 = mock.patch.object(nf, "RENDERS_DIR", self.renders)
        self.p3 = mock.patch.object(NightFactory, "start_worker", lambda *a, **k: None)
        self.p4 = mock.patch.object(NightFactory, "_set_awake", lambda *a, **k: None)
        for p in (self.p1, self.p2, self.p3, self.p4):
            p.start()
        self.jobs = {}
        self.launched = []
        self.scheduled = []

        def launcher(task):
            jid = f"job_{len(self.launched)}"
            self.launched.append(task["topic"])
            self.jobs[jid] = {"status": "running", "progress": 30, "step": "Rendu"}
            return jid

        def scheduler(task, meta, when):
            self.scheduled.append((task["session_id"], when, tuple(task["publish_platforms"])))
            return "post_x"

        NightFactory.configure(launcher=launcher, job_reader=lambda j: self.jobs.get(j), scheduler=scheduler)

    def tearDown(self):
        for p in (self.p1, self.p2, self.p3, self.p4):
            p.stop()
        NightFactory._launcher = NightFactory._job_reader = NightFactory._scheduler = None
        self.tmp.cleanup()

    def _make_render(self, sid, validated):
        d = self.renders / sid
        d.mkdir()
        (d / "final_short.mp4").write_bytes(b"x")
        (d / "metadata.json").write_text(json.dumps({"validated": validated, "script": {"title": "T"}}))

    def test_week_slots_next_monday_to_friday(self):
        fri = datetime(2026, 11, 27, 9, 0)
        self.assertEqual(week_slots(5, "18:30", fri),
                         ["2026-11-30T18:30", "2026-12-01T18:30", "2026-12-02T18:30", "2026-12-03T18:30", "2026-12-04T18:30"])
        self.assertEqual(week_slots(1, "18:00", datetime(2026, 11, 30, 8))[0], "2026-12-07T18:00")

    def test_next_free_slot_skips_past_and_weekend(self):
        self.assertEqual(next_free_slot("2026-12-04T18:00", datetime(2026, 12, 4, 20)), "2026-12-07T18:00")
        self.assertEqual(next_free_slot("2026-12-04T18:00", datetime(2026, 12, 1, 8)), "2026-12-04T18:00")

    def test_one_at_a_time_and_validation_before_scheduling(self):
        NightFactory.enqueue_batch(["A", "B"], publish_platforms=["youtube"], publish_time="18:00")
        NightFactory.tick()
        NightFactory.tick()
        self.assertEqual(self.launched, ["A"])  # B attend la fin de A

        self.jobs["job_0"].update(status="done", session_id="sess_a")
        self._make_render("sess_a", validated=False)
        NightFactory.tick()
        tasks = NightFactory.load_tasks()
        self.assertEqual(tasks[0]["status"], "waiting_validation")
        self.assertEqual(self.launched, ["A", "B"])
        self.assertEqual(self.scheduled, [])  # pas de publication sans validation

        (self.renders / "sess_a" / "metadata.json").write_text(json.dumps({"validated": True}))
        NightFactory.tick()
        self.assertEqual(len(self.scheduled), 1)
        self.assertEqual(NightFactory.load_tasks()[0]["status"], "scheduled")

    def test_quota_pause_keeps_slot_busy(self):
        NightFactory.enqueue_batch(["A", "B"])
        NightFactory.tick()
        self.jobs["job_0"]["status"] = "paused_quota"
        NightFactory.tick()
        self.assertEqual(self.launched, ["A"])
        self.assertIn("quota", NightFactory.load_tasks()[0]["step"])

    def test_legacy_auto_publish_is_ignored(self):
        NightFactory.enqueue_batch(["A"], auto_publish_platforms=["youtube"], engine="gemini")
        t = NightFactory.load_tasks()[0]
        self.assertEqual(t["publish_platforms"], [])
        self.assertNotIn("auto_publish_platforms", t)
        NightFactory.tick()
        self.jobs["job_0"].update(status="done", session_id="s")
        NightFactory.tick()
        self.assertEqual(NightFactory.load_tasks()[0]["status"], "done")
        self.assertEqual(self.scheduled, [])

    def test_launch_refused_marks_error_and_continues(self):
        NightFactory.configure(launcher=mock.Mock(side_effect=RuntimeError("Abonnement inactif")))
        NightFactory.enqueue_batch(["A"])
        NightFactory.tick()
        t = NightFactory.load_tasks()[0]
        self.assertEqual(t["status"], "error")
        self.assertIn("Abonnement", t["error"])

    def test_cancel_running_never_schedules(self):
        NightFactory.enqueue_batch(["A", "B"], publish_platforms=["youtube"])
        NightFactory.tick()
        a_id = NightFactory.load_tasks()[0]["id"]
        NightFactory.cancel_task(a_id)
        NightFactory.tick()
        self.assertEqual(self.launched, ["A"])  # A tourne encore : B attend
        self.jobs["job_0"].update(status="done", session_id="sess_a")
        self._make_render("sess_a", validated=True)
        NightFactory.tick()
        self.assertEqual(NightFactory.load_tasks()[0]["status"], "cancelled_done")
        self.assertEqual(self.scheduled, [])
        self.assertEqual(self.launched, ["A", "B"])


if __name__ == "__main__":
    unittest.main()
