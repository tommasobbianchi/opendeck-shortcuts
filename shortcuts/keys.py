"""Encode key combos as RON Token lists for OpenDeck's Simulate Input action.

The output of :func:`encode` is a RON list of ``enigo::agent::Token`` values,
parseable by ``ron::from_str::<Vec<Token>>`` on the OpenDeck side.
"""

MODIFIER_ORDER = ("ctrl", "alt", "shift", "meta")

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "opt": "alt",
    "option": "alt",
    "shift": "shift",
    "super": "meta",
    "win": "meta",
    "windows": "meta",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
}

_MOD_RON = {"ctrl": "Control", "alt": "Alt", "shift": "Shift", "meta": "Meta"}

_NAMED_ALIASES = {
    "enter": "return",
    "return": "return",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "escape": "escape",
    "esc": "escape",
    "home": "home",
    "end": "end",
    "page_up": "page_up",
    "pageup": "page_up",
    "page_down": "page_down",
    "pagedown": "page_down",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "insert": "insert",
    "equal": "=",
    "minus": "-",
    "plus": "+",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "slash": "/",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "grave": "`",
    "bracket_left": "[",
    "bracket_right": "]",
}

_NAMED_RON = {
    "return": "Return",
    "tab": "Tab",
    "space": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "escape": "Escape",
    "home": "Home",
    "end": "End",
    "page_up": "PageUp",
    "page_down": "PageDown",
    "up": "UpArrow",
    "down": "DownArrow",
    "left": "LeftArrow",
    "right": "RightArrow",
    "insert": "Insert",
}


def _canonical_main(token: str) -> str:
    if len(token) == 1:
        return token
    if token in _NAMED_ALIASES:
        return _NAMED_ALIASES[token]
    if token[0] == "f" and token[1:].isdigit() and 1 <= int(token[1:]) <= 35:
        return token
    raise ValueError(f"unknown key: {token}")


def parse(combo: str) -> tuple[list[str], str]:
    """Return ``(modifiers, main_key)`` in canonical form.

    Modifiers are returned in canonical order (ctrl, alt, shift, meta).
    """
    if not combo or not combo.strip():
        raise ValueError("empty combo")
    parts = [p.strip() for p in combo.lower().split("+")]
    mods: list[str] = []
    mains: list[str] = []
    for p in parts:
        if not p:
            continue
        if p in _MODIFIER_ALIASES:
            mods.append(_MODIFIER_ALIASES[p])
        else:
            mains.append(_canonical_main(p))
    if len(mains) > 1:
        raise ValueError(f"multiple main keys: {mains[1]}")
    if not mains:
        raise ValueError(f"no main key in combo: {combo}")
    mods.sort(key=MODIFIER_ORDER.index)
    return mods, mains[0]


def normalise(combo: str) -> str:
    """Return the canonical ``+``-joined spelling of a combo."""
    mods, main = parse(combo)
    return "+".join(mods + [main])


def _char_literal(c: str) -> str:
    if c == "'":
        return "\\'"
    if c == "\\":
        return "\\\\"
    return c


def _main_ron(main: str) -> str:
    if len(main) == 1:
        return f"Unicode('{_char_literal(main)}')"
    if main in _NAMED_RON:
        return _NAMED_RON[main]
    if main[0] == "f" and main[1:].isdigit():
        return main.upper()
    raise ValueError(f"unknown key: {main}")


def encode(combo: str) -> str:
    """Encode a combo as a RON list of enigo ``Token`` values."""
    mods, main = parse(combo)
    tokens = [f"Key({_MOD_RON[m]}, Press)" for m in mods]
    tokens.append(f"Key({_main_ron(main)}, Click)")
    tokens += [f"Key({_MOD_RON[m]}, Release)" for m in reversed(mods)]
    return "[" + ", ".join(tokens) + "]"
