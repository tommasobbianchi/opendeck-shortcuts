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


def _app_of(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["app"]


def matches(segment: str) -> bool:
    for f in _files():
        try:
            if _app_of(f) == segment:
                return True
        except Exception:
            continue
    return False


def shortcuts(segment: str) -> list[Shortcut]:
    out: list[Shortcut] = []
    for f in _files():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data["app"] != segment:
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
