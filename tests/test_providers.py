import os
import shutil
import tempfile
import unittest
from pathlib import Path

from shortcuts import providers
from shortcuts.providers import curated, kitty

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "kitty.conf"


class TestKittyProvider(unittest.TestCase):
    def test_reads_fixture(self):
        scs = kitty.shortcuts("kitty", paths=[str(FIXTURE)])
        self.assertEqual(len(scs), 12)
        self.assertTrue(all(s.provenance == "extracted" for s in scs))

    def test_ctrl_shift_o_present_with_kitten_label(self):
        scs = kitty.shortcuts("kitty", paths=[str(FIXTURE)])
        by_combo = {s.combo: s for s in scs}
        self.assertIn("ctrl+shift+o", by_combo)
        self.assertEqual(by_combo["ctrl+shift+o"].label, "Llm terminal open folder")

    def test_label_humanised(self):
        scs = kitty.shortcuts("kitty", paths=[str(FIXTURE)])
        by_combo = {s.combo: s for s in scs}
        self.assertEqual(by_combo["ctrl+shift+c"].label, "Copy to clipboard")
        self.assertEqual(by_combo["ctrl+shift+f"].label, "Hints")
        self.assertEqual(by_combo["ctrl+shift+="].label, "Change font size")


class TestCuratedProvider(unittest.TestCase):
    def test_loads_both_files(self):
        chrome = curated.shortcuts("chrome")
        claude = curated.shortcuts("claude")
        self.assertGreater(len(chrome), 0)
        self.assertGreater(len(claude), 0)
        self.assertTrue(all(s.provenance == "curated" for s in chrome + claude))

    def test_chrome_matches(self):
        self.assertTrue(curated.matches("chrome"))
        self.assertTrue(curated.matches("claude"))
        self.assertFalse(curated.matches("firefox"))


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(FIXTURE, os.path.join(self.tmp, "kitty.conf"))
        self.old = os.environ.get("KITTY_CONFIG_DIRECTORY")
        os.environ["KITTY_CONFIG_DIRECTORY"] = self.tmp

    def tearDown(self):
        if self.old is None:
            os.environ.pop("KITTY_CONFIG_DIRECTORY", None)
        else:
            os.environ["KITTY_CONFIG_DIRECTORY"] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kitty_chrome_returns_both(self):
        scs = providers.resolve("kitty:chrome")
        apps = {s.app for s in scs}
        self.assertIn("kitty", apps)
        self.assertIn("chrome", apps)

    def test_unknown_identity_empty(self):
        self.assertEqual(providers.resolve("nonexistent"), [])


if __name__ == "__main__":
    unittest.main()
