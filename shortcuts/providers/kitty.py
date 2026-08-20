import logging
import os
import re
from pathlib import Path

from .. import keys
from ..model import Shortcut

log = logging.getLogger(__name__)

name = "kitty"

_MAX_DEPTH = 5

_MAP_RE = re.compile(r"^map\s+(\S+)\s*(.*)$")
_INCLUDE_RE = re.compile(r"^include\s+(.+)$")


def _default_paths() -> list[str]:
    paths = []
    kcd = os.environ.get("KITTY_CONFIG_DIRECTORY")
    if kcd:
        paths.append(os.path.join(kcd, "kitty.conf"))
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(os.path.join(xdg, "kitty", "kitty.conf"))
    paths.append(os.path.expanduser("~/.config/kitty/kitty.conf"))
    return paths


def matches(segment: str) -> bool:
    return segment == "kitty"


def _collect(path: str, depth: int, visited: set, acc: list) -> None:
    path = os.path.abspath(os.path.expanduser(path))
    if path in visited or depth > _MAX_DEPTH:
        return
    if not os.path.isfile(path):
        return
    visited.add(path)
    base = os.path.dirname(path)
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                m = _INCLUDE_RE.match(stripped)
                if m:
                    inc = m.group(1).strip().strip('"').strip("'")
                    if not inc:
                        continue
                    if not os.path.isabs(inc):
                        inc = os.path.join(base, inc)
                    _collect(inc, depth + 1, visited, acc)
                    continue
                m = _MAP_RE.match(stripped)
                if m:
                    acc.append((m.group(1), m.group(2).strip(), path))
    except OSError as e:
        log.warning("could not read kitty config %s: %s", path, e)


def _label(action: str) -> str:
    words = action.split()
    if words and words[0] == "kitten":
        words = words[1:]
    if not words:
        return ""
    # A kitten is often a script, so "llm-terminal-open-folder.py" has to read as a label
    # rather than as a filename.
    word = words[0]
    if word.endswith(".py"):
        word = word[:-3]
    word = word.replace("_", " ").replace("-", " ").strip()
    return word[:1].upper() + word[1:]


def shortcuts(segment: str, paths: list[str] | None = None) -> list[Shortcut]:
    if paths is None:
        paths = _default_paths()

    acc: list = []
    visited: set = set()
    for p in paths:
        _collect(p, 0, visited, acc)

    mapping: dict = {}
    for combo, action, source in acc:
        mapping[combo] = (action, source)

    out: list[Shortcut] = []
    seen: set = set()
    for combo, (action, source) in mapping.items():
        if not action or action == "no_op":
            continue
        try:
            keys.encode(combo)
        except ValueError as e:
            log.warning("kitty: skipping combo %r: %s", combo, e)
            continue
        canonical = keys.normalise(combo)
        first = action.split()[0]
        if first in seen:
            sid = f"{segment}.{first}.{canonical}"
        else:
            sid = f"{segment}.{first}"
            seen.add(first)
        out.append(
            Shortcut(
                id=sid,
                app=segment,
                label=_label(action),
                combo=canonical,
                provenance="extracted",
                source=source,
            )
        )
    return out
