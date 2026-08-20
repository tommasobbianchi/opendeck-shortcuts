"""What identities the focus daemon has actually published.

OpenDeck matches an application by the WM_CLASS its watcher reads, and on GNOME Wayland that
string comes from ``opendeck-focus``: ``OrcaSlicer``, ``OrcaBelt2608``, ``kitty:claude``. A
catalogue name like ``orca`` is a different thing entirely, and writing one into
``applications.json`` produces a mapping that silently never fires.

The daemon records every class it publishes; this module reads that file so the picker can
tell the two apart instead of guessing.
"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


def seen_path() -> Path:
    override = os.environ.get("OPENDECK_FOCUS_SEEN")
    if override:
        return Path(override).expanduser()
    cache = os.environ.get("XDG_CACHE_HOME")
    root = Path(cache).expanduser() if cache else Path.home() / ".cache"
    return root / "opendeck-focus" / "seen.json"


def seen() -> dict[str, int]:
    """Map of published identity -> unix time last seen. Empty when the daemon has never run."""
    path = seen_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        log.exception("could not read %s", path)
        return {}
    if not isinstance(data, dict):
        log.error("%s is not an object", path)
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, int)}


def identities() -> list[str]:
    """Published identities, most recently seen first."""
    return [k for k, _ in sorted(seen().items(), key=lambda kv: kv[1], reverse=True)]


def is_published(identity: str) -> bool:
    return identity in seen()


def warning_for(identity: str) -> str | None:
    """Why mapping ``identity`` may not fire, or None when there is nothing to say.

    Says nothing when the daemon has published nothing at all: on a machine where it has never
    run, every identity is unknown and a warning on all of them is just noise.
    """
    if not identity:
        return None
    known = seen()
    if not known or identity in known:
        return None
    close = [k for k in known if identity and identity.lower() in k.lower()]
    hint = f" Did you mean {', '.join(sorted(close)[:3])}?" if close else ""
    return (
        f"opendeck-focus has never published {identity!r}, so OpenDeck will not match it "
        f"against a focused window.{hint}"
    )
