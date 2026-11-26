import base64
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from core import edition
from core import license as lic

# RFC 8032, section 7.1, TEST 2 (message 0x72)
RFC_PK = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
RFC_SIG = bytes.fromhex(
    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
    "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    HAVE_CRYPTO = True
except Exception:  # pragma: no cover
    HAVE_CRYPTO = False


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Ed25519Tests(unittest.TestCase):
    def test_rfc_vector(self):
        self.assertTrue(lic.ed25519_verify(RFC_PK, b"\x72", RFC_SIG))

    def test_rejects_tampered(self):
        self.assertFalse(lic.ed25519_verify(RFC_PK, b"\x73", RFC_SIG))
        bad = bytearray(RFC_SIG); bad[5] ^= 1
        self.assertFalse(lic.ed25519_verify(RFC_PK, b"\x72", bytes(bad)))
        self.assertFalse(lic.ed25519_verify(RFC_PK, b"\x72", b"short"))


class KeyFormatTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(lic.normalize_key(" clipoa-ab12-cd34-ef56 "), "CLIPOA-AB12-CD34-EF56")
        self.assertEqual(lic.normalize_key("CLIPOA-AB12"), "")
        self.assertEqual(lic.normalize_key("x; rm -rf"), "")


@unittest.skipUnless(HAVE_CRYPTO, "cryptography absent")
class TokenTests(unittest.TestCase):
    def setUp(self):
        self.sk = Ed25519PrivateKey.generate()
        self.pk_hex = self.sk.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.dir = tempfile.mkdtemp()
        self.mgr = lic.LicenseManager(self.dir, "https://example.invalid", self.pk_hex)
        self.dev = self.mgr.device_id()
        self.pub = mock.patch.object(edition, "EDITION", "public")
        self.pub.start()

    def tearDown(self):
        self.pub.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def token(self, **over):
        data = {"key": "h", "dev": self.dev, "plan": "monthly", "status": "active",
                "iat": int(time.time()), "exp": int(time.time()) + 7 * 86400}
        data.update(over)
        body = json.dumps(data).encode()
        return _b64(body) + "." + _b64(self.sk.sign(body))

    def test_valid_token(self):
        self.assertIsNotNone(lic.verify_token(self.token(), self.pk_hex, self.dev))

    def test_expired_other_device_or_canceled(self):
        self.assertIsNone(lic.verify_token(self.token(exp=int(time.time()) - 1), self.pk_hex, self.dev))
        self.assertIsNone(lic.verify_token(self.token(dev="autre"), self.pk_hex, self.dev))
        self.assertIsNone(lic.verify_token(self.token(status="canceled"), self.pk_hex, self.dev))

    def test_forged_signature(self):
        other = Ed25519PrivateKey.generate()
        body = json.dumps({"dev": self.dev, "status": "active", "exp": time.time() + 99}).encode()
        forged = _b64(body) + "." + _b64(other.sign(body))
        self.assertIsNone(lic.verify_token(forged, self.pk_hex, self.dev))

    def test_no_pubkey_never_valid(self):
        self.assertIsNone(lic.verify_token(self.token(), "", self.dev))

    def test_activate_and_offline_refresh(self):
        tok = self.token()
        with mock.patch.object(self.mgr, "_post", return_value={"token": tok}):
            st = self.mgr.activate("clipoa-ab12-cd34-ef56")
        self.assertTrue(st["valid"])
        self.assertTrue(self.mgr.can_fabricate())
        # hors ligne : le jeton en cache reste valable
        with mock.patch.object(self.mgr, "_post", side_effect=OSError("offline")):
            self.assertTrue(self.mgr.refresh(force=True)["valid"])
        # abonnement terminé : lecture seule
        with mock.patch.object(self.mgr, "_post", return_value={"revoked": True}):
            st = self.mgr.refresh(force=True)
        self.assertFalse(st["valid"])
        self.assertEqual(st["state"], "expired")

    def test_no_key_state(self):
        st = self.mgr.status()
        self.assertEqual(st["state"], "none")
        self.assertFalse(st["valid"])

    def test_perso_edition_not_required(self):
        with mock.patch.object(edition, "EDITION", "perso"):
            self.assertTrue(self.mgr.can_fabricate())


class AppGateTests(unittest.TestCase):
    def test_public_edition_blocks_fabrication_without_license(self):
        try:
            import app as clipoa_app
        except Exception as e:  # pragma: no cover
            self.skipTest("app non importable : %s" % e)
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.object(edition, "EDITION", "public"), \
                    mock.patch.object(clipoa_app, "LICENSE", lic.LicenseManager(tmp, "https://example.invalid", "")):
                c = clipoa_app.app.test_client()
                self.assertEqual(c.post("/api/make", json={}).status_code, 402)
                self.assertEqual(c.get("/api/license/status").get_json()["state"], "none")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
