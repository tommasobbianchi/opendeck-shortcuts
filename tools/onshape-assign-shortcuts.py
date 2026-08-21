#!/usr/bin/env python3
"""Assign Onshape keyboard shortcuts by driving Onshape's own editor.

A deck key can only send a keystroke, and most of Onshape's tools -- mirror, chamfer, shell,
hole, thread, boolean, draft, rib, transform, derived, loft, sweep, pattern -- ship with no
shortcut at all. Onshape lets you bind them yourself, one dialog at a time, in
Settings -> Customize keyboard shortcuts. Twenty tools is twenty trips through that dialog.

So this drives the dialog instead. It talks to a Chrome that is already signed in, over the
DevTools protocol: pick the category, find the row by its label, open the editor, press the
combination, read what Onshape says about it, and confirm -- or move to the next candidate when
Onshape reports the combination is already in use. Onshape's own conflict check is what makes
this safe: nothing is guessed about what is free.

    ssh -f -N -L 9222:127.0.0.1:9222 tommaso@behemoth      # if Chrome runs elsewhere
    python3 tools/onshape-assign-shortcuts.py --dry-run
    python3 tools/onshape-assign-shortcuts.py

Chrome must have been started with --remote-debugging-port=9222. Nothing here handles the
password: sign in first, in that browser.
"""

import argparse
import asyncio
import json
import sys
import urllib.request

try:
    import websockets
except ImportError:                                        # pragma: no cover - dependency hint
    raise SystemExit("pip install websockets")

DEBUGGER = "http://127.0.0.1:9222"

MODIFIERS = {"alt": 1, "ctrl": 2, "meta": 4, "shift": 8}
LETTERS = {chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)}

#: What to bind, and what to try. The first candidate Onshape reports as free wins; a tool
#: whose candidates are all taken is reported rather than forced, because stealing a binding
#: from a tool you already use is worse than leaving a deck key blank.
WANTED = [
    ("Part Studio", "Mirror",           ["alt+m", "alt+shift+m", "alt+i"]),
    ("Part Studio", "Chamfer",          ["alt+h", "alt+shift+c", "alt+j"]),
    ("Part Studio", "Shell",            ["alt+s", "alt+shift+s", "alt+z"]),
    ("Part Studio", "Hole",             ["alt+o", "alt+shift+h", "alt+9"]),
    ("Part Studio", "External thread",  ["alt+t", "alt+shift+t", "alt+8"]),
    ("Part Studio", "Boolean",          ["alt+b", "alt+shift+b", "alt+7"]),
    ("Part Studio", "Draft",            ["alt+d", "alt+shift+d", "alt+6"]),
    ("Part Studio", "Rib",              ["alt+r", "alt+shift+r", "alt+5"]),
    ("Part Studio", "Transform",        ["alt+n", "alt+shift+n", "alt+4"]),
    ("Part Studio", "Derived",          ["alt+v", "alt+shift+v", "alt+3"]),
    ("Part Studio", "Loft",             ["alt+l", "alt+shift+l", "alt+2"]),
    ("Part Studio", "Sweep",            ["alt+w", "alt+shift+w", "alt+1"]),
    ("Part Studio", "Linear pattern",   ["alt+p", "alt+shift+p", "alt+0"]),
    ("Part Studio", "Circular pattern", ["alt+k", "alt+shift+k"]),
    ("Part Studio", "Plane",            ["alt+e", "alt+shift+e"]),
    ("Part Studio", "Split",            ["alt+x", "alt+shift+x"]),
    ("Sketch",      "Mirror sketch",    ["alt+g", "alt+shift+g"]),
    ("Sketch",      "Slot",             ["alt+y", "alt+shift+y"]),
    ("Sketch",      "Sketch chamfer",   ["alt+q", "alt+shift+q"]),
]


def page_target():
    for page in json.load(urllib.request.urlopen(f"{DEBUGGER}/json/list", timeout=5)):
        if page.get("type") == "page":
            return page
    raise SystemExit("no page to drive; is Chrome running with --remote-debugging-port=9222?")


