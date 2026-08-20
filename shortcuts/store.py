"""The shared icon store: generated art, published once, reused everywhere.

Generating a glyph costs money and a few minutes. Doing it again on the next machine, for the
same action of the same application, costs the same again for a byte-identical result. So the
generated ones go in a public git repo and are fetched over raw.githubusercontent before
anything is generated.

Two boundaries, both deliberate:

* **Only generated art is publishable.** An application's own icons are its own -- OrcaSlicer's
  are AGPL, Chrome's are a trademark -- so they are resolved locally on each machine and never
  uploaded. :func:`publish` refuses anything whose origin is not ``generated``.
* **Publishing is opt-in, every time.** The path of an uploaded icon carries the application
  and the action, which is telemetry about what someone runs and what they do with it. Fetching
  is anonymous and safe by comparison; uploading is a decision, so nothing calls it implicitly.

Paths are readable rather than hashed -- ``icons/orca/new_project.png`` -- because a store
nobody can browse is a store nobody can correct.
"""

import base64
import json
import logging
import os
import shutil
import subprocess
from urllib import error, request

log = logging.getLogger(__name__)

DEFAULT_REPO = "tommasobbianchi/opendeck-icons"
DEFAULT_BRANCH = "main"

#: A 96x96 PNG is a couple of kilobytes. Anything far bigger is not one of ours.
MAX_BYTES = 256 * 1024


def repo() -> str:
    return os.environ.get("OPENDECK_ICON_REPO") or DEFAULT_REPO


def enabled() -> bool:
    """The store can be turned off entirely, for an offline machine or a private one."""
    return os.environ.get("OPENDECK_ICON_STORE", "1") not in ("0", "false", "no")


def _safe(part: str) -> str:
    """A path segment that cannot climb out of the store or collide across cases."""
    kept = "".join(c if c.isalnum() or c in "-_." else "_" for c in part.strip().lower())
    kept = kept.strip("._") or "unnamed"
    return kept[:64]


def path_for(shortcut) -> str:
    """``icons/<app>/<action>.png`` for a shortcut.

    ``Shortcut.id`` is usually already prefixed with the app (``orca.new_project``); the prefix
    is dropped so the directory does not repeat in the file name.
    """
    app = _safe(shortcut.app)
    action = shortcut.id
    if action.startswith(f"{shortcut.app}."):
        action = action[len(shortcut.app) + 1 :]
    return f"icons/{app}/{_safe(action)}.png"


def raw_url(shortcut, branch: str = DEFAULT_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{repo()}/{branch}/{path_for(shortcut)}"


def fetch(shortcut, timeout: int = 10) -> bytes | None:
    """Return the published PNG for ``shortcut``, or None. Never raises."""
    if not enabled():
        return None
    url = raw_url(shortcut)
    try:
        with request.urlopen(request.Request(url), timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
    except error.HTTPError as exc:
        # 404 is the normal answer for an icon nobody has published yet.
        if exc.code != 404:
            log.warning("icon store returned HTTP %s for %s", exc.code, url)
        return None
    except Exception:
        log.info("icon store unreachable for %s; carrying on without it", url, exc_info=True)
        return None
    if len(data) > MAX_BYTES:
        log.error("icon at %s is larger than %d bytes; ignoring it", url, MAX_BYTES)
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        log.error("icon at %s is not a PNG; ignoring it", url)
        return None
    return data


#: Origins whose art is ours to share. ``cache`` is on the list because nothing else can get
#: there: :func:`shortcuts.icons.resolve` returns an application's own art directly and never
#: writes it to the cache, so a cached PNG came either from the generator or from this store.
#: ``app`` is what the rule exists to keep out.
PUBLISHABLE = frozenset({"generated", "cache"})


def publish(shortcut, png: bytes, origin: str, message: str | None = None) -> bool:
    """Upload one icon we are entitled to share. Returns whether the store now holds it.

    Refuses an application's own art, and needs an authenticated ``gh``.
    """
    if origin not in PUBLISHABLE:
        log.error("refusing to publish %s art for %s; only generated icons are ours to share",
                  origin, shortcut.id)
        return False
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        log.error("refusing to publish a non-PNG for %s", shortcut.id)
        return False
    gh = shutil.which("gh")
    if gh is None:
        log.error("gh is not installed; cannot publish %s", shortcut.id)
        return False

    path = path_for(shortcut)
    args = [
        gh, "api", "--method", "PUT", f"repos/{repo()}/contents/{path}",
        "-f", f"message={message or f'Add {path}'}",
        "-f", f"content={base64.b64encode(png).decode('ascii')}",
        "-f", f"branch={DEFAULT_BRANCH}",
    ]
    # Updating an existing file needs its blob sha; a missing one is the normal case.
    sha = _sha_of(gh, path)
    if sha:
        args += ["-f", f"sha={sha}"]
    try:
        done = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        log.exception("publishing %s failed", path)
        return False
    if done.returncode != 0:
        log.error("publishing %s failed: %s", path, done.stderr.strip()[:300])
        return False
    return True


def _sha_of(gh: str, path: str) -> str | None:
    try:
        done = subprocess.run(
            [gh, "api", f"repos/{repo()}/contents/{path}", "--jq", ".sha"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.strip() or None


def published(prefix: str = "icons") -> list[str]:
    """Paths the store currently holds, for `shortcuts icons --store-list`."""
    gh = shutil.which("gh")
    if gh is None:
        return []
    try:
        done = subprocess.run(
            [gh, "api", f"repos/{repo()}/git/trees/{DEFAULT_BRANCH}?recursive=1", "--jq",
             ".tree[].path"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line for line in done.stdout.splitlines() if line.startswith(prefix + "/")]


def describe() -> str:
    return json.dumps({"repo": repo(), "enabled": enabled(), "branch": DEFAULT_BRANCH})
