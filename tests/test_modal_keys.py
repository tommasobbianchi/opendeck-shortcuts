"""One keystroke, two meanings: what de-duplication must keep and what it must collapse.

Orca CAD has two key tables that are never live at once, so "p" is Point while a sketch is
open and Show/hide planes when none is. Orca's own shortcut list, separately, repeats a combo
across its sections for the same action. De-duplicating by keystroke alone loses the first
case; not de-duplicating at all keeps the second twice.
"""

from shortcuts.model import Shortcut
from shortcuts.providers import resolve


def _fake(app, label, combo, category="", provenance="curated"):
    return Shortcut(id=f"{app}.{label}", app=app, label=label, combo=combo,
                    provenance=provenance, source="test", category=category)


def test_same_key_different_meaning_both_survive(monkeypatch):
    import shortcuts.providers as providers

    class Provider:
        name = "test"
        matches = staticmethod(lambda segment: segment == "app")
        shortcuts = staticmethod(lambda segment: [
            _fake("app", "Point", "p", "sketch"),
            _fake("app", "Show/hide planes", "p", "feature"),
        ])

    monkeypatch.setattr(providers, "PROVIDERS", [Provider])
    labels = sorted(sc.label for sc in resolve("app"))
    assert labels == ["Point", "Show/hide planes"]


def test_same_key_same_meaning_collapses(monkeypatch):
    import shortcuts.providers as providers

    class Provider:
        name = "test"
        matches = staticmethod(lambda segment: segment == "app")
        shortcuts = staticmethod(lambda segment: [
            _fake("app", "Cut", "ctrl+x", "Plater"),
            _fake("app", "Cut", "ctrl+x", "Object list"),
        ])

    monkeypatch.setattr(providers, "PROVIDERS", [Provider])
    assert [sc.label for sc in resolve("app")] == ["Cut"]


def test_the_real_catalogue_keeps_both_meanings_of_p():
    ids = {sc.id for sc in resolve("OrcaSlicer")}
    assert "OrcaSlicer.point" in ids, "the sketch tool"
    assert "OrcaSlicer.show_planes" in ids, "the view toggle on the same letter"
