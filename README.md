# opendeck-shortcuts

Shortcut catalogue for the OpenDeck, with pluggable providers and provenance.

Answers *"what shortcuts does `<identity>` have"* and turns a key combo into the
exact RON string OpenDeck's *Simulate Input* action executes.

An identity is either `app` (e.g. `kitty`) or `app:program` (e.g.
`kitty:claude`), produced upstream.

## Layout

```
shortcuts/
  model.py              Shortcut dataclass + Provenance literal
  keys.py               combo -> RON Token list encoder (the exact part)
  opendeck.py           OpenDeck profile IO (read/write, no HTTP)
  server.py             localhost picker server
  assets/picker.html    the picker page (inline CSS + JS)
  providers/
    __init__.py         Provider protocol + resolve()
    kitty.py            extracts `map` lines from the kitty config
    curated.py          loads catalogue/*.json
    orca.py             extracts shortcuts + icons from an OrcaSlicer tree
  cli.py                command line interface
catalogue/
  chrome.json           curated Chrome bindings
  claude.json           curated Claude Code bindings
  orca.snapshot.json    OrcaSlicer fallback, for machines with no source tree
tests/
  test_keys.py          encoder tests
  test_providers.py     provider + resolve tests
  test_orca.py          OrcaSlicer provider tests
  test_opendeck.py      profile IO tests
  test_server.py        picker server tests
  fixtures/kitty.conf   the user's real kitty config
  fixtures/KBShortcutsDialog_excerpt.cpp
```

## Usage

```sh
python3 -m shortcuts kitty             # combo<TAB>provenance<TAB>label per row
python3 -m shortcuts kitty:chrome      # both segments
python3 -m shortcuts kitty --json      # full records, incl. tokens
python3 -m shortcuts --check 'ctrl+shift+o'
```

`--check` exits non-zero when the combo is rejected.

## The picker

```sh
python3 -m shortcuts serve [--identity X] [--port N] [--no-browser]
```

Serves a localhost page that lists an identity's shortcuts and lets you drag them
onto the 15 assignable deck keys, then writes the OpenDeck profile and the
application mapping. Binds 127.0.0.1 only, tries the next ten ports if the
default 8767 is taken, and opens the browser unless `--no-browser` is given.

The deck is a numpad in portrait: the top strip holds two reserved screen
buttons (Launcher, Auto) and the encoder's screen (Dial), then 5 rows of 3 main
keys. Positions 0-2 are reserved and never written; only 3-17 are assignable.
Nothing is written until Apply is pressed, and Apply is refused while OpenDeck is
running because it rewrites profiles from memory on exit.

## The encoder (`shortcuts/keys.py`)

`encode(combo)` returns a RON list of `enigo::agent::Token` values, parsed on
the OpenDeck side with `ron::from_str::<Vec<Token>>`.

* Modifiers are pressed in the canonical order **ctrl, alt, shift, meta**, the
  main key is `Click`ed, then modifiers are released in reverse order.
* Single characters become `Unicode('<char>')`, always lowercased — a capital
  is never folded into an implicit shift; the caller states shift explicitly.
* `f1`..`f35` map to `F1`..`F35`; named keys use their enigo spelling
  (`return` -> `Return`, `up` -> `UpArrow`, ...).
* Unknown keys, empty combos and modifier-only combos raise `ValueError`.
  Nothing is ever guessed.

## Providers

* **kitty** (`extracted`) — parses `map` lines from the user's kitty config,
  following `include` directives (depth cap 5, cycle-safe). Later lines
  override earlier ones for the same combo; `no_op`/empty actions and combos
  the encoder rejects are dropped.
* **curated** (`curated`) — reads `catalogue/*.json`, each describing one app
  with a documentation `source`. Entries are only added when the binding is
  known to be real: an invented shortcut silently does nothing, which is worse
  than no key at all. This is why `claude.json` is deliberately minimal.
* **orca** (`extracted`) — parses `src/slic3r/GUI/KBShortcutsDialog.cpp` from
  an OrcaSlicer source tree (`$ORCA_SOURCE`, then a list of known checkouts),
  falling back to `catalogue/orca.snapshot.json` when no tree is present.
  Non-deterministic key expressions (mouse actions, `Any arrow`, the `1-9`
  range, bare `shift`, anything non-ASCII) are dropped, never guessed; the
  Apple side of `#ifdef __APPLE__` branches is discarded. Each shortcut is
  matched to a `resources/images/*.svg` only on an exact stem match, so most
  entries carry no icon. `python3 -m shortcuts.providers.orca --snapshot <tree>`
  regenerates the committed snapshot.

`resolve(identity)` concatenates every matching provider per segment and
de-duplicates by `(app, combo)`, keeping the strongest provenance
(`extracted` > `curated` > `guessed`). A failing provider is logged and
skipped.
