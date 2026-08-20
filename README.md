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
  providers/
    __init__.py         Provider protocol + resolve()
    kitty.py            extracts `map` lines from the kitty config
    curated.py          loads catalogue/*.json
  cli.py                command line interface
catalogue/
  chrome.json           curated Chrome bindings
  claude.json           curated Claude Code bindings
tests/
  test_keys.py          encoder tests
  test_providers.py     provider + resolve tests
  fixtures/kitty.conf   the user's real kitty config
```

## Usage

```sh
python3 -m shortcuts kitty             # combo<TAB>provenance<TAB>label per row
python3 -m shortcuts kitty:chrome      # both segments
python3 -m shortcuts kitty --json      # full records, incl. tokens
python3 -m shortcuts --check 'ctrl+shift+o'
```

`--check` exits non-zero when the combo is rejected.

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

`resolve(identity)` concatenates every matching provider per segment and
de-duplicates by `(app, combo)`, keeping the strongest provenance
(`extracted` > `curated` > `guessed`). A failing provider is logged and
skipped.
