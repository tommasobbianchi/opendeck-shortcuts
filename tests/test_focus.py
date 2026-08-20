import json
import os
import tempfile
import unittest
from pathlib import Path

from shortcuts import focus


class SeenStoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "seen.json"
        os.environ["OPENDECK_FOCUS_SEEN"] = str(self.path)

    def tearDown(self):
        os.environ.pop("OPENDECK_FOCUS_SEEN", None)
        self.tmp.cleanup()

    def _write(self, obj):
        self.path.write_text(json.dumps(obj), encoding="utf-8")

    def test_a_missing_store_is_empty_not_an_error(self):
        self.assertEqual(focus.seen(), {})
        self.assertEqual(focus.identities(), [])

    def test_corrupt_or_wrongly_shaped_stores_read_as_empty(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(focus.seen(), {})
        self._write(["OrcaSlicer"])
        self.assertEqual(focus.seen(), {})

    def test_identities_come_back_most_recently_seen_first(self):
        self._write({"OrcaSlicer": 10, "kitty:claude": 30, "firefox": 20})
        self.assertEqual(focus.identities(), ["kitty:claude", "firefox", "OrcaSlicer"])

    def test_a_published_identity_draws_no_warning(self):
        self._write({"OrcaSlicer": 10})
        self.assertTrue(focus.is_published("OrcaSlicer"))
        self.assertIsNone(focus.warning_for("OrcaSlicer"))

    def test_an_unpublished_identity_is_warned_about_and_gets_a_hint(self):
        self._write({"OrcaSlicer": 10, "OrcaBelt2608": 11, "firefox": 12})
        warning = focus.warning_for("orca")
        self.assertIsNotNone(warning)
        self.assertIn("'orca'", warning)
        # The two Orca classes are the useful part of the message.
        self.assertIn("OrcaBelt2608", warning)
        self.assertIn("OrcaSlicer", warning)
        self.assertNotIn("firefox", warning)

    def test_nothing_published_means_nothing_to_warn_about(self):
        # On a machine where the daemon has never run every name is unknown, and warning on
        # all of them says nothing.
        self.assertIsNone(focus.warning_for("orca"))


if __name__ == "__main__":
    unittest.main()
