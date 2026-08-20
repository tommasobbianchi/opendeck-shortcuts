import unittest

from shortcuts import keys


class TestEncode(unittest.TestCase):
    def test_ctrl_shift_o_example(self):
        expected = (
            "[Key(Control, Press), Key(Shift, Press), "
            "Key(Unicode('o'), Click), Key(Shift, Release), "
            "Key(Control, Release)]"
        )
        self.assertEqual(keys.encode("ctrl+shift+o"), expected)

    def test_f5(self):
        self.assertEqual(keys.encode("f5"), "[Key(F5, Click)]")

    def test_ctrl_shift_equal_uses_unicode(self):
        self.assertIn("Unicode('=')", keys.encode("ctrl+shift+equal"))

    def test_super_return_uses_meta_and_return(self):
        self.assertEqual(
            keys.encode("super+return"),
            "[Key(Meta, Press), Key(Return, Click), Key(Meta, Release)]",
        )

    def test_capital_lowercased(self):
        self.assertEqual(keys.encode("CTRL+SHIFT+O"), keys.encode("ctrl+shift+o"))

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            keys.encode("ctrl+foobar")

    def test_modifiers_only_raises(self):
        with self.assertRaises(ValueError):
            keys.encode("ctrl+shift")

    def test_empty_combo_raises(self):
        with self.assertRaises(ValueError):
            keys.encode("")

    def test_normalise_reorders_modifiers(self):
        self.assertEqual(keys.normalise("shift+ctrl+o"), "ctrl+shift+o")

    def test_normalise_aliases(self):
        self.assertEqual(keys.normalise("control+option+super+enter"), "ctrl+alt+meta+return")


if __name__ == "__main__":
    unittest.main()
