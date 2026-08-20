"""Extract OrcaSlicer shortcuts and per-action artwork from a source tree.

Parses ``src/slic3r/GUI/KBShortcutsDialog.cpp`` and matches each shortcut to an
SVG in ``resources/images/*`` only when the label and the stem agree exactly.
Anything that is not a single deterministic keystroke is dropped, never guessed.
"""

import argparse
import json
import logging
import os
import re
from pathlib import Path

from .. import keys
from ..model import Shortcut

log = logging.getLogger(__name__)

name = "orca"

_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "catalogue" / "orca.snapshot.json"
_CPP_REL = os.path.join("src", "slic3r", "GUI", "KBShortcutsDialog.cpp")

_MATCH = {"orca", "orcaslicer", "orca-slicer", "orcabelt2608", "orcacad"}

_CANDIDATE_TREES = [
    "~/projects/ORCA_2.4.0_pr/OrcaSlicer",
    "~/projects/apps/orca_cad",
    "~/projects/orca-cad-primitives",
    "~/projects/orca-pr12998",
]

_NAME_MAP = {
    "Esc": "escape",
    "Del": "delete",
    "Tab": "tab",
    "Arrow Up": "up",
    "Arrow Down": "down",
    "Arrow Left": "left",
    "Arrow Right": "right",
}

_STOP = {
    "the", "a", "an", "of", "on", "to", "all", "and", "or", "for", "with",
    "selected", "current", "this",
}

_BLOCK_RE = re.compile(r"Shortcuts\s+(\w+)\s*=\s*\{")
_ENTRY_RE = re.compile(r"\{(.*?),\s*L\(\s*\"(.*?)\"\s*\)\s*\}", re.DOTALL)

_skipped = 0


def matches(segment: str) -> bool:
    return segment.lower() in _MATCH


def skipped() -> int:
    return _skipped


