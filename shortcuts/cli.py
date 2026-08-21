import argparse
import json
import sys

from . import keys
from .providers import resolve


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "serve":
        return _serve_main(argv[1:])
    if argv and argv[0] == "icons":
        return _icons_main(argv[1:])
    if argv and argv[0] == "guess":
        return _guess_main(argv[1:])
    if argv and argv[0] == "autofill":
        return _autofill_main(argv[1:])
    return _catalogue_main(argv)


def _serve_main(argv: list[str]) -> int:
    from . import server

    parser = argparse.ArgumentParser(prog="shortcuts serve")
    parser.add_argument("--identity", help="default identity for the picker")
    parser.add_argument("--port", type=int, default=8767, help="first port to try (default 8767)")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    args = parser.parse_args(argv)
    return server.serve(port=args.port, identity=args.identity, no_browser=args.no_browser)


def _icons_main(argv: list[str]) -> int:
    from . import icons

    from . import store

    parser = argparse.ArgumentParser(prog="shortcuts icons")
    parser.add_argument("identity", nargs="?", help="app or app:program identity, e.g. 'orca'")
    parser.add_argument("--generate", action="store_true", help="generate missing icons (network, costs money)")
    parser.add_argument("--publish", action="store_true",
                        help=f"share what was generated to {store.DEFAULT_REPO} (publishes app and action names)")
    parser.add_argument("--limit", type=int, default=None, help="only resolve the first N shortcuts")
    parser.add_argument("--publish-cached", action="store_true",
                        help="share the icons this machine already has, without generating anything")
    parser.add_argument("--push", action="store_true",
                        help="send the chosen icons to a RUNNING OpenDeck, without rewriting its files")
    parser.add_argument("--store-list", action="store_true", help="list what the shared store holds, and exit")
    args = parser.parse_args(argv)

    if args.store_list:
        for path in store.published():
            print(path)
        return 0
    if not args.identity:
        parser.error("identity is required")
    if args.publish and not args.generate:
        parser.error("--publish has nothing to share without --generate")

    if args.publish_cached:
        return _publish_cached(args.identity, args.limit)

    if args.push:
        return _push_live(args.identity)

    shortcuts = resolve(args.identity)
    results = icons.resolve_many(
        shortcuts, generate_missing=args.generate, limit=args.limit, publish=args.publish)
    for sid, result in results.items():
        print(f"{sid}\t{result.origin}\t{'yes' if result.data_uri else 'no'}")
    return 0


