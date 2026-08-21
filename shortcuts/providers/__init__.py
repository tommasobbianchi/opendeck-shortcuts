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
    # Most specific segment first. `google-chrome:gmail` is a Gmail window that happens to be in
    # Chrome, and a deck with room for fifteen keys should spend them on Gmail before it spends
    # them on New Tab. Same for `kitty:claude`.
    for segment in reversed(identity.split(":")):
        if not segment:
            continue
        before = len(by_key)
        for provider in PROVIDERS:
            try:
                if not provider.matches(segment):
                    continue
                for sc in provider.shortcuts(segment):
                    # An application can give one keystroke two meanings in two modes that are
                    # never live at once: Orca CAD's "p" is Point while a sketch is open and
                    # Show/hide planes when none is. Collapsing those loses one of them.
                    #
                    # The label, not the category, is what separates them. Orca's own list
                    # repeats a combo across its sections for the SAME action -- Ctrl+X is Cut
                    # in both Plater and Object list -- and those should still collapse to one
                    # key. Same keystroke, same name: one shortcut. Same keystroke, different
                    # name: two, because they do different things.
                    key = (sc.app, sc.combo, sc.label)
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
