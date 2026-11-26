import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import menubar, notifier, onboarding, platform_win, tools_setup, updater  # noqa: E402


class WindowsPlatformTests(unittest.TestCase):
    def test_store_app_detection_env_and_windowsapps_path(self):
        with mock.patch.dict(os.environ, {"CLIPOA_STORE_APP": "1"}):
            self.assertTrue(platform_win.is_store_app())
        with mock.patch.dict(os.environ, {"CLIPOA_STORE_APP": "0"}):
            self.assertFalse(platform_win.is_store_app())
        with mock.patch.dict(os.environ, {"CLIPOA_STORE_APP": ""}, clear=False), \
                mock.patch.object(platform_win.sys, "platform", "win32"):
            self.assertTrue(platform_win.is_store_app(Path(r"C:\Program Files\WindowsApps\BriceMialon.Clipoa_0.1.0\app")))

    def test_default_data_dir_uses_localappdata(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": "/tmp/fake_local"}):
            self.assertEqual(platform_win.default_data_dir(), Path("/tmp/fake_local") / "Clipoa")

    def test_windows_toast_passes_text_via_env_not_command(self):
        notifier.activate()
        try:
            evil = '"; Remove-Item -Recurse ~; #'
            with mock.patch.object(notifier.sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"CLIPOA_NOTIFY": "1"}), \
                    mock.patch("subprocess.Popen") as popen:
                self.assertTrue(notifier.video_done(evil))
            args = popen.call_args[0][0]
            kwargs = popen.call_args[1]
            self.assertEqual(args[0], "powershell.exe")
            self.assertNotIn(evil, " ".join(args))
            self.assertEqual(kwargs["env"]["CLIPOA_TOAST_MSG"], "Vidéo prête : " + evil)
            self.assertEqual(kwargs["creationflags"], platform_win.CREATE_NO_WINDOW)
        finally:
            notifier._ACTIVE = False

    def test_windows_tray_launch_uses_tray_win_module(self):
        with mock.patch.object(menubar.sys, "platform", "win32"), \
                mock.patch.object(menubar.importlib.util, "find_spec", return_value=object()), \
                mock.patch.dict(os.environ, {"CLIPOA_MENUBAR": "1"}), \
                mock.patch("subprocess.Popen") as popen:
            menubar.launch(8123)
        args = popen.call_args[0][0]
        kwargs = popen.call_args[1]
        self.assertEqual(args[1:3], ["-c", "from core.tray_win import main; main()"])
        self.assertEqual(kwargs.get("creationflags"), platform_win.CREATE_NO_WINDOW)


class WindowsUpdaterAndToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()

    def test_updater_disabled_in_msix_store_mode(self):
        with mock.patch.dict(os.environ, {"CLIPOA_STORE_APP": "1"}):
            self.assertFalse(updater.enabled())
            info = updater.check(force=True)
            self.assertFalse(info["enabled"])
            self.assertTrue(info["store_managed"])

    def test_updater_windows_current_version_without_symlinks(self):
        home = self.tmp
        (home / "versions" / "0.1.0").mkdir(parents=True)
        (home / "versions" / "0.2.0").mkdir(parents=True)
        (home / "current_version").write_text("0.1.0\n", encoding="utf-8")
        self.assertEqual(updater.install_home(home / "versions" / "0.1.0"), home)
        with mock.patch.object(updater.sys, "platform", "win32"):
            updater.link_shared(home / "versions" / "0.2.0")  # no-op sans droits admin
            updater.switch_current(home, "0.2.0")
        self.assertEqual((home / "current_version").read_text(encoding="utf-8").strip(), "0.2.0")

    def test_safe_extract_zip_ok_and_blocks_zip_slip(self):
        good = self.tmp / "good.zip"
        with zipfile.ZipFile(good, "w") as zf:
            zf.writestr("blender/blender.exe", b"MZ")
        out = self.tmp / "out_ok"
        out.mkdir()
        tools_setup.safe_extract_zip(good, out)
        self.assertTrue((out / "blender" / "blender.exe").exists())

        bad = self.tmp / "bad.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr("../escape.exe", b"evil")
        out_bad = self.tmp / "out_bad"
        out_bad.mkdir()
        with self.assertRaises(RuntimeError):
            tools_setup.safe_extract_zip(bad, out_bad)
        with self.assertRaises(RuntimeError):
            updater.safe_extract(bad, out_bad)

    def test_auto_setup_does_not_silently_download_in_store_mode(self):
        with mock.patch.dict(os.environ, {"CLIPOA_STORE_APP": "1"}), \
                mock.patch.object(tools_setup, "start_blender_install") as start_bl:
            tools_setup.auto_setup_on_launch()
            start_bl.assert_not_called()

    def test_onboarding_offers_ffmpeg_blender_whisper_install(self):
        st = {
            "tools": {
                "ffmpeg": {"ok": False, "auto": True, "source": "gyan.dev"},
                "whisper": {"ok": False, "auto": True, "source": "Hugging Face"},
                "voice": {"ok": True},
                "blender": {"ok": False, "auto": True, "source": "download.blender.org"},
            }
        }
        res = onboarding.compute(
            tools_status=st, claude_connected=True, renders_count=0,
            unvalidated_count=0, social_accounts={}, oauth_apps={},
        )
        items = {i["id"]: i for i in res["steps"][0]["items"]}
        self.assertTrue(items["ffmpeg"]["can_install"])
        self.assertTrue(items["blender"]["can_install"])
        self.assertTrue(items["whisper"]["can_install"])
        self.assertFalse(items["voice"]["can_install"])


class WindowsPackagingArtifactsTests(unittest.TestCase):
    def test_msix_manifest_is_valid_xml_with_runfulltrust(self):
        manifest = ROOT / "packaging" / "windows" / "AppxManifest.xml"
        self.assertTrue(manifest.exists())
        tree = ET.parse(manifest)
        xml_text = manifest.read_text(encoding="utf-8")
        self.assertIn('Name="runFullTrust"', xml_text)
        self.assertIn('Executable="Clipoa.exe"', xml_text)
        self.assertIsNotNone(tree.getroot())

    def test_windows_packaging_files_and_workflow_exist(self):
        for rel in (
            "packaging/windows/launcher.py",
            "packaging/windows/build_msix.ps1",
            "packaging/windows/install.ps1",
            "packaging/windows/build_web_release.ps1",
            "packaging/windows/STORE_SUBMISSION.md",
            ".github/workflows/build-windows.yml",
        ):
            self.assertTrue((ROOT / rel).exists(), f"Fichier manquant : {rel}")

        # Vérifie que le workflow n'est PAS déclenché à chaque push sur main (quota Windows x2)
        wf = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", wf)
        self.assertNotIn("branches:", wf)

        # Vérifie que build_msix.ps1 exclut bien imageio-ffmpeg (pas de FFmpeg GPL dans le MSIX)
        msix_ps = (ROOT / "packaging/windows/build_msix.ps1").read_text(encoding="utf-8")
        self.assertIn("imageio-ffmpeg", msix_ps)
        self.assertIn("--nofollow-import-to=imageio_ffmpeg", msix_ps)


if __name__ == "__main__":
    unittest.main()
