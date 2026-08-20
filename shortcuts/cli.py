import argparse
import json
import sys

from . import keys
from .providers import resolve


def main(argv: list[str] | None = None) -> int:
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
