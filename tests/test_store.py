import base64
import subprocess
import unittest
from unittest import mock

from shortcuts import icons, store
from shortcuts.model import Shortcut

PNG = b"\x89PNG\r\n\x1a\n" + b"rest of a png"


def _shortcut(app="orca", sid="orca.new_project"):
    return Shortcut(id=sid, app=app, label="New", combo="ctrl+n", provenance="extracted", source="x")


class PathTestCase(unittest.TestCase):
    def test_the_app_prefix_is_not_repeated_in_the_file_name(self):
        self.assertEqual(store.path_for(_shortcut()), "icons/orca/new_project.png")

    def test_an_id_without_the_prefix_is_left_alone(self):
        self.assertEqual(store.path_for(_shortcut(sid="new_project")), "icons/orca/new_project.png")

    def test_a_hostile_name_cannot_climb_out_of_the_store(self):
        evil = Shortcut(id="../../etc/passwd", app="../..", label="x", combo="ctrl+n",
                        provenance="guessed", source="x")
        path = store.path_for(evil)
        self.assertNotIn("..", path)
        self.assertTrue(path.startswith("icons/"))
        self.assertEqual(path.count("/"), 2)

    def test_the_repo_and_the_store_itself_are_overridable(self):
        with mock.patch.dict("os.environ", {"OPENDECK_ICON_REPO": "someone/else"}):
            self.assertIn("someone/else", store.raw_url(_shortcut()))
        with mock.patch.dict("os.environ", {"OPENDECK_ICON_STORE": "0"}):
            self.assertFalse(store.enabled())
            self.assertIsNone(store.fetch(_shortcut()), "a disabled store makes no request")


class FetchTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict("os.environ", {"OPENDECK_ICON_STORE": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _urlopen(self, body):
        response = mock.MagicMock()
        response.read.return_value = body
        response.__enter__.return_value = response
        return mock.patch.object(store.request, "urlopen", return_value=response)

    def test_a_published_png_comes_back(self):
        with self._urlopen(PNG):
            self.assertEqual(store.fetch(_shortcut()), PNG)

    def test_something_that_is_not_a_png_is_refused(self):
        with self._urlopen(b"<html>404 via a captive portal</html>"):
            self.assertIsNone(store.fetch(_shortcut()))

    def test_an_oversized_body_is_refused(self):
        with self._urlopen(PNG + b"x" * (store.MAX_BYTES + 1)):
            self.assertIsNone(store.fetch(_shortcut()))

    def test_an_unreachable_store_is_not_an_error(self):
        with mock.patch.object(store.request, "urlopen", side_effect=OSError("no route")):
            self.assertIsNone(store.fetch(_shortcut()))


class PublishTestCase(unittest.TestCase):
    def test_an_applications_own_art_may_never_be_published(self):
        with mock.patch.object(store.subprocess, "run") as run:
            self.assertFalse(store.publish(_shortcut(), PNG, "app"))
            self.assertFalse(store.publish(_shortcut(), PNG, "none"))
            run.assert_not_called()

    def test_cached_art_may_be_published_because_app_art_never_reaches_the_cache(self):
        # icons.resolve returns app art directly and only ever caches what it generated or
        # fetched from this store, so a cached PNG is always ours to share.
        import inspect

        from shortcuts import icons
        source = inspect.getsource(icons.resolve)
        self.assertNotIn("_cache_write", source.split('"app"')[0],
                         "app art must not be written to the cache")
        self.assertIn("cache", store.PUBLISHABLE)
        self.assertNotIn("app", store.PUBLISHABLE)

    def test_a_non_png_is_refused_even_when_generated(self):
        with mock.patch.object(store.subprocess, "run") as run:
            self.assertFalse(store.publish(_shortcut(), b"not a png", "generated"))
            run.assert_not_called()

    def test_a_generated_icon_is_put_at_its_readable_path(self):
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            # First call looks up the existing sha; pretend nothing is there yet.
            if "--jq" in args:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            return subprocess.CompletedProcess(args, 0, "{}", "")

        with mock.patch.object(store.shutil, "which", return_value="/usr/bin/gh"), \
             mock.patch.object(store.subprocess, "run", side_effect=fake_run):
            self.assertTrue(store.publish(_shortcut(), PNG, "generated"))
        put = calls[-1]
        self.assertIn("PUT", put)
        self.assertTrue(any("icons/orca/new_project.png" in str(a) for a in put))
        self.assertTrue(any(base64.b64encode(PNG).decode() in str(a) for a in put))

    def test_without_gh_publishing_fails_loudly_rather_than_silently(self):
        with mock.patch.object(store.shutil, "which", return_value=None):
            self.assertFalse(store.publish(_shortcut(), PNG, "generated"))


class AppArtTestCase(unittest.TestCase):
    """An application's own icons: used locally, never published."""

    def test_fetched_app_art_wins_over_the_cache_and_is_not_publishable(self):
        sc = _shortcut(app="onshape", sid="onshape.extrude")
        path = icons.app_art_path(sc)
        self.assertTrue(str(path).endswith("onshape/extrude.png"), path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        with mock.patch.object(icons, "rasterise", return_value=PNG):
            result = icons.resolve(sc)
        self.assertEqual(result.origin, "app")
        self.assertFalse(store.publish(sc, PNG, result.origin),
                         "an application's own art is not ours to redistribute")

    def test_it_is_kept_somewhere_other_than_the_cache(self):
        self.assertNotEqual(icons.app_art_dir(), icons.cache_dir())


class ResolutionOrderTestCase(unittest.TestCase):
    def setUp(self):
        import os
        import shutil as sh
        import tempfile
        self.tmp = tempfile.mkdtemp()
        os.environ["OPENDECK_ICON_CACHE"] = self.tmp
        self.addCleanup(sh.rmtree, self.tmp, True)
        self.addCleanup(os.environ.pop, "OPENDECK_ICON_CACHE", None)

    def test_the_store_is_consulted_before_anything_is_generated(self):
        with mock.patch.object(store, "fetch", return_value=PNG), \
             mock.patch.object(icons, "generate", side_effect=AssertionError("generated anyway")):
            result = icons.resolve(_shortcut(), generate_missing=True)
        self.assertEqual(result.origin, "store")

    def test_what_the_store_gave_us_is_cached_so_it_is_fetched_once(self):
        with mock.patch.object(store, "fetch", return_value=PNG) as fetch:
            self.assertEqual(icons.resolve(_shortcut()).origin, "store")
            self.assertEqual(icons.resolve(_shortcut()).origin, "cache")
            fetch.assert_called_once()

    def test_publishing_is_only_offered_for_what_we_generated(self):
        with mock.patch.object(store, "fetch", return_value=None), \
             mock.patch.object(icons, "generate", return_value=PNG), \
             mock.patch.object(store, "publish", return_value=True) as publish:
            icons.resolve(_shortcut(), generate_missing=True, publish=True)
            publish.assert_called_once()
            args = publish.call_args[0]
            self.assertEqual(args[2], "generated")

    def test_nothing_is_published_unless_asked(self):
        with mock.patch.object(store, "fetch", return_value=None), \
             mock.patch.object(icons, "generate", return_value=PNG), \
             mock.patch.object(store, "publish") as publish:
            icons.resolve(_shortcut(), generate_missing=True)
            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
