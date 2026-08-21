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
        self.assertEqual(filled, [0, 1, 3, 4, 5],
                         "shortcuts from key 3; the strip carries the two mode buttons")
        apps = json.loads((__import__("pathlib").Path(self.tmp) / "applications.json").read_text())
        self.assertEqual(apps["chrome"]["n1-test"], "chrome")

    def test_it_never_fills_more_than_the_deck_has_keys(self):
        cli.main(["autofill", "chrome", "--limit", "99"])
        data = self._profile("chrome")
        self.assertLessEqual(len([k for k in data["keys"] if k]), 15)

    def test_a_second_page_carries_what_the_first_had_no_room_for(self):
        cli.main(["autofill", "chrome", "--limit", "4"])
        cli.main(["autofill", "chrome", "--limit", "4", "--bank", "2"])
        first = self._profile("chrome")
        second = self._profile("chrome_2")
        shortcuts = lambda d: [k["action"]["tooltip"] for i, k in enumerate(d["keys"])
                               if k and i >= 3]
        self.assertEqual(len(shortcuts(first)), 4)
        self.assertEqual(len(shortcuts(second)), 4)
        self.assertFalse(set(shortcuts(first)) & set(shortcuts(second)), "no shortcut on two pages")

        apps = json.loads((__import__("pathlib").Path(self.tmp) / "applications.json").read_text())
        self.assertEqual(apps["chrome"]["n1-test"], "chrome")
        self.assertEqual(apps["chrome#2"]["n1-test"], "chrome_2")

    def test_every_page_can_be_escaped(self):
        # Being taken to a profile by focus and having no way back to the launcher is the
        # worst failure this tool can produce: the deck looks broken and nothing says why.
        cli.main(["autofill", "chrome", "--limit", "3"])
        keys = self._profile("chrome")["keys"]
        self.assertIn("mode launcher", keys[0]["settings"]["down"])
        self.assertIn("mode contextual", keys[1]["settings"]["down"])
        self.assertEqual(keys[0]["states"][0]["text"], "Launcher")

    def test_a_strip_key_someone_set_by_hand_is_left_alone(self):
        cli.main(["autofill", "chrome", "--limit", "3"])
        import pathlib
        path = pathlib.Path(self.tmp) / "profiles" / "n1-test" / "chrome.json"
        data = json.loads(path.read_text())
        data["keys"][0]["settings"]["down"] = "something the user chose"
        path.write_text(json.dumps(data))
        cli.main(["autofill", "chrome", "--limit", "3"])
        self.assertEqual(self._profile("chrome")["keys"][0]["settings"]["down"],
                         "something the user chose")

    def test_every_page_carries_the_dial(self):
        cli.main(["autofill", "chrome", "--limit", "4"])
        slot = self._profile("chrome")["sliders"][0]
        self.assertEqual(slot["context"], "Encoder.0.0")
        self.assertIn("page next", slot["settings"]["rotate"])
        self.assertEqual(slot["settings"]["down"], "", "a turn pages; a press does not")

    def test_a_page_past_the_end_is_refused_rather_than_written_empty(self):
        code = cli.main(["autofill", "chrome", "--limit", "15", "--bank", "3"])
        self.assertEqual(code, 1)
        import pathlib
        self.assertFalse((pathlib.Path(self.tmp) / "profiles" / "n1-test" / "chrome_3.json").exists())

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