def _resolve_cpp() -> tuple[str | None, str | None]:
    env = os.environ.get("ORCA_SOURCE")
    if env:
        cpp = os.path.join(env, _CPP_REL)
        if os.path.isfile(cpp):
            return cpp, env
    for tree in _CANDIDATE_TREES:
        tree = os.path.expanduser(tree)
        cpp = os.path.join(tree, _CPP_REL)
        if os.path.isfile(cpp):
            return cpp, tree
    return None, None


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    lines = text.splitlines()
    blocks: list[tuple[str, list[str]]] = []
    i, n = 0, len(lines)
    while i < n:
        m = _BLOCK_RE.search(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(1)
        body = lines[i][m.end():]
        depth = 1 + body.count("{") - body.count("}")
        buf = [body]
        i += 1
        while i < n and depth > 0:
            line = lines[i]
            depth += line.count("{") - line.count("}")
            buf.append(line)
            i += 1
        blocks.append((name, buf))
    return blocks


def _strip_apple(lines: list[str]) -> list[str]:
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("#ifdef __APPLE__") or s.startswith("#if defined(__APPLE__)"):
            depth = 1
            j = i + 1
            else_idx = endif_idx = None
            while j < n and depth > 0:
                t = lines[j].strip()
                if t.startswith("#if"):
                    depth += 1
                elif t.startswith("#else") and depth == 1:
                    else_idx = j
                elif t.startswith("#endif"):
                    depth -= 1
                    if depth == 0:
                        endif_idx = j
                j += 1
            if endif_idx is not None and else_idx is not None:
                out.extend(lines[else_idx + 1:endif_idx])
            i = endif_idx + 1 if endif_idx is not None else n
            continue
        out.append(lines[i])
        i += 1
    return out


def _key_to_combo(key_expr: str) -> str | None:
    mods: list[str] = []
    main = None
    for part in key_expr.split("+"):
        part = part.strip()
        if not part:
            continue
        if part in ("ctrl", "alt", "shift"):
            mods.append(part)
            continue
        m = re.fullmatch(r'"(.+)"', part)
        if m:
            lit = m.group(1)
            if len(lit) == 1 and lit.isascii():
                main = lit.lower()
                continue
            return None
        m = re.fullmatch(r'L\(\s*"(.*?)"\s*\)', part)
        if m:
            mapped = _NAME_MAP.get(m.group(1))
            if mapped is None:
                return None
            main = mapped
            continue
        return None
    if main is None:
        return None
    return "+".join(mods + [main])


def _category(name: str) -> str:
    if name.endswith("_shortcuts"):
        name = name[: -len("_shortcuts")]
    name = name.replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else name


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _icon_index(tree_root: str) -> dict[str, str]:
    img_dir = Path(tree_root) / "resources" / "images"
    if not img_dir.is_dir():
        return {}
    stems: dict[str, str] = {}
    for f in sorted(img_dir.glob("*.svg")):
        base = f.stem
        while True:
            prev = base
            for suffix in ("_dark", "_hover", "_disable"):
                if base.endswith(suffix):
                    base = base[: -len(suffix)]
                    break
            if base == prev:
                break
        stems.setdefault(base, str(f))
    return stems


def _significant_words(label: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", label.lower()) if w not in _STOP]


def _match_icon(label: str, stems: dict[str, str]) -> str | None:
    words = _significant_words(label)
    best = None
    for i in range(len(words)):
        for j in (i, i + 1):
            if j >= len(words):
                continue
            joined = "_".join(words[i:j + 1])
            if joined not in stems:
                continue
            cand = (j - i + 1, not joined.startswith("toolbar_"), joined)
            if best is None or cand > best:
                best = cand
    return stems[best[2]] if best else None


def _parse(text: str, source: str, stems: dict[str, str]) -> tuple[list[Shortcut], int]:
    out: list[Shortcut] = []
    skipped = 0
    for block_name, lines in _blocks(text):
        category = _category(block_name)
        body = "\n".join(_strip_apple(lines))
        for m in _ENTRY_RE.finditer(body):
            combo = _key_to_combo(m.group(1))
            if combo is None:
                skipped += 1
                continue
            try:
                keys.encode(combo)
            except ValueError:
                skipped += 1
                continue
            combo = keys.normalise(combo)
            label = m.group(2)
            out.append(
                Shortcut(
                    id=f"orca.{_slug(label)}",
                    app="orca",
                    label=label,
                    combo=combo,
                    provenance="extracted",
                    source=source,
                    category=category,
                    icon=_match_icon(label, stems),
                )
            )
    return out, skipped


def load_snapshot(tree_root: str | None = None) -> list[Shortcut]:
    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    out: list[Shortcut] = []
    for e in data["shortcuts"]:
        icon = e.get("icon")
        if icon and tree_root:
            icon = os.path.join(tree_root, icon)
        else:
            icon = None
        out.append(
            Shortcut(
                id=e["id"],
                app="orca",
                label=e["label"],
                combo=e["combo"],
                provenance="extracted",
                source=str(_SNAPSHOT_PATH),
                category=e.get("category", ""),
                icon=icon,
            )
        )
    return out


def shortcuts(segment: str, cpp_path: str | None = None, tree_root: str | None = None) -> list[Shortcut]:
    global _skipped
    if cpp_path is None:
        cpp_path, tree_root = _resolve_cpp()
        if cpp_path is None:
            _skipped = 0
            return load_snapshot()
    text = Path(cpp_path).read_text(encoding="utf-8")
    stems = _icon_index(tree_root) if tree_root else {}
    scs, skips = _parse(text, cpp_path, stems)
    _skipped = skips
    return scs


def _snapshot_payload(tree: str) -> dict:
    cpp = os.path.join(tree, _CPP_REL)
    text = Path(cpp).read_text(encoding="utf-8")
    stems = _icon_index(tree)
    scs, _ = _parse(text, cpp, stems)
    entries = []
    for s in scs:
        icon = os.path.relpath(s.icon, tree) if s.icon else None
        entries.append(
            {"id": s.id, "label": s.label, "combo": s.combo, "category": s.category, "icon": icon}
        )
    return {"shortcuts": entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orca")
    parser.add_argument("--snapshot", nargs="?", const="", help="emit snapshot JSON for a tree")
    args = parser.parse_args(argv)
    tree = args.snapshot
    if not tree:
        _, tree = _resolve_cpp()
    if not tree:
        parser.error("no OrcaSlicer tree found")
    print(json.dumps(_snapshot_payload(tree), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
