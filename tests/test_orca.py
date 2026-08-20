import unittest
from pathlib import Path

from shortcuts import keys
from shortcuts.providers import orca

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "KBShortcutsDialog_excerpt.cpp"


class TestOrcaProvider(unittest.TestCase):
    def _shortcuts(self):
        return orca.shortcuts("orca", cpp_path=str(FIXTURE))

    def test_encodable_entries_and_skips(self):
        scs = self._shortcuts()
        by_label = {s.label: s for s in scs}
        self.assertEqual(
            set(by_label),
            {
                "New Project",
                "Save Project as",
                "Arrange all objects",
                "Deselect all",
                "Delete selected",
                "Move up",
            },
        )
        self.assertEqual(orca.skipped(), 2)

    def test_apple_branch_discarded(self):
        scs = self._shortcuts()
        by_label = {s.label: s for s in scs}
        self.assertEqual(by_label["Delete selected"].combo, "delete")
        self.assertNotIn("fn", " ".join(s.combo for s in scs))
        self.assertNotIn("⌫", " ".join(s.label for s in scs))

    def test_categories(self):
        scs = self._shortcuts()
        self.assertEqual({s.category for s in scs}, {"Global", "Preview"})

    def test_ctrl_shift_s_normalised(self):
        by_label = {s.label: s for s in self._shortcuts()}
        self.assertEqual(by_label["Save Project as"].combo, "ctrl+shift+s")

    def test_all_combos_encode(self):
        for s in self._shortcuts():
            keys.encode(s.combo)

    def test_matches(self):
        self.assertTrue(orca.matches("OrcaBelt2608"))
        self.assertTrue(orca.matches("orca"))
        self.assertFalse(orca.matches("kitty"))

    def test_snapshot_loads_non_empty(self):
        scs = orca.load_snapshot()
        self.assertTrue(scs)
        self.assertTrue(all(s.provenance == "extracted" for s in scs))


if __name__ == "__main__":
    unittest.main()
