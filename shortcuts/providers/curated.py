import json
from pathlib import Path

from ..model import Shortcut

name = "curated"

_CATALOGUE_DIR = Path(__file__).resolve().parents[2] / "catalogue"


def _files() -> list[Path]:
    out: list[Path] = []
    for f in sorted(_CATALOGUE_DIR.glob("*.json")):
        # Provider snapshots share this directory but are not curated files: they carry
        # already-extracted records in their own shape. Name them, rather than sniffing for a
        # key, so a curated file that forgets one is a loud failure and not a silent absence.
        if f.name.endswith(".snapshot.json"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and "app" in data and "shortcuts" in data:
            out.append(f)
    return out


def _identities(data: dict) -> list[str]:
    """The names a catalogue answers to.

    A curated file is written for an application, but the identity a deck asks about is a
    WM_CLASS: `google-chrome`, not `chrome`. Rather than duplicate the file, a catalogue may
    list the other names it covers under "also".
    """
    also = data.get("also")
    extra = [a for a in also if isinstance(a, str)] if isinstance(also, list) else []
    return [data["app"], *extra]


def _app_of(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["app"]


def matches(segment: str) -> bool:
    for f in _files():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if segment in _identities(data):
            return True
    return False


def shortcuts(segment: str) -> list[Shortcut]:
    out: list[Shortcut] = []
    for f in _files():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if segment not in _identities(data):
            continue
        source = data["source"]
        for entry in data["shortcuts"]:
            out.append(
                Shortcut(
                    id=entry["id"],
                    app=segment,
                    label=entry["label"],
                    combo=entry["combo"],
                    provenance="curated",
                    source=source,
                )
            )
    return out
