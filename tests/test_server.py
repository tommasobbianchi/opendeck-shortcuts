import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from shortcuts import server as server_mod


def _request(url, method="GET", body=None, host="127.0.0.1"):
    headers = {"Host": host}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    return urllib.request.urlopen(req)


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["OPENDECK_CONFIG"] = self.tmp
        self.httpd = server_mod.make_server()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        os.environ.pop("OPENDECK_CONFIG", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get_json(self, path):
        with _request(self.base + path) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))


class TestIndex(ServerTestCase):
    def test_serves_picker_html(self):
        with _request(self.base + "/") as resp:
            body = resp.read().decode("utf-8")
        self.assertEqual(resp.status, 200)
        self.assertIn("OpenDeck Shortcuts", body)


class TestShortcuts(ServerTestCase):
    def test_expected_keys_and_collision(self):
        status, data = self._get_json("/api/shortcuts?identity=kitty")
        self.assertEqual(status, 200)
        self.assertGreater(len(data), 0)
        expected = {"id", "label", "combo", "tokens", "provenance", "source",
                    "category", "icon", "app", "collision"}
        self.assertTrue(all(expected <= set(rec) for rec in data))
        self.assertTrue(all(isinstance(rec["collision"], bool) for rec in data))

    def test_collision_flagged_across_segments(self):
        status, data = self._get_json("/api/shortcuts?identity=kitty:claude")
        self.assertEqual(status, 200)
        self.assertTrue(any(rec["collision"] for rec in data))


class TestSecurity(ServerTestCase):
    def test_evil_host_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _request(self.base + "/", host="evil.example")
        self.assertEqual(ctx.exception.code, 403)

    def test_path_traversal_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _request(self.base + "/../../etc/passwd")
        self.assertIn(ctx.exception.code, (404, 403))


class TestApply(ServerTestCase):
    def test_apply_writes_profile_and_mapping(self):
        body = {
            "identity": "chrome",
            "device": "n1-test",
            "assignments": {"3": "chrome.new_tab", "4": None, "5": "chrome.close_tab"},
        }
        with _request(self.base + "/api/apply", method="POST", body=body) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            code = resp.status
        self.assertEqual(code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["written"], 2)

        profile_path = Path(self.tmp) / "profiles" / "n1-test" / "chrome.json"
        saved = json.loads(profile_path.read_text())
        self.assertIsNotNone(saved["keys"][3])
        self.assertEqual(saved["keys"][3]["context"], "Keypad.3.0")
        self.assertIsNone(saved["keys"][4])

        apps = json.loads((Path(self.tmp) / "applications.json").read_text())
        self.assertEqual(apps["chrome"]["n1-test"], "chrome")

    def test_apply_refuses_when_opendeck_running(self):
        body = {"identity": "chrome", "device": "n1-test", "assignments": {"3": "chrome.new_tab"}}
        with mock.patch.object(server_mod.opendeck, "opendeck_running", return_value=True):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                _request(self.base + "/api/apply", method="POST", body=body)
        self.assertEqual(ctx.exception.code, 409)


if __name__ == "__main__":
    unittest.main()


class TestIconRoute(unittest.TestCase):
    """The picker shows artwork from outside the assets directory, so the route that hands it
    over is the one place this tool could become a file-disclosure hole."""

    def test_rejects_paths_outside_the_allowed_roots(self):
        from shortcuts import server

        self.assertIsNone(server.icon_path("/etc/passwd"))
        self.assertIsNone(server.icon_path("resources/images/save.svg"))  # not absolute
        self.assertIsNone(server.icon_path(""))

    def test_rejects_traversal_and_non_images(self):
        from shortcuts import server
        from shortcuts.providers import orca

        tree = orca.source_tree()
        if not tree:
            self.skipTest("no OrcaSlicer checkout on this machine")
        self.assertIsNone(server.icon_path(f"{tree}/resources/../../../../etc/passwd"))

    def test_accepts_an_icon_the_provider_actually_returned(self):
        from shortcuts import server
        from shortcuts.providers import orca

        icons = [s.icon for s in orca.shortcuts("orca") if s.icon]
        if not icons:
            self.skipTest("no icon matches available")
        self.assertIsNotNone(server.icon_path(icons[0]))
