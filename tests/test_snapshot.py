"""The snapshot tool's two load-bearing decisions: what is a secret, and is OpenDeck up.

Both were wrong once. `is_private` decides what reaches a public repository, and
`opendeck_running` guards a restore that overwrites the live configuration -- its first
version matched the name of the /proc symlink ("exe") rather than what it pointed at, so
it answered False every time and a restore ran under a live OpenDeck.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "snapshot", Path(__file__).resolve().parent.parent / "tools" / "snapshot-profiles.py"
)
snapshot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snapshot)


def test_public_urls_are_kept():
    for url in [
        "https://cad.onshape.com/signin",
        "https://mail.google.com/mail/u/0/#inbox",
        "https://www.youtube.com/",
        "https://claude.ai/new",
    ]:
        assert not snapshot.is_private(url), url


def test_private_endpoints_are_secrets():
    for url in [
        "https://8wo2u1cqkgzke7uzjbajnqgipoiyyu8k.ui.nabu.casa/lovelace/0",
        "https://nativedev.tail7d3518.ts.net/mcp",
        "http://100.112.35.102:8099/",  # tailnet: 100.64/10, which ip_address.is_private misses
        "http://192.168.0.144/",
        "http://localhost:8767/",
        "http://printer.local/",
    ]:
        assert snapshot.is_private(url), url


def test_scrub_strips_art_and_redacts_only_the_private_url():
    profile = {
        "keys": [
            {"action": {"icon": "data:image/png;base64,AAAA", "states": [{"image": "data:image/png;base64,BBBB"}]},
             "states": [{"image": "0.png"}],
             "settings": {"down": "https://cad.onshape.com/signin"}},
            {"settings": {"down": "https://private.nabu.casa/x"}},
        ]
    }
    stripped, redacted = snapshot.scrub(profile)
    assert (stripped, redacted) == (2, 1)
    assert profile["keys"][0]["action"]["icon"] == ""
    assert profile["keys"][0]["states"][0]["image"] == "0.png"  # our own art is a filename
    assert profile["keys"][0]["settings"]["down"] == "https://cad.onshape.com/signin"
    assert profile["keys"][1]["settings"]["down"] == snapshot.REDACTED


def test_running_check_reads_the_link_not_its_name(tmp_path):
    proc = tmp_path / "proc"
    (proc / "101").mkdir(parents=True)
    other = tmp_path / "bin" / "bash"
    other.parent.mkdir(parents=True)
    other.touch()
    (proc / "101" / "exe").symlink_to(other)
    assert not snapshot.opendeck_running(proc)

    (proc / "202").mkdir()
    binary = tmp_path / "bin" / "opendeck"
    binary.touch()
    (proc / "202" / "exe").symlink_to(binary)
    assert snapshot.opendeck_running(proc)


def test_running_check_survives_a_process_that_exits(tmp_path):
    proc = tmp_path / "proc"
    (proc / "303").mkdir(parents=True)
    (proc / "303" / "exe").symlink_to(tmp_path / "gone")
    assert not snapshot.opendeck_running(proc)
