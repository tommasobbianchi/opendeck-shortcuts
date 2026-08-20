import pathlib
import unittest

from shortcuts import keys
from shortcuts.providers import gtk

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "nautilus-shortcuts-dialog.ui"


class AcceleratorTestCase(unittest.TestCase):
    """GTK's own notation, translated into what the encoder speaks."""

    def test_modifiers_and_plain_keys(self):
        self.assertEqual(gtk.parse_accelerator("<Primary>O"), "ctrl+o")
        self.assertEqual(gtk.parse_accelerator("<Primary><shift>N"), "ctrl+shift+n")
        self.assertEqual(gtk.parse_accelerator("<alt><Primary>O"), "alt+ctrl+o")
        self.assertEqual(gtk.parse_accelerator("F2"), "f2")
        self.assertEqual(gtk.parse_accelerator("Return"), "return")
        self.assertEqual(gtk.parse_accelerator("<shift>Delete"), "shift+delete")

    def test_keysym_names_become_the_character_they_mean(self):
        self.assertEqual(gtk.parse_accelerator("<Primary>period"), "ctrl+.")
        self.assertEqual(gtk.parse_accelerator("<Primary>Page_Up"), "ctrl+page_up")

    def test_what_is_not_a_single_chord_is_refused(self):
        self.assertIsNone(gtk.parse_accelerator("<alt>0...8"), "a range is not a key")
        self.assertIsNone(gtk.parse_accelerator("<Nonsense>X"), "an unknown modifier")
        self.assertIsNone(gtk.parse_accelerator(""), "nothing at all")
        self.assertIsNone(gtk.parse_accelerator("<Primary>"), "a modifier with no key")


class ShortcutsWindowTestCase(unittest.TestCase):
    """Nautilus 49's real shortcuts window, as shipped inside /usr/bin/nautilus."""

    def setUp(self):
        self.rows = gtk.shortcuts_from_ui(FIXTURE.read_text(), "org.gnome.Nautilus", "fixture")

    def test_it_finds_the_shortcuts_the_application_documents(self):
        self.assertGreater(len(self.rows), 30)
        by_combo = {r.combo: r.label for r in self.rows}
        self.assertEqual(by_combo["f2"], "Rename")
        self.assertEqual(by_combo["ctrl+shift+n"], "Create Folder")
        self.assertEqual(by_combo["shift+delete"], "Delete Permanently")

    def test_every_combo_it_returns_can_actually_be_sent(self):
        for row in self.rows:
            keys.encode(row.combo)   # raises if the encoder disagrees

    def test_an_item_with_no_accelerator_is_skipped_not_invented(self):
        # "Undo" and "New Window" are listed by action name only: the user binds them.
        labels = {r.label for r in self.rows}
        self.assertNotIn("Undo", labels)
        self.assertNotIn("New Window", labels)
        self.assertIn("Rename", labels)

    def test_provenance_is_extracted_because_the_app_said_so(self):
        self.assertTrue(all(r.provenance == "extracted" for r in self.rows))
        self.assertTrue(all(r.id.startswith("org.gnome.Nautilus.") for r in self.rows))

    def test_one_chord_per_action_even_when_several_are_offered(self):
        # "Open" lists "Return <Primary>O"; the key gets the first that encodes.
        opens = [r for r in self.rows if r.label == "Open"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(opens[0].combo, "return")

    def test_rubbish_is_reported_rather_than_crashing(self):
        self.assertEqual(gtk.shortcuts_from_ui("<not xml", "x", "y"), [])


if __name__ == "__main__":
    unittest.main()
