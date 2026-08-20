import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from shortcuts import cli, icons


class AutofillTestCase(unittest.TestCase):
    """Catalogue + icons + profile for one identity, in one command."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["OPENDECK_CONFIG"] = self.tmp
        (nested := __import__("pathlib").Path(self.tmp) / "profiles" / "n1-test").mkdir(parents=True)
        self.device = nested.name
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(os.environ.pop, "OPENDECK_CONFIG", None)

    def _profile(self, name):
        import pathlib
        return json.loads((pathlib.Path(self.tmp) / "profiles" / "n1-test" / f"{name}.json").read_text())

    def test_it_fills_keys_from_the_first_key_onwards_and_maps_the_identity(self):
        code = cli.main(["autofill", "chrome", "--limit", "3"])
        self.assertEqual(code, 0)
        data = self._profile("chrome")
        self.assertEqual(sorted(data), ["infobars", "keys", "sliders"])
        filled = [i for i, k in enumerate(data["keys"]) if k]
        self.assertEqual(filled, [3, 4, 5], "the strip's three slots are left alone")
        apps = json.loads((__import__("pathlib").Path(self.tmp) / "applications.json").read_text())
        self.assertEqual(apps["chrome"]["n1-test"], "chrome")

    def test_it_never_fills_more_than_the_deck_has_keys(self):
        cli.main(["autofill", "chrome", "--limit", "99"])
        data = self._profile("chrome")
        self.assertLessEqual(len([k for k in data["keys"] if k]), 15)

    def test_a_dry_run_writes_nothing(self):
        import pathlib
        code = cli.main(["autofill", "chrome", "--limit", "2", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertFalse((pathlib.Path(self.tmp) / "profiles" / "n1-test" / "chrome.json").exists())

    def test_an_identity_nobody_knows_fails_rather_than_writing_an_empty_profile(self):
        with mock.patch("shortcuts.providers.guessed.build", return_value=[]):
            code = cli.main(["autofill", "nosuchapp1234", "--limit", "3"])
        self.assertEqual(code, 1)

    def test_generation_is_off_unless_asked(self):
        with mock.patch.object(icons, "generate", side_effect=AssertionError("generated")):
            self.assertEqual(cli.main(["autofill", "chrome", "--limit", "2"]), 0)


if __name__ == "__main__":
    unittest.main()
