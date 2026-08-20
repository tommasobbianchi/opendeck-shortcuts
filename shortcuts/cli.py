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

    parser = argparse.ArgumentParser(prog="shortcuts icons")
    parser.add_argument("identity", help="app or app:program identity, e.g. 'orca'")
    parser.add_argument("--generate", action="store_true", help="generate missing icons (network, costs money)")
    parser.add_argument("--limit", type=int, default=None, help="only resolve the first N shortcuts")
    args = parser.parse_args(argv)

    shortcuts = resolve(args.identity)
    results = icons.resolve_many(shortcuts, generate_missing=args.generate, limit=args.limit)
    for sid, result in results.items():
        print(f"{sid}\t{result.origin}\t{'yes' if result.data_uri else 'no'}")
    return 0


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