class Browser:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def send(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            message = json.loads(await self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    async def js(self, expression):
        out = await self.send("Runtime.evaluate", expression=expression,
                              returnByValue=True, awaitPromise=True)
        if out.get("exceptionDetails"):
            raise RuntimeError(out["exceptionDetails"].get("text"))
        return out.get("result", {}).get("value")

    async def press(self, combo):
        """Send one chord as real key events, the way the dialog expects to hear it."""
        *names, letter = combo.split("+")
        modifiers = 0
        for name in names:
            if name not in MODIFIERS:
                raise ValueError(f"unknown modifier {name!r} in {combo!r}")
            modifiers |= MODIFIERS[name]
        if letter in LETTERS:
            code, vk = f"Key{letter.upper()}", LETTERS[letter]
        elif letter.isdigit():
            code, vk = f"Digit{letter}", ord(letter)
        else:
            raise ValueError(f"unsupported key {letter!r} in {combo!r}")
        for kind in ("rawKeyDown", "keyUp"):
            await self.send("Input.dispatchKeyEvent", type=kind, modifiers=modifiers, key=letter,
                            code=code, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)


async def open_category(browser, category):
    await browser.js(f"""(() => {{
        const el = [...document.querySelectorAll('.osx-shortcut-category-header-list *')]
            .find(e => (e.innerText||'').trim() === {json.dumps(category)} && !e.children.length);
        (el?.closest('li,a,button') || el)?.click();
        return !!el;
    }})()""")
    await asyncio.sleep(1.2)


async def current_key(browser, label):
    return await browser.js(f"""(() => {{
        const row = [...document.querySelectorAll('.osx-keyboard-shortcut-container')]
            .find(r => (r.querySelector('.osx-shortcut-label')?.innerText||'').trim() === {json.dumps(label)});
        return row ? (row.querySelector('.osx-shortcut-keys')?.innerText||'').replace(/\\s+/g,' ').trim() : null;
    }})()""")


async def assign(browser, category, label, candidates, dry_run):
    await open_category(browser, category)
    existing = await current_key(browser, label)
    if existing is None:
        return "missing", None, "no such row"
    if not existing.lower().startswith("unassigned"):
        return "kept", existing, "already bound"

    for combo in candidates:
        opened = await browser.js(f"""(() => {{
            const row = [...document.querySelectorAll('.osx-keyboard-shortcut-container')]
                .find(r => (r.querySelector('.osx-shortcut-label')?.innerText||'').trim() === {json.dumps(label)});
            const edit = row?.querySelector('.edit-action');
            if (!edit) return false;
            edit.click();
            return true;
        }})()""")
        if not opened:
            return "missing", None, "no edit control"
        await asyncio.sleep(0.8)
        await browser.js("""(() => {
            document.querySelector('.customize-shortcut-dialog-window input.form-control')?.focus();
        })()""")
        await browser.press(combo)
        await asyncio.sleep(0.7)
        state = await browser.js("""(() => {
            const d = document.querySelector('.customize-shortcut-dialog-window');
            return JSON.stringify({
                value: d?.querySelector('input.form-control')?.value || '',
                text: (d?.innerText || '').replace(/\\s+/g, ' ')});
        })()""")
        state = json.loads(state or "{}")
        taken = "already in use" in state.get("text", "").lower()
        if taken or dry_run:
            await browser.js("""(() => {
                document.querySelector('.ns-dialog-button-cancel')?.click();
            })()""")
            await asyncio.sleep(0.5)
            if dry_run:
                return ("would take" if not taken else "conflict"), combo, state.get("text", "")[:90]
            continue
        await browser.js("""(() => { document.querySelector('.ns-dialog-button-ok')?.click(); })()""")
        await asyncio.sleep(1.2)
        now = await current_key(browser, label)
        if now and not now.lower().startswith("unassigned"):
            return "assigned", now, ""
        return "failed", combo, f"still {now!r} after confirming"
    return "conflict", None, "every candidate was already in use"


async def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="say what would happen, change nothing")
    parser.add_argument("--only", action="append", help="restrict to these labels")
    args = parser.parse_args()

    wanted = [w for w in WANTED if not args.only or w[1] in args.only]
    target = page_target()
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
        browser = Browser(ws)
        await browser.send("Page.enable")
        await browser.send("Runtime.enable")
        await browser.send("Page.navigate",
                           url="https://cad.onshape.com/user/settings?focusView=customize-keyboard-shortcuts")
        await asyncio.sleep(9)

        tally = {}
        for category, label, candidates in wanted:
            outcome, key, note = await assign(browser, category, label, candidates, args.dry_run)
            tally[outcome] = tally.get(outcome, 0) + 1
            print(f"{label:20} {outcome:10} {key or '-':14} {note}")
        print("\n" + ", ".join(f"{n} {k}" for k, n in sorted(tally.items())), file=sys.stderr)
    return 0


raise SystemExit(asyncio.run(main()))
