"""Shortcuts a GTK application ships inside itself.

Every GTK/libadwaita app with a "Keyboard Shortcuts" window carries that window as a GResource
compiled into its binary -- `help-overlay.ui` under GTK, `shortcuts-dialog.ui` under Adwaita 1.8.
It is the authoritative list: the same table the application shows its own users, maintained by
the people who wrote the keybindings.

So for a GNOME app there is nothing to guess. Find the binary behind the identity's desktop
file, ask `gresource` what it holds, and read the accelerators out of the XML.

Accelerators come in GTK's own notation (`<Primary>O`, `<shift>Delete`, `F2`), which this module
translates into the combos the encoder understands. An item with no accelerator -- Nautilus
lists several by action name only, because the user binds them -- is not a shortcut anyone can
press, and is skipped rather than invented.
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree

from ..model import Shortcut

name = "gtk"

log = logging.getLogger(__name__)

_DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
    Path("/var/lib/flatpak/exports/share/applications"),
]

#: GTK writes modifiers as <Primary>/<Control>/<shift>/<alt>/<Super>, any case.
_MODIFIERS = {
    "primary": "ctrl",
    "control": "ctrl",
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "meta": "meta",
    "super": "meta",
}

#: X11 keysym names that are not already what the encoder calls them.
_KEYS = {
    "return": "return", "kp_enter": "return", "escape": "escape", "delete": "delete",
    "backspace": "backspace", "tab": "tab", "space": "space", "home": "home", "end": "end",
    "page_up": "page_up", "page_down": "page_down", "up": "up", "down": "down",
    "left": "left", "right": "right", "insert": "insert",
    "plus": "+", "minus": "-", "equal": "=", "period": ".", "comma": ",", "slash": "/",
    "backslash": "\\", "semicolon": ";", "apostrophe": "'", "grave": "`", "asciitilde": "~",
    "bracketleft": "[", "bracketright": "]", "question": "?", "exclam": "!", "at": "@",
}


def _desktop_files() -> list[Path]:
    out: list[Path] = []
    for directory in _DESKTOP_DIRS:
        if directory.is_dir():
            out.extend(sorted(directory.glob("*.desktop")))
    return out


def _binary_for(segment: str) -> str | None:
    """The executable behind an identity, via its desktop file.

    Matched on StartupWMClass first, because that is what the identity *is*, then on the file
    name, which is how reverse-DNS identities like org.gnome.Nautilus find themselves.
    """
    wanted = segment.lower()
    for path in _desktop_files():
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        wm = re.search(r"^StartupWMClass=(.+)$", text, re.M)
        names = {path.stem.lower()}
        if wm:
            names.add(wm.group(1).strip().lower())
        if wanted not in names:
            continue
        exec_line = re.search(r"^Exec=(.+)$", text, re.M)
        if not exec_line:
            continue
        first = exec_line.group(1).split()[0]
        resolved = shutil.which(first) or (first if os.path.isfile(first) else None)
        if resolved:
            return resolved
    return None


def _resource_paths(binary: str) -> list[str]:
    try:
        done = subprocess.run(["gresource", "list", binary], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line for line in done.stdout.splitlines()
            if line.endswith(".ui") and ("shortcut" in line or "help-overlay" in line)]


def _extract(binary: str, resource: str) -> str | None:
    try:
        done = subprocess.run(["gresource", "extract", binary, resource],
                              capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def parse_accelerator(accel: str) -> str | None:
    """`<Primary><shift>N` -> `ctrl+shift+n`; None when it is not a single chord.

    GTK lists alternatives separated by a space, and ranges like `<alt>0...8`. The caller gets
    one combo per call, so alternatives are split by the caller and ranges are refused here.
    """
    accel = accel.strip()
    if not accel or "..." in accel:
        return None
    parts = re.findall(r"<([^>]+)>", accel)
    modifiers = []
    for part in parts:
        mod = _MODIFIERS.get(part.lower())
        if mod is None:
            return None
        if mod not in modifiers:
            modifiers.append(mod)
    key = re.sub(r"<[^>]+>", "", accel).strip()
    if not key:
        return None
    lower = key.lower()
    if lower in _KEYS:
        key = _KEYS[lower]
    elif re.fullmatch(r"f\d{1,2}", lower):
        key = lower
    elif len(key) == 1:
        key = lower
    else:
        return None
    return "+".join([*modifiers, key])


def shortcuts_from_ui(xml: str, app: str, source: str) -> list[Shortcut]:
    """Every item in a shortcuts window that names a key you can actually press."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        log.error("could not parse the shortcuts window for %s: %s", app, error)
        return []

    from .. import keys as key_encoder

    out: list[Shortcut] = []
    seen: set[str] = set()
    for obj in root.iter("object"):
        title = accelerator = None
        for prop in obj.findall("property"):
            if prop.get("name") == "title":
                title = (prop.text or "").strip()
            elif prop.get("name") == "accelerator":
                accelerator = (prop.text or "").strip()
        if not title or not accelerator:
            continue
        for alternative in accelerator.split():
            combo = parse_accelerator(alternative)
            if combo is None:
                continue
            try:
                key_encoder.encode(combo)
            except ValueError:
                continue
            if combo in seen:
                continue
            seen.add(combo)
            identifier = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
            out.append(Shortcut(
                id=f"{app}.{identifier}",
                app=app,
                label=title,
                combo=combo,
                provenance="extracted",
                source=source,
            ))
            break  # one chord per action: the first alternative the encoder accepts
    return out


def _ui_for(segment: str) -> tuple[str, str] | None:
    binary = _binary_for(segment)
    if binary is None or shutil.which("gresource") is None:
        return None
    for resource in _resource_paths(binary):
        xml = _extract(binary, resource)
        if xml:
            return xml, f"{binary}!{resource}"
    return None


def matches(segment: str) -> bool:
    return _ui_for(segment) is not None


def shortcuts(segment: str) -> list[Shortcut]:
    found = _ui_for(segment)
    if found is None:
        return []
    xml, source = found
    return shortcuts_from_ui(xml, segment, source)
