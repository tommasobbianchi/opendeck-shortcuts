import logging
from typing import Protocol

from ..model import Shortcut
from . import curated, gtk, guessed, kitty, orca

log = logging.getLogger(__name__)


class Provider(Protocol):
    name: str

    def matches(self, segment: str) -> bool: ...

    def shortcuts(self, segment: str) -> list[Shortcut]: ...


# `guessed` is last: it only ever answers from its cache, and a real source that knows the
# same combo outranks it anyway.
PROVIDERS: list = [kitty, curated, orca, gtk, guessed]

_PROVENANCE_RANK = {"extracted": 3, "curated": 2, "guessed": 1}


def resolve(identity: str, build_missing: bool = False) -> list[Shortcut]:
    """Return every shortcut for an identity like ``kitty`` or ``kitty:chrome``.

    Splits on ``:``, asks every matching provider per segment, and de-duplicates
    by ``(app, combo)`` keeping the strongest provenance. A failing provider is
    logged and skipped, never propagated.

    With ``build_missing``, a segment no provider knows anything about is sent to the
    ``guessed`` provider, which asks a local model and caches the answer. It is off by default
    because it takes tens of seconds: an unknown app should cost the caller a decision, not a
    surprise.
    """
    by_key: dict = {}
    for segment in identity.split(":"):
        if not segment:
            continue
        before = len(by_key)
        for provider in PROVIDERS:
            try:
                if not provider.matches(segment):
                    continue
                for sc in provider.shortcuts(segment):
                    key = (sc.app, sc.combo)
                    current = by_key.get(key)
                    if current is None or _PROVENANCE_RANK[sc.provenance] > _PROVENANCE_RANK[current.provenance]:
                        by_key[key] = sc
            except Exception:
                log.exception("provider %s failed for segment %r", getattr(provider, "name", provider), segment)
        if build_missing and len(by_key) == before:
            log.info("nothing known about %r; asking the local model", segment)
            for sc in guessed.build(segment):
                by_key.setdefault((sc.app, sc.combo), sc)
    return list(by_key.values())
