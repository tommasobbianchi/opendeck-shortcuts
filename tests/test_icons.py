import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shortcuts import icons
from shortcuts.model import Shortcut

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _shortcut(id="test.thing", app="test", label="Thing", icon=None):
    return Shortcut(
        id=id, app=app, label=label, combo="ctrl+t",
        provenance="curated", source="", icon=icon,
    )


def _tiny_png() -> bytes:
    from PIL import Image

    im = Image.new("RGB", (1, 1), (200, 200, 200))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestRasterise(unittest.TestCase):
    def test_svg_to_96x96_png(self):
        if shutil.which("convert") is None:
            self.skipTest("ImageMagick convert not installed")
        png = icons.rasterise(FIXTURES / "tiny.svg")
        self.assertIsNotNone(png)
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            self.assertEqual(im.size, (96, 96))

    def test_unreadable_returns_none(self):
        self.assertIsNone(icons.rasterise(FIXTURES / "nope.svg"))


class TestDataUri(unittest.TestCase):
    def test_prefix(self):
        self.assertTrue(icons.to_data_uri(b"abc").startswith("data:image/png;base64,"))


class TestCacheKey(unittest.TestCase):
    def test_stable(self):
        self.assertEqual(icons.cache_key(_shortcut()), icons.cache_key(_shortcut()))

    def test_differs_across_ids(self):
        self.assertNotEqual(icons.cache_key(_shortcut(id="a")), icons.cache_key(_shortcut(id="b")))


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["OPENDECK_ICON_CACHE"] = self.tmp

    def tearDown(self):
        os.environ.pop("OPENDECK_ICON_CACHE", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pre_seeded_cache_yields_cache(self):
        sc = _shortcut()
        path = icons.cache_dir() / f"{icons.cache_key(sc)}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_tiny_png())
        result = icons.resolve(sc)
        self.assertEqual(result.origin, "cache")
        self.assertTrue(result.data_uri.startswith("data:image/png;base64,"))

    def test_no_icon_no_generate_yields_none_without_generate(self):
        sc = _shortcut()
        with mock.patch.object(icons, "generate", side_effect=AssertionError("generate called")):
            result = icons.resolve(sc)
        self.assertEqual(result.origin, "none")
        self.assertIsNone(result.data_uri)


class TestPrompt(unittest.TestCase):
    def test_prompt_mentions_label_and_no_text(self):
        sc = _shortcut(label="New tab")
        prompt = icons.prompt_for(sc)
        self.assertIn("New tab", prompt)
        self.assertIn("no text", prompt.lower())


if __name__ == "__main__":
    unittest.main()
