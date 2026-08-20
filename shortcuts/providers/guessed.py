"""Last-resort catalogue for an application nobody has written one for.

Every other provider reads a real source: kitty's config, OrcaSlicer's own source tree, a
curated file someone checked. This one asks a local language model, which is a different kind
of answer entirely -- hence the ``guessed`` provenance, which loses to every real source when
they disagree about the same combo.

Two rules make a guess safe enough to put on a key:

* **Every combo goes through the encoder.** A shortcut invented in a syntax that does not
  exist is dropped here, rather than written into a profile as a key that quietly does nothing.
* **Nothing is guessed twice.** The answer is cached per application under
  ``~/.cache/opendeck-shortcuts/catalogue``, so the slow path happens once and the file stays
  editable by hand: correcting a guess is deleting a line, not fighting the model.

The model is local (Ollama), so unlike icon generation this costs no money and needs no network
beyond localhost. It is still slow -- tens of seconds -- so ``resolve`` never triggers it
implicitly; something has to ask.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path

from .. import keys
from ..model import Shortcut

name = "guessed"

log = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3-vl:8b-instruct-q4_K_M"
DEFAULT_HOST = "http://127.0.0.1:11434"

#: Enough to fill the deck several times over. A model asked for "all" of them starts inventing.
MAX_SHORTCUTS = 40


def cache_dir() -> Path:
    override = os.environ.get("OPENDECK_CATALOGUE")
    if override:
        return Path(override).expanduser()
    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".cache"
    return base / "opendeck-shortcuts" / "catalogue"


def cache_file(segment: str) -> Path:
    # The segment reaches us from a WM_CLASS, so it is not automatically a safe file name.
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in segment)
    return cache_dir() / f"{safe}.json"


def matches(segment: str) -> bool:
    return cache_file(segment).is_file()


def shortcuts(segment: str) -> list[Shortcut]:
    path = cache_file(segment)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception:
        log.exception("could not read guessed catalogue %s", path)
        return []
    return _records(segment, data)


def _records(segment: str, data: dict) -> list[Shortcut]:
    source = data.get("source") or "guessed"
    out: list[Shortcut] = []
    for entry in data.get("shortcuts") or []:
        try:
            out.append(
                Shortcut(
                    id=f"{segment}.{entry['id']}",
                    app=segment,
                    label=entry["label"],
                    combo=entry["combo"],
                    provenance="guessed",
                    source=source,
                )
            )
        except (KeyError, TypeError):
            log.warning("skipping malformed guessed entry in %s: %r", segment, entry)
    return out


def app_name(segment: str) -> str:
    """The identity as a person would name the application.

    An identity is a WM_CLASS, and those are rarely the name of anything: GNOME publishes
    reverse-DNS (`org.gnome.Nautilus`), snaps publish the package twice
    (`telegram-desktop_telegram-desktop`). Asking a model about those strings verbatim is
    asking about something it has never heard of, and it answers accordingly -- with nothing,
    or with a stall.
    """
    name = segment.split(":")[-1].strip()
    # snap: <package>_<package>, sometimes <package>_<binary>
    if "_" in name:
        head, _, tail = name.partition("_")
        if head == tail:
            name = head
    # reverse-DNS: org.gnome.Nautilus, com.discordapp.Discord
    parts = name.split(".")
    if len(parts) >= 3 and all(parts[:-1]):
        name = parts[-1]
    return name.replace("-", " ").replace("_", " ").strip() or segment


def prompt_for(segment: str) -> str:
    app = app_name(segment)
    return (
        f'List the most useful keyboard shortcuts of the application "{app}" on Linux.\n'
        "Only shortcuts you are confident actually exist in that application. "
        "Use the form modifier+modifier+key, e.g. ctrl+shift+s, alt+f4, f5. "
        "Give each one a short snake_case id and a label of at most three words.\n"
        'Answer as JSON: {"shortcuts":[{"id":"save_as","label":"Save As",'
        '"combo":"ctrl+shift+s"}]}'
    )


def _ask(segment: str, model: str, host: str, timeout: int) -> dict | None:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt_for(segment),
            "format": "json",
            "stream": False,
            # Guessing is bad enough without sampling noise on top.
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            answer = json.load(response)
    except urllib.error.URLError as error:
        log.error("no local model at %s (%s); cannot guess %s", host, error, segment)
        return None
    except TimeoutError:
        log.error("%s did not answer about %s within %ds", model, segment, timeout)
        return None
    except Exception:
        log.exception("asking %s for %s failed", model, segment)
        return None
    try:
        return json.loads(answer.get("response") or "")
    except json.JSONDecodeError:
        log.error("%s did not answer with JSON for %s", model, segment)
        return None


def _clean(raw: dict) -> list[dict]:
    """Keep the entries that are shaped right and whose combo the encoder accepts."""
    kept: list[dict] = []
    seen: set[str] = set()
    for entry in (raw.get("shortcuts") or [])[: MAX_SHORTCUTS * 2]:
        if not isinstance(entry, dict):
            continue
        identifier, label, combo = entry.get("id"), entry.get("label"), entry.get("combo")
        if not (isinstance(identifier, str) and isinstance(label, str) and isinstance(combo, str)):
            continue
        combo = combo.strip().lower()
        try:
            keys.encode(combo)
        except ValueError as error:
            log.info("dropping unusable guessed combo %r: %s", combo, error)
            continue
        if combo in seen:
            continue
        seen.add(combo)
        kept.append({"id": identifier.strip(), "label": label.strip(), "combo": combo})
        if len(kept) >= MAX_SHORTCUTS:
            break
    return kept


def build(
    segment: str,
    model: str | None = None,
    host: str | None = None,
    timeout: int = 300,
) -> list[Shortcut]:
    """Ask the local model about ``segment``, cache what survives validation, and return it."""
    model = model or os.environ.get("OPENDECK_GUESS_MODEL") or DEFAULT_MODEL
    host = host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST
    if not host.startswith("http"):
        host = "http://" + host

    raw = _ask(segment, model, host, timeout)
    if raw is None:
        return []
    entries = _clean(raw)
    if not entries:
        log.error("nothing usable came back for %s", segment)
        return []

    data = {"app": segment, "source": f"ollama:{model}", "shortcuts": entries}
    path = cache_file(segment)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        log.exception("could not cache guessed catalogue %s", path)
    return _records(segment, data)
