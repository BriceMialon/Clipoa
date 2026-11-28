"""Style « Carte animée » (geo_map) : manifeste figé, nettoyage des beats écrits par l'IA, branchement du style."""
import json
import unittest

from core import geo_engine as g
from core.style_plugins import STARTER_PLUGINS, STARTER_PRODUCTION, STYLE_DESCRIPTIONS, sanitize_production

GAZ = {"names": {"fra", "france", "rus", "russia", "usa", "usa:alaska", "alaska", "moscow", "bering sea"}, "iso3": ["FRA", "RUS", "USA"]}
SPRITES = ["plane_grey", "ship_grey"]


class TestManifest(unittest.TestCase):
    def test_pinned_and_hashed(self):
        m = g.manifest()
        self.assertRegex(m["commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(m["license"], "MIT")
        self.assertIn("LICENSE", m["files"])
        self.assertIn("CREDITS.md", m["files"])
        for rel, (size, sha) in m["files"].items():
            self.assertTrue(g._safe_rel(rel), rel)
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
            self.assertGreater(size, 0)
        # pas d'images de vidéos de référence (studies/, reference/) : seulement le moteur et ses données libres
        self.assertFalse(any(r.startswith(("studies/", "reference/", "examples/", "projects/")) for r in m["files"]))
        self.assertLess(sum(v[0] for v in m["files"].values()), 80e6)

    def test_safe_rel(self):
        self.assertFalse(g._safe_rel("../etc/passwd"))
        self.assertFalse(g._safe_rel("/etc/passwd"))
        self.assertTrue(g._safe_rel("engine/flags/fr.svg"))


class TestSanitize(unittest.TestCase):
    def _raw(self, beats):
        return {"camera": [{"t": 0, "at": "RUS", "zoom": 12}, {"t": "w3", "at": "USA:Alaska"}], "beats": beats}

    def test_keeps_valid(self):
        beats = [{"t": "w0", "type": "clouds", "dur": 1}, {"t": 0, "type": "skin", "kind": "sat"},
                 {"t": "w2", "type": "fill", "target": "RUS", "color": "#D8111C", "style": "flash"},
                 {"t": "w4+0.3", "type": "label", "text": "Russie", "at": "RUS", "flag": "RUS"},
                 {"t": "w5", "type": "arrow", "from": "Moscow", "to": [-150, 64]}]
        s = g.sanitize(self._raw(beats), 10, GAZ, SPRITES)
        self.assertIsNotNone(s)
        self.assertEqual(len(s["beats"]), 5)
        self.assertEqual(len(s["camera"]), 2)

    def test_drops_unknown_places_types_and_files(self):
        beats = [{"t": 0, "type": "clouds"}, {"t": 0, "type": "skin", "kind": "lava"},
                 {"t": 1, "type": "fill", "target": "Russie"},          # nom français inconnu
                 {"t": 1, "type": "label", "text": "x", "at": "Atlantis"},
                 {"t": 1, "type": "script", "code": "alert(1)"},       # type inconnu
                 {"t": "w99", "type": "pin", "at": "FRA"},             # mot hors voix
                 {"t": 2, "type": "sprite", "sprite": "../../secret"},  # hors bibliothèque
                 {"t": 2, "type": "scene", "image": "../../x.png", "code": "evil"},
                 {"t": 3, "type": "fill", "target": ["FRA", "RUS"], "color": "#fff"},
                 {"t": 3, "type": "sprite", "sprite": "plane_grey", "at": "Bering Sea"}]
        s = g.sanitize(self._raw(beats), 10, GAZ, SPRITES)
        types = [b["type"] for b in s["beats"]]
        self.assertEqual(types, ["clouds", "skin", "scene", "fill", "sprite"])
        self.assertEqual(s["beats"][1]["kind"], "atlas")
        scene = s["beats"][2]
        self.assertNotIn("image", scene)
        self.assertEqual(scene["code"], "mountains")

    def test_none_when_too_little(self):
        self.assertIsNone(g.sanitize({"camera": [], "beats": []}, 5, GAZ, SPRITES))
        self.assertIsNone(g.sanitize("pas un dict", 5, GAZ, SPRITES))

    def test_heuristic_is_valid(self):
        words = [[i * 0.4, i * 0.4 + 0.3, f"m{i}"] for i in range(100)]
        spec = g.heuristic_spec(words, 40.0)
        self.assertGreaterEqual(len(spec["camera"]), 2)
        self.assertEqual(spec["beats"][-1]["type"], "endcard")
        json.dumps(spec)

    def test_words_and_prompt(self):
        kw = g.to_kit_words([{"word": "Pourquoi", "start": 0.0, "end": 0.4}, {"word": "la", "start": 0.45, "end": 0.5}, {"x": 1}])
        self.assertEqual(kw, [[0.0, 0.4, "Pourquoi"], [0.45, 0.5, "la"]])
        p = g.build_prompt({"title": "L'Alaska"}, kw, 30.0)
        self.assertIn("w1:la@0.45", p)
        self.assertIn("ISO3", p)

    def test_parse_json(self):
        self.assertEqual(g._parse_json('voici ```json\n{"camera": [], "beats": []}\n```'), {"camera": [], "beats": []})
        self.assertIsNone(g._parse_json("rien"))


class TestStyleWiring(unittest.TestCase):
    def test_starter_style(self):
        sp = next(p for p in STARTER_PLUGINS if p["id"] == "carte_geo")
        self.assertTrue(sp["starter"])
        self.assertIn("carte_geo", STYLE_DESCRIPTIONS)
        self.assertEqual(STARTER_PRODUCTION["carte_geo"]["visual_style"], "geo_map")
        self.assertEqual(sanitize_production({"visual_style": "geo_map"}).get("visual_style"), "geo_map")


if __name__ == "__main__":
    unittest.main()
