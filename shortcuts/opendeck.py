"""OpenDeck profile IO: read and write the configuration files the deck uses.

Pure logic plus file IO, no HTTP. The layout mirrors what
``~/projects/vsd-n1/opendeck-focus/setup-n1.py`` already writes, so the two
scripts stay compatible: profiles live under ``<config>/profiles/<device>/`` and
the application-to-profile map is ``<config>/applications.json``.

Image paths are absolute on purpose: OpenDeck's webserver serves files by
absolute path, and a relative one renders as a blank key.
"""

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

# ~/.config/opendeck, overridable by $OPENDECK_CONFIG for tests and sandboxes.
log = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "opendeck"

RESERVED = (0, 1, 2)
FIRST_KEY, LAST_KEY = 3, 17

_STARTERPACK = "com.amansprojects.starterpack.sdPlugin"
_INPUT_SIMULATION_UUID = "com.amansprojects.starterpack.inputsimulation"

_EMPTY_KEYS = [None] * 18

#: A profile OpenDeck will actually load. It deserialises the file into a struct with all
#: three fields, and a file missing any of them is not "a profile with defaults" -- it is
#: replaced wholesale by an empty one, silently, the next time OpenDeck starts. That is how a
#: freshly created profile lost every key it had just been given: writing only `keys` looked
#: fine on disk and survived exactly until the app came back.
_EMPTY_SLIDERS = [None]     # the one encoder: the knob
_EMPTY_INFOBARS: list = []


def empty_profile() -> dict:
    return {
        "infobars": list(_EMPTY_INFOBARS),
        "keys": list(_EMPTY_KEYS),
        "sliders": list(_EMPTY_SLIDERS),
    }


def _config_dir() -> Path:
    override = os.environ.get("OPENDECK_CONFIG")
    return Path(override).expanduser() if override else CONFIG_DIR


def devices() -> list[str]:
    """Subdirectories of ``<config>/profiles``, one per physical deck."""
    root = _config_dir() / "profiles"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def profile_path(device: str, profile: str) -> Path:
    return _config_dir() / "profiles" / device / f"{profile}.json"


def binary() -> str | None:
    """The OpenDeck executable, for talking to a running instance."""
    override = os.environ.get("OPENDECK_BINARY")
    if override:
        return override if Path(override).is_file() else None
    for candidate in (Path.home() / ".local/bin/opendeck", Path("/usr/bin/opendeck")):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("opendeck")


def push_image(device: str, profile: str, position: int, data_uri: str,
               controller: str = "Keypad") -> bool:
    """Set one key's image on a *running* OpenDeck, without touching its files.

    Writing profiles needs OpenDeck stopped, because it holds them in memory and writes them
    out on exit. This is the other door: the same `setImage` event its own plugins send. The
    change lands in memory and is persisted when OpenDeck next exits.

    OpenDeck answers nothing useful -- a malformed message is only a warning in its log -- so a
    True here means "the message was delivered", not "the key changed".
    """
    executable = binary()
    if executable is None:
        log.error("no opendeck binary found; cannot push to a running instance")
        return False
    # The context is the flat string OpenDeck uses everywhere: device.profile.controller.pos.state
    message = json.dumps({
        "event": "setImage",
        "context": f"{device}.{profile}.{controller}.{position}.0",
        "payload": {"image": data_uri},
    })
    try:
        done = subprocess.run([executable, "--process-message", message],
                              capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        log.exception("could not reach OpenDeck to set key %d", position)
        return False
    return done.returncode == 0


def load_profile(device: str, profile: str) -> dict:
    """Read a profile; a missing file is an empty profile, not an error."""
    path = profile_path(device, profile)
    if not path.is_file():
        return empty_profile()
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = data.get("keys")
    if not isinstance(keys, list):
        data["keys"] = list(_EMPTY_KEYS)
    # An older profile, or one we wrote before this was understood, gets the missing fields
    # rather than being handed back in a shape OpenDeck will throw away.
    if not isinstance(data.get("sliders"), list):
        data["sliders"] = list(_EMPTY_SLIDERS)
    if not isinstance(data.get("infobars"), list):
        data["infobars"] = list(_EMPTY_INFOBARS)
    return data


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(value, indent=1))


def save_profile(device: str, profile: str, data: dict) -> None:
    """Write a profile, backing up the previous one first.

    Refuses while OpenDeck is running: it holds profiles in memory and rewrites
    them on exit, silently discarding the file just written.
    """
    if opendeck_running():
        raise RuntimeError(
            "OpenDeck is running; quit it first or it will overwrite these files on exit."
        )
    _write_json(profile_path(device, profile), data)


def profile_name_for(identity: str) -> str:
    """Turn an identity into a profile filename: ``kitty:claude`` -> ``kitty_claude``.

    Keeps only ``[A-Za-z0-9_-]``, collapsing runs of anything else into a single
    underscore, capped at 48 characters.
    """
    return re.sub(r"[^A-Za-z0-9_-]+", "_", identity)[:48]


def _absolute_image(icon: str | None) -> str:
    if not icon:
        return ""
    if icon.startswith("data:"):
        return icon
    return os.path.abspath(os.path.expanduser(icon))


def _state(image: str, text: str = "") -> dict:
    return {
        "alignment": "middle",
        "background_colour": "#000000",
        "colour": "#FFFFFF",
        "family": "Liberation Sans",
        "image": image,
        "image_scale": 100,
        "name": "",
        "show": True,
        "size": 16,
        "stroke_colour": "#000000",
        "stroke_size": 3,
        "style": "Regular",
        "text": text,
        "underline": False,
    }


def input_key(position: int, label: str, ron: str, icon: str | None) -> dict:
    """Build the OpenDeck key record for the Starter Pack's Simulate Input action."""
    image = _absolute_image(icon)
    return {
        "action": {
            "controllers": ["Keypad", "Encoder"],
            "disable_automatic_states": False,
            "encoder": None,
            "icon": image,
            "name": "Simulate Input",
            "plugin": _STARTERPACK,
            "property_inspector": (
                f"plugins/{_STARTERPACK}/propertyInspector/inputSimulation.html"
            ),
            "states": [_state(image)],
            "supported_in_multi_actions": True,
            "tooltip": label,
            "uuid": _INPUT_SIMULATION_UUID,
            "visible_in_action_list": True,
        },
        "children": None,
        "context": f"Keypad.{position}.0",
        "current_state": 0,
        "settings": {"down": ron, "up": "", "anticlockwise": "", "clockwise": ""},
        "states": [_state(image, label)],
    }


def applications() -> dict:
    """Read ``<config>/applications.json``; ``{}`` when absent or unreadable."""
    path = _config_dir() / "applications.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def map_application(identity: str, device: str, profile: str) -> None:
    """Point an application identity at a profile on a device, and persist it."""
    apps = applications()
    apps.setdefault(identity, {})[device] = profile
    _write_json(_config_dir() / "applications.json", apps)


def opendeck_running() -> bool:
    """True when an ``opendeck`` process exists, by exact ``comm`` name.

    ``/proc/*/comm`` is the process name, not the command line, so this never
    matches the calling Python process the way ``pgrep -f`` would.
    """
    for comm in Path("/proc").glob("*/comm"):
        try:
            if comm.read_text(encoding="utf-8").strip() == "opendeck":
                return True
        except OSError:
            continue
    return False
