import unittest
from unittest import mock

from core import elevenlabs_accounts as ea
from core.settings_store import _deep_merge

K1 = "sk_" + "a" * 48
K2 = "sk_" + "b" * 48


class ElevenLabsAccountsTest(unittest.TestCase):
    def setUp(self):
        self.store = {"elevenlabs": {"api_key": K1}}

        def save(upd):
            self.store = _deep_merge(self.store, upd)
            return self.store

        def connect(api_key, enabled=True, **_):
            if api_key == "sk_bad":
                return {"connected": False, "message": "refusée"}
            self.store = _deep_merge(self.store, {"elevenlabs": {"api_key": api_key}})
            return {"connected": True, "tier": "creator"}

        self.patches = [
            mock.patch.object(ea, "load_settings", side_effect=lambda: self.store),
            mock.patch.object(ea, "save_settings", side_effect=save),
            mock.patch.object(ea.VoiceEngine, "get_elevenlabs_key",
                              side_effect=lambda *a: self.store["elevenlabs"].get("api_key", "")),
            mock.patch.object(ea.VoiceEngine, "connect_elevenlabs", side_effect=connect),
            mock.patch.object(ea.VoiceEngine, "get_elevenlabs_status", return_value={"connected": True}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_current_key_listed_without_secret(self):
        accs = ea.list_accounts()
        self.assertEqual(len(accs), 1)
        self.assertTrue(accs[0]["active"])
        self.assertNotIn(K1, str(accs))

    def test_switch_keeps_previous_account(self):
        aid2 = ea.remember(K2, {"tier": "creator"})
        ea.switch(aid2)
        self.assertEqual(self.store["elevenlabs"]["api_key"], K2)
        ids = {a["id"]: a for a in ea.list_accounts()}
        self.assertIn(ea.account_id(K1), ids)          # l'ancien compte n'est pas perdu
        self.assertTrue(ids[aid2]["active"])
        self.assertEqual(ids[aid2]["label"], "Compte creator ···bbbb")
        ea.switch(ea.account_id(K1))
        self.assertEqual(self.store["elevenlabs"]["api_key"], K1)

    def test_unknown_account_refused(self):
        with self.assertRaises(ValueError):
            ea.switch("nope")


if __name__ == "__main__":
    unittest.main()
