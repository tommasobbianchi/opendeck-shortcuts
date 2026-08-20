import json
import os
import tempfile
import unittest
from unittest import mock

from shortcuts.providers import guessed, resolve


class CleanTestCase(unittest.TestCase):
    def test_a_combo_the_encoder_rejects_never_reaches_a_key(self):
        raw = {"shortcuts": [
            {"id": "save", "label": "Save", "combo": "Ctrl+S"},
            {"id": "nonsense", "label": "Nonsense", "combo": "banana+7"},
            {"id": "moon", "label": "Moon", "combo": "hyper+moon"},
        ]}
        kept = guessed._clean(raw)
        self.assertEqual([e["id"] for e in kept], ["save"])
        self.assertEqual(kept[0]["combo"], "ctrl+s", "combos are normalised to lower case")

    def test_malformed_entries_are_skipped_rather_than_crashing(self):
        raw = {"shortcuts": ["not a dict", {"id": "x"}, {"id": 1, "label": 2, "combo": 3}, None]}
        self.assertEqual(guessed._clean(raw), [])

    def test_duplicate_combos_collapse_and_the_list_is_capped(self):
        raw = {"shortcuts": [{"id": f"a{i}", "label": "x", "combo": "ctrl+s"} for i in range(5)]}
        self.assertEqual(len(guessed._clean(raw)), 1)
        letters = "abcdefghijklmnopqrstuvwxyz"
        combos = [f"{mod}+{letter}" for mod in ("ctrl", "alt", "ctrl+shift") for letter in letters]
        many = {"shortcuts": [{"id": f"k{i}", "label": "x", "combo": c} for i, c in enumerate(combos)]}
        self.assertEqual(len(guessed._clean(many)), guessed.MAX_SHORTCUTS)

    def test_an_empty_answer_yields_nothing(self):
        self.assertEqual(guessed._clean({}), [])


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["OPENDECK_CATALOGUE"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("OPENDECK_CATALOGUE", None)
        self.tmp.cleanup()

    def test_a_wm_class_is_never_taken_as_a_path(self):
        path = guessed.cache_file("../../etc/passwd")
        self.assertEqual(path.parent, guessed.cache_dir())
        self.assertNotIn("/", path.name[:-5])

    def test_build_caches_what_survived_and_reads_back_as_guessed(self):
        answer = {"response": json.dumps({"shortcuts": [
            {"id": "save", "label": "Save", "combo": "ctrl+s"},
            {"id": "junk", "label": "Junk", "combo": "banana+7"},
        ]})}
        with mock.patch.object(guessed, "_ask", return_value=json.loads(answer["response"])):
            records = guessed.build("inkscape")
        self.assertEqual([r.combo for r in records], ["ctrl+s"])
        self.assertEqual(records[0].provenance, "guessed")
        self.assertEqual(records[0].id, "inkscape.save")

        self.assertTrue(guessed.matches("inkscape"))
        self.assertEqual([r.combo for r in guessed.shortcuts("inkscape")], ["ctrl+s"])

    def test_a_model_that_says_nothing_usable_writes_no_cache(self):
        with mock.patch.object(guessed, "_ask", return_value={"shortcuts": []}):
            self.assertEqual(guessed.build("inkscape"), [])
        self.assertFalse(guessed.matches("inkscape"))

    def test_resolve_only_asks_the_model_when_told_to(self):
        with mock.patch.object(guessed, "build", return_value=[]) as build:
            resolve("inkscape")
            build.assert_not_called()
            resolve("inkscape", build_missing=True)
            build.assert_called_once_with("inkscape")

    def test_resolve_leaves_a_known_app_alone(self):
        # kitty has a real provider, so nothing should be guessed for it.
        with mock.patch.object(guessed, "build", return_value=[]) as build:
            resolve("kitty", build_missing=True)
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
