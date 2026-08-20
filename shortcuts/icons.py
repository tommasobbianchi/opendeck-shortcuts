"""Icon resolution for the OpenDeck picker: app art, then cache, then generated.

Three sources, in order, and never guessing:

1. App art -- ``Shortcut.icon``, the artwork the application itself ships.
   Free, exact, offline.
2. Cache -- ``~/.cache/opendeck-shortcuts/icons/<key>.png``, overridable by
   ``$OPENDECK_ICON_CACHE``. Anything generated once is never generated twice.
3. Generated -- only when explicitly asked for; it costs money and needs the
   network, so it is never implicit.

Pillow is the one optional dependency, imported lazily so importing this module
(and the rest of the package) never fails when it is absent.
"""

import base64
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib import request

log = logging.getLogger(__name__)

SIZE = 96

_RASTER_EXT = {".png", ".jpg", ".jpeg", ".webp"}

_INFSH = Path.home() / ".local" / "bin" / "infsh"
_MODEL = "google/gemini-2-5-flash-image"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class IconResult:
    data_uri: str | None
    origin: str  # "app" | "cache" | "generated" | "none"


def cache_key(shortcut) -> str:
    """sha256 of ``<app>\0<id>``, first 16 hex chars."""
    return hashlib.sha256(f"{shortcut.app}\0{shortcut.id}".encode("utf-8")).hexdigest()[:16]


def cache_dir() -> Path:
    override = os.environ.get("OPENDECK_ICON_CACHE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "opendeck-shortcuts" / "icons"


def _rasterise_svg(path: Path, size: int) -> bytes | None:
    convert = shutil.which("convert")
    if convert is None:
        log.error("ImageMagick `convert` is not installed; cannot rasterise %s", path)
        return None
    try:
        proc = subprocess.run(
            [convert, "-background", "none", "-density", "300",
             "-resize", f"{size}x{size}", str(path), "png:-"],
            capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        log.exception("convert failed on %s", path)
        return None
    if proc.returncode != 0:
        log.error("convert exited %d on %s", proc.returncode, path)
        return None
    return proc.stdout


def _rasterise_pillow(path: Path, size: int) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        log.error("Pillow is required to rasterise images; install it with `pip install Pillow`")
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            resample = getattr(Image, "Resampling", Image).LANCZOS
            im = im.resize((size, size), resample)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        log.exception("could not rasterise %s", path)
        return None


def rasterise(path: str | Path, size: int = SIZE) -> bytes | None:
    """Return ``path`` as ``size``x``size`` PNG bytes, or None when unreadable."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".svg":
        return _rasterise_svg(p, size)
    if suffix in _RASTER_EXT:
        return _rasterise_pillow(p, size)
    return None


def to_data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def prompt_for(shortcut) -> str:
    return (
        f'Create a flat, minimalist user-interface icon for the action "{shortcut.label}" '
        f"in the application {shortcut.app}. One centred glyph representing the action, "
        "drawn with thick, even strokes in light grey on a solid very dark background. "
        "No text, no letters, no numbers, no border. "
        "Do not draw the application's logo."
    )


def _download(url: str, timeout: int) -> bytes | None:
    req = request.Request(url, headers={"User-Agent": _UA})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        log.exception("could not download generated image")
        return None


def _cache_write(shortcut, png: bytes) -> None:
    path = cache_dir() / f"{cache_key(shortcut)}.png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
    except OSError:
        log.exception("could not write icon cache %s", path)


def generate(shortcut, timeout: int = 300) -> bytes | None:
    """Generate a 96x96 PNG via the local ``infsh`` binary, cached, or None."""
    if not _INFSH.is_file():
        log.error("inferencesh binary not found at %s", _INFSH)
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "result.json"
            proc = subprocess.run(
                [str(_INFSH), "app", "run", _MODEL, "--no-input", "-j",
                 "-o", str(json_path), "--input", json.dumps({"prompt": prompt_for(shortcut)})],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                log.error("infsh exited %d: %s", proc.returncode, proc.stderr[:200])
                return None
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if data.get("status_text") != "completed":
                log.error("infsh status %r", data.get("status_text"))
                return None
            images = (data.get("output") or {}).get("images") or []
            if not images:
                log.error("no image URL in infsh output")
                return None
            raw = _download(images[0], timeout)
            if raw is None:
                return None
            img_path = Path(tmp) / "gen.png"
            img_path.write_bytes(raw)
            png = rasterise(img_path)
            if png is None:
                return None
            _cache_write(shortcut, png)
            return png
    except Exception:
        log.exception("generation failed for %s", shortcut.id)
        return None


def resolve(shortcut, generate_missing: bool = False) -> IconResult:
    if shortcut.icon:
        png = rasterise(shortcut.icon)
        if png is not None:
            return IconResult(to_data_uri(png), "app")
    cache_file = cache_dir() / f"{cache_key(shortcut)}.png"
    if cache_file.is_file():
        try:
            return IconResult(to_data_uri(cache_file.read_bytes()), "cache")
        except OSError:
            log.exception("could not read cached icon %s", cache_file)
    if generate_missing:
        png = generate(shortcut)
        if png is not None:
            return IconResult(to_data_uri(png), "generated")
    return IconResult(None, "none")


def resolve_many(shortcuts, generate_missing: bool = False, limit: int | None = None) -> dict[str, IconResult]:
    selected = shortcuts if limit is None else shortcuts[:limit]
    return {sc.id: resolve(sc, generate_missing=generate_missing) for sc in selected}
