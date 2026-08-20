"""Localhost picker server: serves the picker page and a small JSON API.

Bound to 127.0.0.1 only, and it refuses any request whose ``Host`` header is not
``127.0.0.1`` or ``localhost`` (with optional port), so a page on another site
cannot drive it. Only ``shortcuts/assets`` is served, and only ``picker.html``
is reachable at ``/`` -- there is no directory listing and no arbitrary file
read, so path traversal falls on the 404 path.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import focus, icons, opendeck
from .providers import orca, resolve

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

_ICON_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def icon_roots() -> list[Path]:
    """Directories an icon may legitimately come from."""
    roots: list[Path] = []
    tree = orca.source_tree()
    if tree:
        roots.append(Path(tree) / "resources")
    for extra in ("/usr/share/icons", "/usr/share/pixmaps"):
        roots.append(Path(extra))
    roots.append(Path.home() / ".local/share/icons")
    return [r for r in roots if r.is_dir()]


def icon_path(raw: str) -> Path | None:
    """The file `raw` names, but only if it is a real image under an allowed root."""
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_file() or resolved.suffix.lower() not in _ICON_TYPES:
        return None
    for root in icon_roots():
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return resolved
    return None



_GOOD_HOSTS = {"127.0.0.1", "localhost"}


class Handler(BaseHTTPRequestHandler):
    server_version = "opendeck-shortcuts/0.1"

    # -- plumbing -----------------------------------------------------------

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "").strip()
        name = host.rsplit(":", 1)[0].lower() if host else ""
        return name in _GOOD_HOSTS

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def log_message(self, fmt, *args):  # silence per-request noise
        pass


    # The picker has to show the artwork an application already ships, which lives outside the
    # served assets directory. Serving an arbitrary filesystem path from a local origin is how a
    # picker turns into a file-disclosure hole, so the path is checked against the roots the
    # providers can legitimately reference and nothing else.
    def _send_icon(self, raw: str) -> None:
        resolved = icon_path(raw)
        if resolved is None:
            self.send_error(404)
            return
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _ICON_TYPES[resolved.suffix.lower()])
        self.send_header("Content-Length", str(len(body)))
        # An SVG is a document: served inline it could run script on this origin. The picker only
        # ever uses these in <img>, where script never runs, and this makes direct navigation
        # inert too.
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    # -- routes -------------------------------------------------------------

    def do_GET(self):
        if not self._host_ok():
            self.send_error(403, "forbidden host")
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self._serve_picker()
        elif parsed.path == "/api/identity":
            self._send_json({"identity": resolve_identity(query)})
        elif parsed.path == "/api/shortcuts":
            self._send_json(
                shortcuts_payload(
                    query.get("identity", [""])[0],
                    build_missing=query.get("build", ["0"])[0] == "1",
                )
            )
        elif parsed.path == "/api/profile":
            self._send_json(
                profile_payload(
                    query.get("identity", [""])[0],
                    query.get("device", [""])[0],
                )
            )
        elif parsed.path == "/api/identities":
            self._send_json(
                {
                    "identities": focus.identities(),
                    "warning": focus.warning_for(query.get("identity", [""])[0]),
                }
            )
        elif parsed.path == "/api/devices":
            self._send_json(opendeck.devices())
        elif parsed.path == "/api/icon":
            self._send_icon(query.get("path", [""])[0])
        else:
            self.send_error(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            self.send_error(403, "forbidden host")
            return
        if urlparse(self.path).path != "/api/apply":
            self.send_error(404, "not found")
            return
        status, obj = apply_payload(self._read_json())
        self._send_json(obj, status)

    def _serve_picker(self) -> None:
        path = ASSETS / "picker.html"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# -- API logic (pure, so the tests can import them) -------------------------


def resolve_identity(query: dict) -> str:
    """Resolve the identity for the picker, in priority order, never guessing."""
    if "identity" in query and query["identity"]:
        return query["identity"][0]
    env = os.environ.get("OPENDECK_IDENTITY")
    if env:
        return env
    if not shutil.which("xprop"):
        return ""
    try:
        active = subprocess.run(
            ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        match = re.search(r"0x[0-9a-fA-F]+", active)
        if not match:
            return ""
        wm_class = subprocess.run(
            ["xprop", "-id", match.group(0), "WM_CLASS"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        quoted = re.findall(r'"([^"]*)"', wm_class)
        return quoted[-1] if quoted else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def shortcuts_payload(identity: str, build_missing: bool = False) -> list[dict]:
    # build_missing runs a local model and takes tens of seconds, so it is never the default:
    # the picker asks for it explicitly, on a page that has told the user what it costs.
    records = resolve(identity, build_missing=build_missing)
    counts: dict[str, int] = {}
    for sc in records:
        counts[sc.combo] = counts.get(sc.combo, 0) + 1
    return [
        {
            "id": sc.id,
            "label": sc.label,
            "combo": sc.combo,
            "tokens": sc.tokens,
            "provenance": sc.provenance,
            "source": sc.source,
            "category": sc.category,
            "icon": sc.icon,
            "app": sc.app,
            "collision": counts[sc.combo] > 1,
        }
        for sc in records
    ]


def profile_payload(identity: str, device: str) -> dict:
    profile = opendeck.profile_name_for(identity)
    data = opendeck.load_profile(device, profile)
    return {"device": device, "profile": profile, "keys": data.get("keys", [])}


def apply_payload(payload: dict) -> tuple[int, dict]:
    identity = payload.get("identity", "")
    device = payload.get("device", "")
    if not identity or not device:
        return 400, {"ok": False, "error": "identity and device are required"}

    by_id = {sc.id: sc for sc in resolve(identity)}
    profile = opendeck.profile_name_for(identity)
    data = opendeck.load_profile(device, profile)
    keys = list(data.get("keys") or [])
    while len(keys) <= opendeck.LAST_KEY:
        keys.append(None)

    assignments = payload.get("assignments") or {}
    generate_missing = bool(payload.get("generate"))
    origins = {"app": 0, "cache": 0, "generated": 0, "none": 0}
    written = 0
    for position in range(opendeck.FIRST_KEY, opendeck.LAST_KEY + 1):
        sid = assignments.get(str(position))
        sc = by_id.get(sid) if sid else None
        if sc is None:
            keys[position] = None
        else:
            result = icons.resolve(sc, generate_missing=generate_missing)
            keys[position] = opendeck.input_key(position, sc.label, sc.tokens, result.data_uri)
            origins[result.origin] += 1
            written += 1

    data["keys"] = keys
    try:
        opendeck.save_profile(device, profile, data)
    except RuntimeError as exc:
        return 409, {"ok": False, "error": str(exc)}
    opendeck.map_application(identity, device, profile)
    # Applying still goes through: setting up an app before its first focus is legitimate, and
    # the mapping starts working the moment the daemon publishes that class. The warning is so
    # a name that will never match does not look like success.
    return 200, {
        "ok": True,
        "profile": profile,
        "written": written,
        "icons": origins,
        "warning": focus.warning_for(identity),
    }


def make_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(port: int = 8767, identity: str | None = None, no_browser: bool = False) -> int:
    if identity:
        os.environ["OPENDECK_IDENTITY"] = identity

    server = None
    bound_port = None
    for candidate in range(port, port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            bound_port = candidate
            break
        except OSError:
            continue
    if server is None:
        print(f"error: no free port in {port}..{port + 9}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{bound_port}/"
    print(f"serving on {url}", flush=True)
    if not no_browser:
        import webbrowser

        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