def _autofill_main(argv: list[str]) -> int:
    """Catalogue, icons and a profile for one application, in one go.

    The whole of Auto mode for a single identity: whatever a provider knows (asking the local
    model when nothing does), an icon per shortcut, and a profile OpenDeck will load, mapped to
    the identity so it appears when that application takes focus.

    Deliberately not clever about *which* shortcuts get keys -- the first `--limit` of them, in
    provider order. Choosing is what the picker is for; this is for filling a deck without
    sitting there.
    """
    from . import icons, opendeck
    from .providers import resolve as resolve_shortcuts

    parser = argparse.ArgumentParser(
        prog="shortcuts autofill",
        description="Build a catalogue, resolve icons and write a profile for one identity.",
    )
    parser.add_argument("identity", help="the WM_CLASS the focus daemon publishes, e.g. 'google-chrome'")
    parser.add_argument("--device", default=None, help="device id (default: the only one)")
    parser.add_argument("--limit", type=int, default=15, help="keys to fill (default 15, the deck's count)")
    parser.add_argument("--ids", help="comma-separated shortcut ids, in the order they take keys; "
                                      "overrides --bank's slice of the catalogue")
    parser.add_argument("--bank", type=int, default=1,
                        help="which page of keys (1 is the plain identity, 2+ publish <identity>#N)")
    parser.add_argument("--generate", action="store_true", help="draw missing icons (costs money)")
    parser.add_argument("--publish", action="store_true", help="share what was generated")
    parser.add_argument("--dry-run", action="store_true", help="say what would happen, write nothing")
    args = parser.parse_args(argv)

    device = args.device or next(iter(opendeck.devices()), None)
    if device is None:
        print("error: no device under ~/.config/opendeck/profiles", file=sys.stderr)
        return 1

    records = resolve_shortcuts(args.identity, build_missing=True)
    if not records:
        print(f"error: nothing known about {args.identity!r} and the model gave us nothing",
              file=sys.stderr)
        return 1
    slots = min(args.limit, opendeck.LAST_KEY - opendeck.FIRST_KEY + 1)
    if args.bank < 1:
        parser.error("--bank counts from 1")
    if args.ids:
        # An explicit page: the keys are chosen, not sliced. A page of solid features is not a
        # contiguous run of any catalogue, and reordering the file to fake one would break the
        # other pages.
        by_id = {sc.id: sc for sc in records}
        wanted = [i.strip() for i in args.ids.split(",") if i.strip()]
        missing = [i for i in wanted if i not in by_id]
        if missing:
            print(f"error: not in {args.identity}: {', '.join(missing)}", file=sys.stderr)
            return 1
        chosen = [by_id[i] for i in wanted][:slots]
        start = 0
    else:
        # Page 2 carries the shortcuts page 1 had no room for, and so on.
        start = (args.bank - 1) * slots
        chosen = records[start:start + slots]
    if not chosen:
        print(f"error: {args.identity} has {len(records)} shortcut(s); page {args.bank} would be empty",
              file=sys.stderr)
        return 1
    banked = args.identity if args.bank == 1 else f"{args.identity}#{args.bank}"
    print(f"{banked}: {len(records)} shortcut(s), filling {len(chosen)} key(s) "
          f"from #{start + 1}")

    results = icons.resolve_many(chosen, generate_missing=args.generate, publish=args.publish)
    origins: dict[str, int] = {}
    for result in results.values():
        origins[result.origin] = origins.get(result.origin, 0) + 1
    print(f"  icons: {origins}")
    if args.dry_run:
        print("  (dry run: nothing written)")
        return 0

    profile = opendeck.profile_name_for(banked)
    data = opendeck.load_profile(device, profile)
    keys = list(data.get("keys") or [])
    while len(keys) <= opendeck.LAST_KEY:
        keys.append(None)
    for offset, sc in enumerate(chosen):
        position = opendeck.FIRST_KEY + offset
        keys[position] = opendeck.input_key(
            position, sc.label, sc.tokens, results[sc.id].data_uri)
    # The strip is the way out of a page: without it a per-application profile is a room with
    # no door. Only fill a strip key that is empty, so a deliberate one is never overwritten.
    for position, (mode, label) in opendeck.MODE_KEYS.items():
        if not keys[position]:
            keys[position] = opendeck.mode_key(position, mode, label)
    data["keys"] = keys
    # Every page carries the dial, or you can turn onto a page you cannot turn off.
    data["sliders"] = [opendeck.dial_key()]
    try:
        opendeck.save_profile(device, profile, data)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    opendeck.map_application(banked, device, profile)
    print(f"  wrote profile {profile!r} on {device} and mapped {banked!r} to it")
    return 0


def _guess_main(argv: list[str]) -> int:
    from .providers import guessed

    parser = argparse.ArgumentParser(
        prog="shortcuts guess",
        description="Ask the local model for an app nobody has written a catalogue for. "
        "Slow, offline, and cached: run it once per app.",
    )
    parser.add_argument("identity", help="app identity, e.g. 'inkscape'")
    parser.add_argument("--model", default=None, help=f"Ollama model (default {guessed.DEFAULT_MODEL})")
    parser.add_argument("--host", default=None, help=f"Ollama host (default {guessed.DEFAULT_HOST})")
    parser.add_argument("--force", action="store_true", help="ask again even if a catalogue is cached")
    args = parser.parse_args(argv)

    path = guessed.cache_file(args.identity)
    if path.is_file() and not args.force:
        print(f"already guessed: {path} (use --force to ask again)", file=sys.stderr)
        records = guessed.shortcuts(args.identity)
    else:
        records = guessed.build(args.identity, model=args.model, host=args.host)
    if not records:
        print("error: nothing usable came back; see the log for why", file=sys.stderr)
        return 1
    for s in records:
        print(f"{s.combo}\t{s.provenance}\t{s.label}")
    print(f"cached in {path}", file=sys.stderr)
    return 0


