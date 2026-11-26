import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import menubar, notifier  # noqa: E402


class NotifierTests(unittest.TestCase):
    def tearDown(self):
        notifier._ACTIVE = False

    def test_inactive_until_server_starts(self):
        with mock.patch.object(notifier.sys, "platform", "darwin"), mock.patch("subprocess.Popen") as popen:
            self.assertFalse(notifier.video_done("Titre"))
            popen.assert_not_called()

    def test_text_passed_as_argument_not_code(self):
        notifier.activate()
        evil = 'x" & do shell script "rm -rf ~'
        with mock.patch.object(notifier.sys, "platform", "darwin"), \
                mock.patch.dict(os.environ, {"CLIPOA_NOTIFY": "1"}), mock.patch("subprocess.Popen") as popen:
            self.assertTrue(notifier.video_done(evil))
        args = popen.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/osascript")
        self.assertEqual(args[-1], "Vidéo prête : " + evil)
        self.assertNotIn(evil, " ".join(args[:-1]))
        self.assertNotIn("shell", popen.call_args[1])

    def test_opt_out_and_other_os(self):
        notifier.activate()
        with mock.patch("subprocess.Popen") as popen:
            with mock.patch.object(notifier.sys, "platform", "linux"):
                self.assertFalse(notifier.notify("x"))
            with mock.patch.object(notifier.sys, "platform", "darwin"), mock.patch.dict(os.environ, {"CLIPOA_NOTIFY": "0"}):
                self.assertFalse(notifier.notify("x"))
            with mock.patch.object(notifier.sys, "platform", "win32"), mock.patch.dict(os.environ, {"CLIPOA_NOTIFY": "0"}):
                self.assertFalse(notifier.notify("x"))
            popen.assert_not_called()

    def test_messages(self):
        self.assertEqual(notifier.video_message("Mon short"), "Vidéo prête : Mon short")
        self.assertEqual(notifier.video_message("", "boom"), "Échec du rendu")
        self.assertEqual(notifier.publish_message("published", ["youtube", "tiktok"]), "Publiée sur YouTube, TikTok")
        self.assertEqual(notifier.publish_message("partial", ["youtube"]), "Publiée en partie (YouTube)")
        self.assertEqual(notifier.publish_message("failed", []), "Échec de la publication")
        self.assertEqual(notifier.publish_message("manual_upload", []), "")
        self.assertLessEqual(len(notifier.video_message("a" * 300)), 80)


class MenubarTests(unittest.TestCase):
    def test_summary_running(self):
        s = menubar.summarize([
            {"status": "done", "video_title": "Ancien", "updated_at": 1},
            {"status": "running", "progress": 42, "updated_at": 5},
            {"status": "running", "progress": 10, "updated_at": 3},
        ])
        self.assertEqual(s["title"], "42%")
        self.assertEqual(s["line"], "Rendu en cours : 42% (+1)")
        self.assertTrue(s["busy"])

    def test_summary_ready_and_idle(self):
        self.assertEqual(menubar.summarize([{"status": "done", "video_title": "Les requins", "updated_at": 2}])["line"],
                         "Prête : Les requins")
        self.assertEqual(menubar.summarize([])["line"], "Aucun rendu")
        self.assertEqual(menubar.summarize([{"status": "error"}])["title"], "")

    def test_not_launched_without_mac_or_rumps(self):
        with mock.patch.object(menubar.sys, "platform", "linux"), mock.patch("subprocess.Popen") as popen:
            self.assertIsNone(menubar.launch(8080))
            popen.assert_not_called()
        with mock.patch.object(menubar.sys, "platform", "darwin"), \
                mock.patch.object(menubar.importlib.util, "find_spec", return_value=None), mock.patch("subprocess.Popen") as popen:
            self.assertIsNone(menubar.launch(8080))
            popen.assert_not_called()

    def test_launch_uses_import_not_file(self):
        # compatible Nuitka (--module) : on lance par import, pas par chemin de fichier .py
        with mock.patch.object(menubar.sys, "platform", "darwin"), \
                mock.patch.object(menubar.importlib.util, "find_spec", return_value=object()), \
                mock.patch.dict(os.environ, {"CLIPOA_MENUBAR": "1"}), mock.patch("subprocess.Popen") as popen:
            menubar.launch(8123)
        args = popen.call_args[0][0]
        self.assertEqual(args[1:3], ["-c", "from core.menubar import main; main()"])
        self.assertIn("8123", args)
        self.assertIn(str(os.getpid()), args)

    def test_icon_present(self):
        self.assertTrue(menubar.ICON.exists())


if __name__ == "__main__":
    unittest.main()
