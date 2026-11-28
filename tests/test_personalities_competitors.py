import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as clipoa_app  # noqa: E402
from core import edition, personality, settings_store  # noqa: E402


class TestPersonalitiesAndCompetitors(unittest.TestCase):
    def setUp(self):
        clipoa_app.app.config["TESTING"] = True
        clipoa_app._RATE_LIMITER.reset()
        self.client = clipoa_app.app.test_client()

    def test_business_personality_and_five_competitors_gate(self):
        with tempfile.TemporaryDirectory() as td:
            sf = Path(td) / "settings.json"
            with patch.object(settings_store, "SETTINGS_FILE", sf):
                self.assertEqual(personality.get_personality()["mode"], "creator")
                self.assertEqual(personality.build_personality_prompt_block(), "")

                r = self.client.post("/api/personality", json={
                    "mode": "business",
                    "company_name": "Optique du Marché",
                    "industry": "Opticien",
                    "offer": "Réglage gratuit",
                    "cta": "Passe en boutique",
                })
                self.assertEqual(r.status_code, 200)
                data = r.get_json()
                self.assertEqual(data["personality"]["mode"], "business")
                self.assertEqual(len(data["angles"]), 4)
                block = personality.build_personality_prompt_block()
                self.assertIn("Optique du Marché", block)
                self.assertIn("STRUCTURE ENTREPRISE EN 3 TEMPS", block)

                # Save 5 competitors max (6th ignored)
                r_c = self.client.post("/api/competitors", json={
                    "competitors": ["@c1", "@c2", "@c3", "@c4", "@c5", "@c6"]
                })
                self.assertEqual(r_c.status_code, 200)
                self.assertEqual(len(r_c.get_json()["competitors"]), 5)

                brief = personality.build_recipe_inspiration_brief({"title": "Test Viral", "ratio": 3.5, "competitor": "@c1"})
                self.assertIn("INTERDICTION ABSOLUE", brief)
                self.assertIn("Optique du Marché", brief)

                with patch.object(edition, "EDITION", "public"):
                    self.assertEqual(self.client.get("/api/personality").status_code, 200)
                    self.assertEqual(self.client.get("/api/competitors").status_code, 403)
                    self.assertEqual(self.client.post("/api/competitors/scan", json={}).status_code, 403)

    def test_example_or_empty_business_profile_never_becomes_an_ad(self):
        # une fiche restée sur un exemple fictif (« Atelier Nuance ») ou vide ne pousse aucune pub dans les scripts
        for ex in personality.BUSINESS_EXAMPLES:
            prof = dict(ex, mode="business")
            self.assertTrue(personality.is_example_profile(prof))
            self.assertEqual(personality.build_personality_prompt_block(prof), "")
            brief = personality.build_recipe_inspiration_brief({"title": "T", "ratio": 3, "competitor": "@c"}, prof)
            self.assertNotIn(ex["company_name"], brief)
        self.assertEqual(personality.build_personality_prompt_block({"mode": "business", "company_name": " ", "offer": ""}), "")
        self.assertIn("Salon Lila", personality.build_personality_prompt_block(
            {"mode": "business", "company_name": "Salon Lila", "offer": "Coupe offerte"}))

    def test_custom_personalities_crud_and_private_owner_hidden_in_public(self):
        with tempfile.TemporaryDirectory() as td:
            sf = Path(td) / "settings.json"
            with patch.object(settings_store, "SETTINGS_FILE", sf):
                r1 = self.client.post("/api/personalities", json={
                    "name": "Coach Sport",
                    "mission": "Transformer les débutants en 30 jours",
                    "key_points": "Séances 15 min sans matériel",
                    "cta": "Lien en bio",
                    "angles": "Erreur 1 : Pourquoi les abdos ne font pas perdre du ventre",
                })
                self.assertEqual(r1.status_code, 200)
                self.assertEqual(r1.get_json()["personality"]["mode"], "custom")
                self.assertIn("Coach Sport", personality.build_personality_prompt_block())

                r2 = self.client.post("/api/personalities", json={
                    "name": "ClipRoll",
                    "mission": "Promo privée fondateur",
                    "private_owner": True,
                })
                self.assertEqual(r2.status_code, 200)
                priv_id = r2.get_json()["item"]["id"]

                self.assertEqual(len(self.client.get("/api/personalities").get_json()["custom_personalities"]), 2)
                with patch.object(edition, "EDITION", "public"):
                    pub_list = self.client.get("/api/personalities").get_json()["custom_personalities"]
                    self.assertEqual([x["name"] for x in pub_list], ["Coach Sport"])

                self.assertEqual(self.client.delete(f"/api/personalities/{priv_id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
