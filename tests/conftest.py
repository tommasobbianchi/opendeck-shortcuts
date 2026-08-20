"""The suite never touches the network.

Icon resolution now consults the shared store, which is an HTTP fetch. Left on, every test
that resolves an icon would depend on the network being there and on what someone published
today. The store has an off switch for offline machines; the tests use it, and the ones that
are about the store mock the transport explicitly.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _no_icon_store(monkeypatch):
    monkeypatch.setenv("OPENDECK_ICON_STORE", "0")
    yield


os.environ.setdefault("OPENDECK_ICON_STORE", "0")
