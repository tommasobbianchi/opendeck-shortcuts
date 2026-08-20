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
  icons.py              icon resolution: app art, then cache, then store, then generated
  store.py              the shared icon store (fetch anonymous, publish opt-in)
  focus.py              which identities opendeck-focus has actually published
  opendeck.py           OpenDeck profile IO (read/write, no HTTP)
  server.py             localhost picker server
  assets/picker.html    the picker page (inline CSS + JS)
  providers/
    __init__.py         Provider protocol + resolve()
    kitty.py            extracts `map` lines from the kitty config
    curated.py          loads catalogue/*.json
    orca.py             extracts shortcuts + icons from an OrcaSlicer tree
    guessed.py          last resort: asks a local model, validates, caches
  cli.py                command line interface
catalogue/
  chrome.json           curated Chrome bindings
  claude.json           curated Claude Code bindings
  orca.snapshot.json    OrcaSlicer fallback, for machines with no source tree
tests/
  test_keys.py          encoder tests
  test_focus.py         published-identity tests
  test_guessed.py       guessed-provider tests (no network)
  test_store.py         shared-store tests (transport mocked)
  conftest.py           turns the store off, so no test reaches the network
  test_providers.py     provider + resolve tests
  test_orca.py          OrcaSlicer provider tests
  test_opendeck.py      profile IO tests
  test_server.py        picker server tests
  test_icons.py         icon resolution tests
  fixtures/kitty.conf   the user's real kitty config
  fixtures/KBShortcutsDialog_excerpt.cpp
  fixtures/tiny.svg     a hand-written SVG for the rasterise test
```

## Usage

```sh
python3 -m shortcuts kitty             # combo<TAB>provenance<TAB>label per row
python3 -m shortcuts kitty:chrome      # both segments
python3 -m shortcuts kitty --json      # full records, incl. tokens
python3 -m shortcuts --check 'ctrl+shift+o'
python3 -m shortcuts icons orca        # id<TAB>origin<TAB>has-data-uri per row
python3 -m shortcuts icons orca --limit 8 --generate
```

`--check` exits non-zero when the combo is rejected.

```sh
python3 -m shortcuts guess inkscape       # no catalogue? ask the local model, once
```

## Identity, and why the picker nags about it

OpenDeck matches an application by the WM_CLASS its watcher reads, which on GNOME Wayland is
whatever `opendeck-focus` publishes: `OrcaSlicer`, `OrcaBelt2608`, `kitty:claude`. A catalogue
name like `orca` is a different string, and a profile mapped under it never fires — silently,
which is the worst way to fail.

So the daemon writes every class it publishes to `~/.cache/opendeck-focus/seen.json`, and
`shortcuts/focus.py` reads it. The picker offers those names in the identity box and says so
when the name in the box has never been published. Applying anyway is allowed: setting up an
app before its first focus is legitimate.

## Guessing (`shortcuts/providers/guessed.py`)

For an application no provider knows, a local Ollama model is asked for a catalogue. Two rules
keep a guess honest:

* every combo is run through `keys.encode`, so an invented syntax is dropped rather than
  written to a key that does nothing;
* the answer is cached per app under `~/.cache/opendeck-shortcuts/catalogue`, editable by hand,
  and never asked for twice.

Records come back with provenance `guessed`, which loses to every real source. Nothing triggers
it implicitly — `resolve(identity, build_missing=True)`, `shortcuts guess`, or the picker's
button, which appears only when nothing at all is known. `$OPENDECK_GUESS_MODEL` and
`$OLLAMA_HOST` override the defaults.

## Icon resolution (`shortcuts/icons.py`)

Each key needs a 96x96 image. Three sources, in order, never guessing:

1. **App art** — `Shortcut.icon`, the artwork the application ships (OrcaSlicer's
   own SVGs). Free, exact, offline. SVGs are rasterised through ImageMagick
   `convert`; `.png`/`.jpg`/`.jpeg`/`.webp` through Pillow.
2. **Cache** — `~/.cache/opendeck-shortcuts/icons/<key>.png`, overridable by
   `$OPENDECK_ICON_CACHE`. Anything resolved once is never resolved twice.
3. **Store** — art someone already generated for this action, fetched from
   [opendeck-icons](https://github.com/tommasobbianchi/opendeck-icons) and cached
   on arrival. Anonymous, free, and skipped when the network is not there.
4. **Generated** — only when explicitly asked for, via the local `infsh` binary.
   It costs money and needs the network, so it is never implicit.

`python3 -m shortcuts icons <identity>` reports the origin of every key's icon
(`app`, `cache`, `generated`, or `none`). Without `--generate` it makes no
network calls at all; the generated prompt asks for a flat minimalist glyph with
**no text** (the deck draws its own text over the image), and the result is
cached. `POST /api/apply` accepts `"generate": true` to allow step 3 and reports
per-key origins as `{"icons": {"app": n, "cache": n, "generated": n, "none": n}}`;
it defaults to false so applying never spends money unasked.

## The shared store (`shortcuts/store.py`)

Generating a glyph costs money and minutes; doing it again on the next machine costs the same
for a byte-identical result. So generated art goes to a public repo, keyed by application and
action at a readable path — `icons/orca/new_project.png` — and is fetched over
`raw.githubusercontent.com` before anything is generated.

Two boundaries hold it up:

* **Only generated art may be published.** `store.publish` refuses any other origin. An
  application's own icons are its own — OrcaSlicer's are AGPL, Chrome's a trademark — so they
  are resolved locally on each machine and never uploaded. This is what lets the store be
  public at all.
* **Uploading is opt-in, every time.** A path names an app and an action, which is telemetry
  about what you run. Fetching is anonymous; publishing takes `--publish` on the CLI or
  `"publish": true` on `POST /api/apply`, and both need `--generate` first, since there is
  nothing of ours to share otherwise.

```sh
python3 -m shortcuts icons orca --generate --publish   # share what this run generated
python3 -m shortcuts icons --store-list                # what the store holds
```

`OPENDECK_ICON_STORE=0` turns it off for an offline or a private machine;
`OPENDECK_ICON_REPO=owner/name` points at a different store. Hostile names cannot escape the
store: every path segment is sanitised, so a `Shortcut` whose app is `../..` lands at
`icons/unnamed/…`.

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