def _push_live(identity: str) -> int:
    """Refresh a running OpenDeck's keys with the icons currently chosen.

    Apply rewrites profile files, which OpenDeck holds in memory and overwrites on exit, so it
    needs the app stopped. Changing your mind about an icon afterwards should not cost a
    restart: this pushes the chosen art straight into the running instance instead.

    Keys are matched by the RON tokens they send, which is what makes a key *that* shortcut --
    not by label, which repeats.
    """
    from . import icons, opendeck

    device = next(iter(opendeck.devices()), None)
    if device is None:
        print("error: no device under ~/.config/opendeck/profiles", file=sys.stderr)
        return 1
    profile = opendeck.profile_name_for(identity)
    data = opendeck.load_profile(device, profile)
    # A page is the same application with a "#N" suffix, and no provider knows that suffix:
    # ask about the identity itself, or pages 2+ resolve to the bare app and match nothing.
    base = identity.split("#", 1)[0]
    # One keystroke can belong to more than one shortcut. Orca CAD is OrcaSlicer plus a CAD
    # workbench, so both catalogues answer and "p" is the SLA-support gizmo in the slicer;
    # inside the workbench the same "p" is Point while a sketch is open and Show/hide planes
    # when none is. Which one a KEY means is not a property of the keystroke, so ask the key:
    # the profile records what it is for in the state's name.
    candidates: dict[str, list] = {}
    for sc in resolve(base):
        candidates.setdefault(sc.tokens, []).append(sc)

    def pick(tokens: str, key: dict):
        options = candidates.get(tokens) or []
        if len(options) <= 1:
            return options[0] if options else None
        wanted = ((key.get("states") or [{}])[0].get("name")
                  or (key.get("action") or {}).get("tooltip") or "")
        for sc in options:
            if sc.label == wanted:
                return sc
        for sc in options:
            if sc.app == base:
                return sc
        return options[0]

    pushed = missing = unmatched = 0
    for position, key in enumerate(data.get("keys") or []):
        if not key:
            continue
        sc = pick((key.get("settings") or {}).get("down") or "", key)
        if sc is None:
            unmatched += 1
            continue
        result = icons.resolve(sc)
        if result.data_uri is None:
            missing += 1
            continue
        if opendeck.push_image(device, profile, position, result.data_uri):
            print(f"{position}\t{sc.id}\t{result.origin}")
            pushed += 1
        else:
            missing += 1
    print(f"pushed {pushed} to the running OpenDeck ({profile} on {device}); "
          f"{unmatched} key(s) not ours, {missing} without an icon", file=sys.stderr)
    print("OpenDeck acknowledges nothing, so check the deck; the change persists when it exits.",
          file=sys.stderr)
    return 0 if pushed else 1


def _publish_cached(identity: str, limit: int | None) -> int:
    """Share the icons already sitting in this machine's cache.

    The usual `--generate --publish` pairing cannot do this: it would pay to draw a glyph that
    already exists. An application's own art is skipped rather than uploaded -- it is not ours
    to redistribute, and it never reaches the cache in the first place.
    """
    from . import icons, store

    shortcuts = resolve(identity)
    if limit is not None:
        shortcuts = shortcuts[:limit]
    shared = skipped = failed = 0
    for sc in shortcuts:
        if sc.icon:
            skipped += 1
            continue
        result = icons.resolve(sc)
        if result.origin != "cache":
            skipped += 1
            continue
        png = (icons.cache_dir() / f"{icons.cache_key(sc)}.png").read_bytes()
        if store.publish(sc, png, "cache", message=f"Add {store.path_for(sc)}"):
            print(f"{sc.id}\t{store.path_for(sc)}")
            shared += 1
        else:
            failed += 1
    print(f"shared {shared}, skipped {skipped}, failed {failed}", file=sys.stderr)
    return 1 if failed else 0


def _catalogue_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shortcuts")
    parser.add_argument("identity", nargs="?", help="app or app:program identity, e.g. 'kitty' or 'kitty:claude'")
    parser.add_argument("--json", action="store_true", help="emit full records including tokens")
    parser.add_argument("--check", metavar="COMBO", help="print the encoding of a single combo")
    args = parser.parse_args(argv)

    if args.check:
        try:
            print(keys.encode(args.check))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.identity:
        parser.error("identity is required")

    shortcuts = resolve(args.identity)
    if args.json:
        records = [
            {
                "id": s.id,
                "app": s.app,
                "label": s.label,
                "combo": s.combo,
                "provenance": s.provenance,
                "source": s.source,
                "category": s.category,
                "icon": s.icon,
                "tokens": s.tokens,
            }
            for s in shortcuts
        ]
        print(json.dumps(records, indent=2))
    else:
        for s in shortcuts:
            print(f"{s.combo}\t{s.category}\t{s.provenance}\t{s.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
