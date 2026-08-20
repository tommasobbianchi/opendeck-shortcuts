"""The suite never touches the network, and never sees this machine's own icons.

Icon resolution consults the shared store (an HTTP fetch) and the local cache (whatever the
developer happens to have generated). Left alone, a test that resolves an icon would depend on
the network being up, on what somebody published today, and on which icons this machine has
lying around. Both are switched to somewhere empty; the tests that are *about* them set their
own cache directory or mock the transport.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _hermetic_icons(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENDECK_ICON_STORE", "0")
    monkeypatch.setenv("OPENDECK_ICON_CACHE", str(tmp_path / "icons"))
    yield


os.environ.setdefault("OPENDECK_ICON_STORE", "0")
