"""Fetch an application's own toolbar icons, so a key looks like the button it presses.

A generated glyph for "Extrude" is a guess at what extruding looks like. Onshape已 drew that
icon years ago, it is on the toolbar the user already knows, and muscle memory is the entire
point of a deck. So for applications that publish their icons, fetch theirs.

These stay on the machine that fetched them (see :func:`shortcuts.icons.app_art_dir`): using a
vendor's icon for its own tool is what the icon is for, redistributing it from a public
repository is not.

Onshape's help site names each tool's icon inside that tool's page, rather than at a path you
can guess -- `extrudetooliconLG.png` exists but `fillettooliconLG.png` does not -- so this
reads the page and takes the reference.
"""

import logging
import re
from pathlib import Path
from urllib import error, parse, request

log = logging.getLogger(__name__)

HELP_BASE = "https://cad.onshape.com/help/Content/"
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

#: Where a tool's help page is not simply its name.
ONSHAPE_PAGES = {
    "centre rectangle": "rectangle",
    "corner rectangle": "rectangle",
    "3 point arc": "arc",
    "use / project": "useedges",
    "show/hide sketches": "sketch",
    "sketch point": "point",
    "mate connectors": "mate-connectors",
    "exit command": None,
    "construction": "sketchconstruction",
}


def _get(url: str, timeout: int = 30) -> bytes | None:
    try:
        with request.urlopen(request.Request(url, headers={"User-Agent": _UA}), timeout=timeout) as r:
            return r.read()
    except error.HTTPError as exc:
        if exc.code != 404:
            log.warning("HTTP %s for %s", exc.code, url)
        return None
    except Exception:
        log.info("could not fetch %s", url, exc_info=True)
        return None


def page_name(label: str) -> str | None:
    """The help page a tool's label points at."""
    key = label.strip().lower()
    if key in ONSHAPE_PAGES:
        return ONSHAPE_PAGES[key]
    return re.sub(r"[^a-z0-9]+", "", key) or None


def direct_url(label: str) -> str | None:
    """Some icons sit at a guessable path: `extrudetooliconLG.png`, `planetooliconLG.png`.

    Most do not -- `fillettooliconLG.png` is a 404 while the fillet page names
    `filletfeaturetoolicon.png` -- so this is a fallback, tried when the page itself says
    nothing, not a rule.
    """
    stem = re.sub(r"[^a-z0-9]+", "", label.strip().lower())
    if not stem:
        return None
    for suffix in ("tooliconLG", "toolicon", "featuretoolicon", "featuretooliconLG"):
        url = f"{HELP_BASE}Resources/Images/icons/{stem}{suffix}.png"
        if _get(url, timeout=15) is not None:
            return url
    return None


def icon_url(label: str) -> str | None:
    """Find the toolbar icon a tool's own help page shows."""
    page = page_name(label)
    if page is None:
        return direct_url(label)
    html = _get(HELP_BASE + f"{page}.htm")
    if html is None:
        return direct_url(label)
    text = html.decode("utf-8", "replace")
    # The page shows its tool icon as ...Resources/Images/icons/<something>toolicon[LG].png
    found = re.findall(r'src="([^"]*Resources/Images/icons/[^"]*toolicon[^"]*\.png)"', text, re.I)
    if not found:
        return direct_url(label)
    # Prefer the large one: it is the same drawing with more pixels to rescale from.
    found.sort(key=lambda s: ("LG.png" not in s, len(s)))
    return parse.urljoin(HELP_BASE + f"{page}.htm", found[0])


def fetch(shortcut, force: bool = False) -> Path | None:
    """Put this action's own icon on disk, and return where. None when there isn't one."""
    from . import icons

    destination = icons.app_art_path(shortcut)
    if destination.is_file() and not force:
        return destination
    url = icon_url(shortcut.label)
    if url is None:
        return None
    data = _get(url)
    if data is None or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        log.info("no usable icon at %s", url)
        return None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    except OSError:
        log.exception("could not write %s", destination)
        return None
    return destination
