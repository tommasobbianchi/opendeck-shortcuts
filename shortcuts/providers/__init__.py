import logging
from typing import Protocol

from ..model import Shortcut
from . import curated, kitty

log = logging.getLogger(__name__)


class Provider(Protocol):
    name: str

    def matches(self, segment: str) -> bool: ...

    def shortcuts(self, segment: str) -> list[Shortcut]: ...


PROVIDERS: list = [kitty, curated]

_PROVENANCE_RANK = {"extracted": 3, "curated": 2, "guessed": 1}


def resolve(identity: str) -> list[Shortcut]:
    """Return every shortcut for an identity like ``kitty`` or ``kitty:chrome``.

    Splits on ``:``, asks every matching provider per segment, and de-duplicates
    by ``(app, combo)`` keeping the strongest provenance. A failing provider is
    logged and skipped, never propagated.
    """
    by_key: dict = {}
    for segment in identity.split(":"):
        if not segment:
            continue
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
    return list(by_key.values())
