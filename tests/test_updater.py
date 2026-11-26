import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import updater  # noqa: E402


def _tar(path: Path, members):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            if isinstance(data, tuple):  # ("sym", target)
                info.type = tarfile.SYMTYPE
                info.linkname = data[1]
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()  # macOS : /var -> /private/var

    def test_parse_version(self):
        self.assertGreater(updater.parse_version("0.10.0"), updater.parse_version("0.9.9"))
        self.assertEqual(updater.parse_version("v1.2"), (1, 2))

    def test_safe_url(self):
        self.assertTrue(updater.safe_url("https://dl.clipoa.app"))
        self.assertTrue(updater.safe_url("http://127.0.0.1:8765"))
        self.assertFalse(updater.safe_url("http://dl.clipoa.app"))
        self.assertFalse(updater.safe_url("file:///etc/passwd"))

    def test_dev_checkout_has_no_updates(self):
        self.assertIsNone(updater.install_home(self.tmp))
        self.assertEqual(updater.release_info(self.tmp), {})

    @unittest.skipIf(os.name == "nt", "disposition macOS par symlink (Windows passe par current_version)")
    def test_install_layout_and_switch(self):
        home = self.tmp
        for v in ("0.1.0", "0.2.0", "0.0.9"):
            (home / "versions" / v).mkdir(parents=True)
        (home / "app").symlink_to("versions/0.1.0")
        self.assertEqual(updater.install_home(home / "versions" / "0.1.0"), home)
        updater.switch_current(home, "0.2.0")
        self.assertEqual(os.readlink(home / "app"), "versions/0.2.0")
        updater.prune_versions(home, keep=("0.2.0", "0.1.0"))
        self.assertEqual(sorted(p.name for p in (home / "versions").iterdir()), ["0.1.0", "0.2.0"])

    def test_switch_current_windows_marker(self):
        from unittest.mock import patch
        home = self.tmp
        (home / "versions" / "0.2.0").mkdir(parents=True)
        with patch.object(updater.sys, "platform", "win32"):
            updater.switch_current(home, "0.2.0")
        self.assertEqual((home / "current_version").read_text(encoding="utf-8").strip(), "0.2.0")
        self.assertFalse((home / "current_version.tmp").exists())

    @unittest.skipIf(os.name == "nt", "symlinks macOS (Windows passe par CLIPOA_DATA_DIR)")
    def test_link_shared(self):
        d = self.tmp / "versions" / "1.0.0"
        (d / "storage").mkdir(parents=True)
        updater.link_shared(d)
        self.assertEqual(os.readlink(d / "storage"), "../../data/storage")
        self.assertTrue((d / "venv").is_symlink())

    def test_safe_extract_ok(self):
        a = self.tmp / "ok.tar.gz"
        _tar(a, [("release.json", json.dumps({"version": "1.0.0"}).encode()), ("core/x.txt", b"x")])
        out = self.tmp / "out"
        out.mkdir()
        updater.safe_extract(a, out)
        self.assertEqual(updater.release_info(out)["version"], "1.0.0")

    def test_safe_extract_refuses_escape(self):
        for members in ([("../evil.txt", b"x")], [("/abs.txt", b"x")], [("link", ("sym", "/etc"))]):
            a = self.tmp / "bad.tar.gz"
            _tar(a, members)
            out = self.tmp / "out_bad"
            out.mkdir(exist_ok=True)
            with self.assertRaises(RuntimeError):
                updater.safe_extract(a, out)

    def test_disabled_without_release(self):
        self.assertFalse(updater.enabled())  # copie de développement git
        self.assertFalse(updater.start_update()["ok"])


if __name__ == "__main__":
    unittest.main()
