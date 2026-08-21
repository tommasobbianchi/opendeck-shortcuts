#!/usr/bin/env python3
"""Keep the deck's layout in the repository, where it outlives the machine.

Which shortcut sits on which key of which page is a decision made many times over
and recorded nowhere but ``~/.config/opendeck`` on one desktop. This copies it into
the repo and puts it back.

    snapshot-profiles.py save
    snapshot-profiles.py restore [--device ID]

Two things are deliberately not saved, because this repository is public:

* **The embedded action art.** Every key carries the plugin's own default icon as a
  base64 data URI in ``action.icon`` and ``action.states[].image`` -- 175 copies, 2.7 MB,
  none of it ours to redistribute. Our chosen art is not in there: it is the ``0.png``
  beside the profile, drawn from the app-art tier, which is local by design. Stripping
  the data URIs costs nothing, because they are the plugin's defaults and every key we
  write has its own image anyway.
* **Private endpoints.** A launcher key can hold a Home Assistant remote URL or a tailnet
  address, which is a credential in all but name. Those are replaced by a placeholder and
  ``restore`` says which keys need it typed back in.

So a restore brings back every key, its action, its keystroke and its name; run
``shortcuts icons --push <identity>`` afterwards to repaint the art from app-art.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path.home() / ".config" / "opendeck"
HERE = Path(__file__).resolve().parent.parent
SNAPSHOT = HERE / "profiles"

REDACTED = "private://redacted-endpoint"
PRIVATE_SUFFIXES = (".nabu.casa", ".ts.net", ".local", ".lan", ".internal")


def is_private(url: str) -> bool:
    """A URL only this network can reach is a secret, whatever it is called."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1") or host.endswith(PRIVATE_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Tailscale hands out 100.64/10, which `is_private` does not cover.
    return addr.is_private or addr.is_loopback or addr in ipaddress.ip_network("100.64.0.0/10")


def scrub(node):
    """Strip embedded art and private URLs, in place, and count what went."""
    stripped = redacted = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                if value.startswith("data:"):
                    node[key] = ""
                    stripped += 1
                elif value.startswith(("http://", "https://")) and is_private(value):
                    node[key] = REDACTED
                    redacted += 1
            else:
                a, b = scrub(value)
                stripped += a
                redacted += b
    elif isinstance(node, list):
        for value in node:
            a, b = scrub(value)
            stripped += a
            redacted += b
    return stripped, redacted


def devices() -> list[str]:
    root = CONFIG / "profiles"
    return sorted(d.name for d in root.iterdir() if d.is_dir()) if root.is_dir() else []


def cmd_save(args: argparse.Namespace) -> int:
    if not (CONFIG / "profiles").is_dir():
        sys.exit(f"no OpenDeck profiles under {CONFIG}")
    total_stripped = total_redacted = 0
    written = []
    for device in devices():
        out = SNAPSHOT / device
        out.mkdir(parents=True, exist_ok=True)
        for path in sorted((CONFIG / "profiles" / device).glob("*.json")):
            data = json.loads(path.read_text())
            stripped, redacted = scrub(data)
            total_stripped += stripped
            total_redacted += redacted
            (out / path.name).write_text(json.dumps(data, indent="\t", sort_keys=True) + "\n")
            written.append(out / path.name)
    apps = CONFIG / "applications.json"
    if apps.is_file():
        SNAPSHOT.mkdir(parents=True, exist_ok=True)
        data = json.loads(apps.read_text())
        (SNAPSHOT / "applications.json").write_text(json.dumps(data, indent="\t", sort_keys=True) + "\n")
        written.append(SNAPSHOT / "applications.json")
    size = sum(p.stat().st_size for p in written)
    print(f"saved   {len(written)} file(s), {size // 1024} KB, to {SNAPSHOT}")
    print(f"        {total_stripped} embedded image(s) stripped, {total_redacted} private URL(s) redacted")
    return 0


def opendeck_running(proc: Path = Path("/proc")) -> bool:
    """True if OpenDeck holds the config.

    Resolve /proc/<pid>/exe rather than matching a command line: the name of the link is
    always "exe", which is how the first version of this check passed every time and let a
    restore run under a live OpenDeck.
    """
    for link in proc.glob("*/exe"):
        try:
            if link.resolve().name == "opendeck":
                return True
        except OSError:
            continue  # a process that exited between the glob and the readlink
    return False


def cmd_restore(args: argparse.Namespace) -> int:
    if not SNAPSHOT.is_dir():
        sys.exit(f"no snapshot at {SNAPSHOT}")
    # OpenDeck holds the profiles in memory and writes them out when it exits, so a restore
    # under a running instance is undone the moment it quits -- or, worse, silently survives
    # and the running copy wins.
    if opendeck_running():
        sys.exit("OpenDeck is running -- stop it first, or it will overwrite this on exit")

    restored, needs_url = 0, []
    for device in sorted(d.name for d in SNAPSHOT.iterdir() if d.is_dir()):
        if args.device and device != args.device:
            continue
        target = CONFIG / "profiles" / device
        target.mkdir(parents=True, exist_ok=True)
        for path in sorted((SNAPSHOT / device).glob("*.json")):
            text = path.read_text()
            if REDACTED in text:
                needs_url.append(f"{device}/{path.stem}")
            (target / path.name).write_text(text)
            restored += 1
    apps = SNAPSHOT / "applications.json"
    if apps.is_file():
        (CONFIG / "applications.json").write_text(apps.read_text())
        restored += 1
    print(f"restored {restored} file(s) to {CONFIG}")
    for name in needs_url:
        print(f"NEEDS URL {name}: a private endpoint was redacted; type it back in OpenDeck")
    print("then start OpenDeck and run `shortcuts icons --push <identity>` to repaint the art")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="copy the live profiles into the repo, scrubbed")
    s.set_defaults(func=cmd_save)
    r = sub.add_parser("restore", help="write the snapshot back (OpenDeck must be stopped)")
    r.add_argument("--device", help="only this device id")
    r.set_defaults(func=cmd_restore)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
