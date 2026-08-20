import os
import shutil
import tempfile
import unittest
from unittest import mock

from shortcuts import opendeck


class OpendeckTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["OPENDECK_CONFIG"] = self.tmp

    def tearDown(self):
        os.environ.pop("OPENDECK_CONFIG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestProfileNameFor(OpendeckTestCase):
    def test_colon(self):
        self.assertEqual(opendeck.profile_name_for("kitty:claude"), "kitty_claude")

    def test_run_of_junk_collapsed(self):
        self.assertEqual(opendeck.profile_name_for("kitty:::claude"), "kitty_claude")
        self.assertEqual(opendeck.profile_name_for("a!@#$%^&*()b"), "a_b")

    def test_keeps_allowed_chars(self):
        self.assertEqual(opendeck.profile_name_for("aBc-09_xY"), "aBc-09_xY")

    def test_capped_at_48(self):
        self.assertEqual(len(opendeck.profile_name_for("x" * 100)), 48)


class TestInputKey(OpendeckTestCase):
    def test_shape(self):
        key = opendeck.input_key(5, "Copy", "[Key(Control, Press)]", None)
        self.assertEqual(key["action"]["uuid"], "com.amansprojects.starterpack.inputsimulation")
        self.assertEqual(key["action"]["plugin"], "com.amansprojects.starterpack.sdPlugin")
        self.assertEqual(key["action"]["name"], "Simulate Input")
        self.assertEqual(key["context"], "Keypad.5.0")
        self.assertEqual(key["settings"]["down"], "[Key(Control, Press)]")
        self.assertEqual(key["states"][0]["text"], "Copy")

    def test_absolute_image_path(self):
        key = opendeck.input_key(3, "X", "[]", "icons/foo.png")
        image = key["states"][0]["image"]
        self.assertTrue(os.path.isabs(image))
        self.assertEqual(key["action"]["icon"], image)

    def test_data_uri_preserved(self):
        key = opendeck.input_key(3, "X", "[]", "data:image/png;base64,AAAA")
        self.assertEqual(key["states"][0]["image"], "data:image/png;base64,AAAA")

    def test_no_icon_empty_image(self):
        key = opendeck.input_key(3, "X", "[]", None)
        self.assertEqual(key["states"][0]["image"], "")


class TestSaveProfile(OpendeckTestCase):
    def test_writes_bak_sidecar(self):
        opendeck.save_profile("dev", "pro", {"keys": [None] * 18})
        opendeck.save_profile("dev", "pro", {"keys": [None] * 18, "extra": 1})
        path = opendeck.profile_path("dev", "pro")
        self.assertTrue(path.is_file())
        self.assertTrue(path.with_suffix(path.suffix + ".bak").is_file())

    def test_refuses_when_running(self):
        with mock.patch.object(opendeck, "opendeck_running", return_value=True):
            with self.assertRaises(RuntimeError):
                opendeck.save_profile("dev", "pro", {"keys": [None] * 18})


class TestLoadProfile(OpendeckTestCase):
    def test_missing_file_is_18_slot_empty(self):
        data = opendeck.load_profile("dev", "missing")
        self.assertEqual(data["keys"], [None] * 18)


class TestApplications(OpendeckTestCase):
    def test_absent_is_empty(self):
        self.assertEqual(opendeck.applications(), {})

    def test_map_application_writes_mapping(self):
        opendeck.map_application("kitty:claude", "dev", "kitty_claude")
        self.assertEqual(opendeck.applications()["kitty:claude"]["dev"], "kitty_claude")


class TestDevices(OpendeckTestCase):
    def test_lists_profile_subdirs(self):
        (opendeck._config_dir() / "profiles" / "n1-abc").mkdir(parents=True)
        (opendeck._config_dir() / "profiles" / "n1-def").mkdir(parents=True)
        self.assertEqual(opendeck.devices(), ["n1-abc", "n1-def"])


if __name__ == "__main__":
    unittest.main()
