#!/usr/bin/env python3
"""Fetch an application's own icons and render them into the app-art tier.

Screenshot crops are a stand-in, not the app's art: they carry the resampling
blur of whatever zoom the toolbar happened to be at, plus whatever sat next to
the icon in the frame.  Where an app publishes its icon set — Onshape as an SVG
sprite, GTK apps as an icon theme, OrcaSlicer as SVGs in its source tree — we
take the real thing and render it ourselves at the deck's own resolution.

    vendor-icons.py onshape [--theme dark] [--size 96] [--sheet PATH]

Writes ~/.local/share/opendeck-shortcuts/app-art/<app>/<action>.png, which
shortcuts/icons.py already prefers over cache, store and generated glyphs.
The art stays local: store.py refuses to publish the app tier.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

import gi

gi.require_version("Rsvg", "2.0")
gi.require_foreign("cairo")  # librsvg draws onto a pycairo Context
from gi.repository import Rsvg  # noqa: E402

import cairo  # noqa: E402

ONSHAPE = "https://cad.onshape.com"
ART = Path(
    os.environ.get(
        "OPENDECK_APP_ART",
        Path.home() / ".local/share/opendeck-shortcuts/app-art",
    )
)

# action name (the app-art filename) -> the id Onshape gives that icon in its sprite
ONSHAPE_ICONS = {
    # part studio
    "sketch": "svg-icon-new-sketch-button",
    "extrude": "svg-icon-extrude-button",
    "revolve": "svg-icon-revolve-button",
    "sweep": "svg-icon-sweep-button",
    "loft": "svg-icon-loft-button",
    "fillet": "svg-icon-fillet-button",
    "chamfer": "svg-icon-chamfer-button",
    "shell": "svg-icon-shell-button",
    "hole": "svg-icon-hole-button",
    "thread": "svg-icon-external-thread-button",
    "draft": "svg-icon-draft-button",
    "rib": "svg-icon-rib-button",
    "boolean": "svg-icon-boolean-bodies-button",
    "mirror": "svg-icon-mirror-button",
    "linear_pattern": "svg-icon-linear-pattern-button",
    "circular_pattern": "svg-icon-circular-pattern-button",
    "curve_pattern": "svg-icon-curve-pattern-button",
    "transform": "svg-icon-transform-button",
    "split": "svg-icon-split-part-button",
    "thicken": "svg-icon-thicken-button",
    "plane": "svg-icon-default-plane-button",
    "measure": "svg-icon-measure-button",
    "mate_connectors": "svg-icon-mate-connector-button",
    "isolate": "svg-icon-isolate-button",
    "derived": "svg-icon-import-derived-button",
    "hide_sketches": "svg-icon-eye_closed",
    "exit": "svg-icon-cancel-button",
    "named_view": "svg-icon-named-view-button",
    # sketch entities
    "line": "svg-icon-sketch-line-segment-button",
    "circle": "svg-icon-sketch-circle-button",
    "three_point_circle": "svg-icon-sketch-perimeter-circle-button",
    "corner_rectangle": "svg-icon-sketch-rectangle-button",
    "center_rectangle": "svg-icon-sketch-center-rectangle-button",
    "aligned_rectangle": "svg-icon-sketch-aligned-rectangle-button",
    "arc": "svg-icon-sketch-arc-button",
    "tangent_arc": "svg-icon-sketch-tangent-arc-button",
    "center_point_arc": "svg-icon-sketch-center-arc-button",
    "ellipse": "svg-icon-sketch-ellipse-button",
    "elliptical_arc": "svg-icon-elliptical-arc-button",
    "conic": "svg-icon-sketch-conic-button",
    "spline": "svg-icon-sketch-spline-button",
    "spline_control_point": "svg-icon-fit-spline-button",
    "bezier": "svg-icon-sketch-bezier-button",
    "polygon": "svg-icon-sketch-inscribed-polygon-button",
    "inscribed_polygon": "svg-icon-sketch-inscribed-polygon-button",
    "circumscribed_polygon": "svg-icon-sketch-circumscribed-polygon-button",
    "slot": "svg-icon-sketch-slot-button",
    "sketch_point": "svg-icon-sketch-point-button",
    "text": "svg-icon-sketch-text-rectangle-button",
    "insert_image": "svg-icon-sketch-image-rectangle-button",
    "insert_dxf": "svg-icon-150715_Sketch_Icons_30_InsertDXFDWG",
    "construction": "svg-icon-sketch-construction-button",
    # sketch edits
    "dimension": "svg-icon-sketch-dimension-button",
    "trim": "svg-icon-sketch-trim-button",
    "extend": "svg-icon-sketch-extend-button",
    "offset": "svg-icon-sketch-offset-button",
    "use": "svg-icon-sketch-use-button",
    "sketch_fillet": "svg-icon-sketch-fillet-button",
    "sketch_chamfer": "svg-icon-sketch-chamfer-button",
    "mirror_sketch": "svg-icon-sketch-mirror-button",
    "pattern": "svg-icon-sketch-lpattern-button",
    "sketch_transform": "svg-icon-sketch-transform-button",
    "intersection": "svg-icon-sketch-intersection-button",
    # constraints
    "coincident": "svg-icon-sketch-coincident-button",
    "concentric": "svg-icon-sketch-concentric-button",
    "tangent": "svg-icon-sketch-tangent-button",
    "parallel": "svg-icon-sketch-parallel-button",
    "perpendicular": "svg-icon-sketch-perpendicular-button",
    "equal": "svg-icon-sketch-equal-button",
    "horizontal": "svg-icon-sketch-horizontal-button",
    "vertical": "svg-icon-sketch-vertical-button",
    "midpoint": "svg-icon-sketch-midpoint-button",
    "midpoint_line": "svg-icon-sketch-midpoint-line-button",
    "symmetric": "svg-icon-sketch-symmetric-button",
}


# Nautilus's shortcuts are GNOME actions, and GNOME draws them with the Adwaita symbolic set --
# the same icon the menu item beside the shortcut shows.  Symbolic icons are single-colour by
# design: GTK recolours them per theme, so tinting one light is not a liberty, it is the format.
GTK_ICONS = {
    "open": "document-open-symbolic",
    "open_in_new_tab": "tab-new-symbolic",
    "open_in_new_window": "window-new-symbolic",
    "open_item_location_search_and_recent_only": "folder-symbolic",
    "open_with_default_app": "application-x-executable-symbolic",
    "open_current_directory_in_console": "utilities-terminal-symbolic",
    "open_context_menu": "view-more-symbolic",
    "create_folder": "folder-new-symbolic",
    "cut": "edit-cut-symbolic",
    "copy": "edit-copy-symbolic",
    "paste": "edit-paste-symbolic",
    "rename": "document-edit-symbolic",
    "move_to_trash": "user-trash-symbolic",
    "delete_permanently": "edit-delete-symbolic",
    "create_link_to_copied_item": "insert-link-symbolic",
    "select_all": "edit-select-all-symbolic",
    "search": "edit-find-symbolic",
    "undo": "edit-undo-symbolic",
    "redo": "edit-redo-symbolic",
    "properties": "document-properties-symbolic",
    "zoom_in": "zoom-in-symbolic",
    "zoom_out": "zoom-out-symbolic",
    "reload": "view-refresh-symbolic",
}

# OrcaSlicer keeps its icons as SVGs beside the source, most with a "_dark" twin for the dark
# theme.  Only actions Orca actually draws an icon for appear here: its File menu is half
# text-only, and inventing art for the rest would defeat the point of using the app's own.
ORCA_ICONS = {
    "open_project": "menu_open",
    "save_project": "menu_save",
    "save_project_as": "menu_save",
    "import_geometry_data_from_stl_step_3mf_obj_amf_files": "menu_import",
    "export_plate_sliced_file": "menu_export_sliced_file",
    "cut": "menu_cut",
    "copy_to_clipboard": "menu_copy",
    "paste_from_clipboard": "menu_paste",
    "delete_selected": "menu_delete",
    "delete_all": "menu_remove",
    "undo": "menu_undo",
    "redo": "menu_redo",
    "arrange_all_objects": "toolbar_arrange",
    "arrange_objects_on_selected_plates": "toolbar_arrange",
    "zoom_in": "canvas_zoom_in",
    "zoom_out": "canvas_zoom_out",
    "gizmo_move": "toolbar_move",
    "gizmo_rotate": "toolbar_rotate",
    "gizmo_scale": "toolbar_scale",
    "gizmo_place_face_on_bed": "toolbar_flatten",
    "gizmo_cut": "toolbar_cut",
    "gizmo_mesh_boolean": "toolbar_meshboolean",
    "gizmo_measure": "toolbar_measure",
    "gizmo_assemble": "toolbar_assemble",
    "gizmo_brim_ears": "toolbar_brimears",
    "gizmo_fdm_paint_on_fuzzy_skin": "toolbar_fuzzy_skin_paint",
    "gizmo_text_emboss_engrave": "toolbar_text",
    "collapse_expand_the_sidebar": "collapse",
}

ORCA_TREES = (
    "~/projects/orca/orcaslicer-pr/belt-2026-08-local/resources/images",
    "~/projects/orca/orcacad-native/src/resources/images",
)


# Gmail's interface is drawn with Google's Material Symbols, which Google serves as SVG.
# Single-colour by design, like GTK's symbolic set, so the deck tints them the same way.
MATERIAL = "https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsoutlined"
MATERIAL_ICONS = {
    "gmail": {
        "compose": "edit",
        "send": "send",
        "search": "search",
        "reply": "reply",
        "reply_all": "reply_all",
        "forward": "forward",
        "archive": "archive",
        "delete": "delete",
        "star": "star",
        "select": "check_box",
        "mute": "notifications_off",
        "spam": "report",
        "older": "navigate_next",
        "newer": "navigate_before",
        "back_to_list": "arrow_back",
        "label": "label",
        "snooze": "schedule",
        "mark_unread": "mark_email_unread",
    },
    # Chrome's own icons are compiled into the browser, but Chrome is drawn in this very
    # language, so the family holds. Directional pairs must be a pair: next is the mirror of
    # previous, and pointing them the same way -- which is what the drawn glyphs did -- is the
    # single worst thing an icon set can do.
    # The identity is `google-chrome` while the catalogue ids are `chrome.*`; app art keeps
    # whatever of the id the app name does not prefix, so these keys carry it.
    "google-chrome": {
        "chrome.new_tab": "add_box",
        "chrome.close_tab": "tab_close",
        "chrome.reopen_closed_tab": "restore_page",
        "chrome.next_tab": "chevron_right",
        "chrome.previous_tab": "chevron_left",
        "chrome.address_bar": "web",
        "chrome.find": "find_in_page",
        "chrome.reload": "refresh",
        "chrome.devtools": "code",
        "chrome.incognito": "visibility_off",
        "chrome.bookmark": "star",
        "chrome.history": "history",
        "chrome.downloads": "download",
    },
    "youtube": {
        "play_pause": "play_pause",
        "mute": "volume_off",
        "fullscreen": "fullscreen",
        "captions": "closed_caption",
        "back_10": "replay_10",
        "forward_10": "forward_10",
        "next_video": "skip_next",
        "previous_video": "skip_previous",
        # A pair must look like a pair, and these two shortcuts are literally ">" and "<".
        "faster": "keyboard_double_arrow_right",
        "slower": "keyboard_double_arrow_left",
        "next_frame": "arrow_forward_ios",
        "previous_frame": "arrow_back_ios",
        "search": "search",
        "restart": "replay",
        "next_chapter": "playlist_play",
    },
    "kitty": {
        "copy_to_clipboard": "content_copy",
        "paste_from_clipboard": "content_paste",
        "paste_from_clipboard.ctrl+v": "content_paste_go",
        "new_os_window": "open_in_new",
        "next_layout": "view_quilt",
        "change_font_size": "text_increase",
        "change_font_size.ctrl+shift+-": "text_decrease",
        "change_font_size.ctrl+shift+backspace": "format_size",
        "copy_and_clear_or_interrupt": "stop_circle",
        "kitten": "link",
        "kitten.ctrl+shift+p": "text_select_start",
        "kitten.ctrl+shift+o": "folder_open",
    },
    "claude": {
        "clear_screen": "clear_all",
        "permission_mode": "admin_panel_settings",
        "expand_output": "unfold_more",
    },
    "discord": {
        "toggle_mute": "volume_off",
        "toggle_video": "videocam",
        "toggle_voice": "record_voice_over",
        "toggle_typing": "keyboard",
        "toggle_screen_share": "screen_share",
        "toggle_reaction": "add_reaction",
        "toggle_voice_chat": "headset_mic",
        "toggle_voice_mute": "mic_off",
        "toggle_voice_typing": "keyboard_voice",
    },
    "telegram-desktop_telegram-desktop": {
        "toggle_sidebar": "menu_open",
        "toggle_fullscreen": "fullscreen",
        "toggle_dark_mode": "dark_mode",
        "copy_link": "link",
        "paste": "content_paste",
        "delete_message": "delete",
        "reply": "reply",
        "search": "search",
        "mute_group": "notifications_off",
        "mark_read": "mark_chat_read",
    },
    "WhatsApp Desktop": {
        "new_chat": "add_comment",
        "send_message": "send",
        "copy_text": "content_copy",
        "paste_text": "content_paste",
        "delete_message": "delete",
        "toggle_mute": "volume_off",
        "toggle_notifications": "notifications",
        "refresh": "refresh",
        "minimize": "minimize",
        "close": "close",
    },
    # Only what OrcaSlicer ships no art of; everything else on that page is Orca's own SVG.
    "orca": {
        "new_project": "note_add",
        "import_geometry_data_from_stl_step_3mf_obj_amf_files": "file_open",
        "export_plate_sliced_file": "download",
        "slice_plate": "layers",
        "print_plate": "print",
        "preferences": "settings",
        "show_hide_3dconnexion_devices_settings_dialog": "mouse",
        "switch_table_page": "swap_horiz",
        "delete_selected": "delete",
    },
    # Onshape draws these two with the view cube, not with a toolbar icon.
    "onshape": {
        "isometric": "deployed_code",
        "front_view": "crop_square",
    },
}



def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def onshape_sprite_url() -> str:
    """The sprite is versioned, so read the path out of the page that loads it."""
    root = fetch(ONSHAPE + "/")
    m = re.search(r'icons-path="([^"]+)"', root)
    if not m:
        sys.exit("no icons-path in the Onshape landing page — the markup changed")
    return ONSHAPE + m.group(1)


def onshape_palette(theme: str) -> dict[str, str]:
    """Resolve Onshape's design tokens down to the concrete colours of one theme.

    The token file layers :root over [data-os-theme=light] over
    [data-os-theme=dark], each block redefining --os-* in terms of other --os-*.
    """
    css = fetch(ONSHAPE + "/css/onshape-design-tokens.v1.0.53.min.css")
    raw: dict[str, str] = {}
    for head, body in re.findall(r"([^{}]*)\{([^{}]*)\}", css):
        selector = head.split("@")[-1].strip()
        if "data-os-theme" not in selector and ":root" not in selector:
            continue
        if theme == "dark" and "=light" in selector:
            continue  # dark inherits the shared block, not the light one
        if theme != "dark" and "=dark" in selector:
            continue
        for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+)", body):
            raw[name] = value.strip()

    def resolve(value: str, depth: int = 0) -> str:
        if depth > 12:
            return value
        m = re.fullmatch(r"var\((--[a-z0-9-]+)(?:,\s*(.*))?\)", value.strip())
        if not m:
            return value
        name, fallback = m.group(1), m.group(2)
        if name in raw:
            return resolve(raw[name], depth + 1)
        return resolve(fallback, depth + 1) if fallback else "none"

    return {k: resolve(v) for k, v in raw.items()}


def flatten_vars(svg: str, palette: dict[str, str]) -> str:
    """librsvg does not do CSS custom properties, so bake the colours in."""

    def sub(m: re.Match[str]) -> str:
        name, fallback = m.group(1), (m.group(2) or "").strip()
        return palette.get(name) or fallback or "none"

    return re.sub(r"var\((--[a-z0-9-]+)(?:,\s*([^)]*))?\)", sub, svg)


def sprite_body(sprite: str) -> str:
    """The sprite's contents, without its own <svg> wrapper."""
    return sprite[sprite.index(">", sprite.index("<svg")) + 1 : sprite.rindex("</svg>")]


def symbol_viewbox(sprite: str, symbol_id: str) -> str | None:
    m = re.search(r'<symbol[^>]*id="%s"[^>]*>' % re.escape(symbol_id), sprite)
    if not m:
        return None
    vb = re.search(r'viewBox="([^"]+)"', m.group(0))
    return vb.group(1) if vb else "0 0 20 20"


def render(sprite: str, body: str, symbol_id: str, size: int) -> bytes | None:
    """Render one sprite symbol onto an opaque black square, deck-sized.

    A <symbol> never paints where it is defined — it paints through <use> — so
    rendering it needs a document that instantiates it, not a layer lookup.
    """
    viewbox = symbol_viewbox(sprite, symbol_id)
    if viewbox is None:
        return None
    pad = 0.08  # the app draws its icons with breathing room; keep it
    x0, y0, w, h = (float(v) for v in viewbox.replace(",", " ").split())
    grow = pad / (1 - 2 * pad)
    doc = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{size}" height="{size}" '
        f'viewBox="{x0 - w * grow} {y0 - h * grow} {w * (1 + 2 * grow)} {h * (1 + 2 * grow)}">'
        f"{body}<use xlink:href=\"#{symbol_id}\"/></svg>"
    ).encode()
    handle = Rsvg.Handle.new_from_data(doc)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, size, size)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    rect = Rsvg.Rectangle()
    rect.x = rect.y = 0
    rect.width = rect.height = size
    if not handle.render_document(ctx, rect):
        return None
    surface.flush()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def _tint(png: bytes, colour: tuple[int, int, int]) -> bytes:
    """Repaint a rendered glyph in one colour, keeping its coverage.

    Symbolic icons carry shape, not palette; the toolkit picks the colour from the theme.
    On a black key that colour is a light grey, the same as GNOME's own dark styling.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGBA")
    flat = Image.new("RGBA", img.size, colour + (0,))
    flat.putalpha(img.getchannel("A"))
    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(flat, (0, 0), flat)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def render_file(
    path: Path,
    size: int,
    tint: tuple[int, int, int] | None = None,
    auto_light: bool = False,
) -> bytes | None:
    """Render a standalone SVG onto a deck-sized black square.

    ``auto_light`` catches art drawn for a light background: an icon that comes out
    nearly black has not failed to render, it has rendered in ink the key cannot show,
    so it is repainted in the light the app itself would use on a dark theme.
    """
    handle = Rsvg.Handle.new_from_data(path.read_bytes())
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    pad = size * 0.08
    rect = Rsvg.Rectangle()
    rect.x = rect.y = pad
    rect.width = rect.height = size - 2 * pad
    if not handle.render_document(ctx, rect):
        return None
    surface.flush()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    png = buf.getvalue()
    from PIL import Image, ImageStat

    img = Image.open(io.BytesIO(png)).convert("RGBA")
    # Some apps ship a placeholder where a menu item has no art -- OrcaSlicer's menu_delete.svg
    # is a 1%-opacity grey square.  A key painted with that is a black key, so say so instead.
    if img.getchannel("A").getextrema()[1] < 8:
        return None
    if tint:
        return _tint(png, tint)
    out = Image.new("RGB", img.size, (0, 0, 0))
    out.paste(img, (0, 0), img)
    if auto_light and ImageStat.Stat(out.convert("L")).mean[0] < 8:
        return _tint(png, (0xDF, 0xDF, 0xDF))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def safe(part: str) -> str:
    """The same folder name `icons.app_art_path` looks under, so the art is found."""
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in part)[:64]


def write_all(app: str, jobs: dict[str, Path], size: int, tint=None, sheet=None,
              auto_light: bool = False) -> int:
    out_dir = ART / safe(app)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, failed = [], []
    for action, source in sorted(jobs.items()):
        png = render_file(source, size, tint, auto_light)
        if png is None:
            failed.append(action)
            continue
        path = out_dir / f"{safe(action)}.png"
        path.write_bytes(png)
        written.append(path)
    print(f"wrote   {len(written)} icons to {out_dir}")
    for action in failed:
        print(f"EMPTY   {action}: the app ships no art for it")
    if sheet:
        contact_sheet(written, Path(sheet), size)
        print(f"sheet   {sheet}")
    return 1 if failed else 0


def contact_sheet(paths: list[Path], out: Path, size: int) -> None:
    from PIL import Image, ImageDraw

    cols = 8
    cell = size + 14
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 14)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        sheet.paste(Image.open(p).convert("RGB"), (x + 7, y + 7))
        draw.text((x + 4, y + size + 8), p.stem[:17], fill="black")
    sheet.save(out)


def cmd_onshape(args: argparse.Namespace) -> int:
    url = onshape_sprite_url()
    print(f"sprite  {url}")
    sprite = fetch(url)
    palette = onshape_palette(args.theme)
    sprite = flatten_vars(sprite, palette)
    body = sprite_body(sprite)

    out_dir = ART / "onshape"
    out_dir.mkdir(parents=True, exist_ok=True)
    written, missing = [], []
    for action, symbol in sorted(ONSHAPE_ICONS.items()):
        png = render(sprite, body, symbol, args.size)
        if png is None:
            missing.append((action, symbol))
            continue
        path = out_dir / f"{action}.png"
        path.write_bytes(png)
        written.append(path)

    print(f"wrote   {len(written)} icons to {out_dir}")
    for action, symbol in missing:
        print(f"MISSING {action}: no {symbol} in the sprite")
    if args.sheet:
        contact_sheet(written, Path(args.sheet), args.size)
        print(f"sheet   {args.sheet}")
    return 1 if missing else 0


def cmd_gtk(args: argparse.Namespace) -> int:
    theme = Path("/usr/share/icons/Adwaita")
    jobs, missing = {}, []
    for action, name in GTK_ICONS.items():
        found = next(theme.rglob(f"{name}.svg"), None)
        if found is None:
            missing.append(f"{action}: no {name} in the Adwaita theme")
            continue
        jobs[action] = found
    rc = write_all(args.app, jobs, args.size, tint=(0xDF, 0xDF, 0xDF), sheet=args.sheet)
    for line in missing:
        print("MISSING", line)
    return rc or (1 if missing else 0)


def cmd_orca(args: argparse.Namespace) -> int:
    tree = None
    for candidate in ([args.tree] if args.tree else list(ORCA_TREES)):
        path = Path(candidate).expanduser()
        if path.is_dir():
            tree = path
            break
    if tree is None:
        sys.exit("no OrcaSlicer resources/images tree found; pass --tree")
    print(f"tree    {tree}")

    jobs, missing = {}, []
    for action, stem in ORCA_ICONS.items():
        # Orca ships a "_dark" twin for the dark theme; on a black key that is the right one.
        dark, plain = tree / f"{stem}_dark.svg", tree / f"{stem}.svg"
        source = dark if dark.exists() else plain
        if not source.exists():
            missing.append(f"{action}: no {stem}.svg under {tree}")
            continue
        jobs[action] = source
    rc = write_all("orca", jobs, args.size, sheet=args.sheet, auto_light=True)
    for line in missing:
        print("MISSING", line)
    return rc or (1 if missing else 0)


def cmd_material(args: argparse.Namespace) -> int:
    icons = MATERIAL_ICONS.get(args.app)
    if icons is None:
        sys.exit(f"no Material Symbols mapping for {args.app!r}: "
                 f"known apps are {', '.join(sorted(MATERIAL_ICONS))}")
    tmp = Path(tempfile.mkdtemp(prefix="material-"))
    jobs, missing = {}, []
    for action, name in icons.items():
        try:
            svg = fetch(f"{MATERIAL}/{name}/default/48px.svg")
        except Exception as exc:  # a name Google does not serve
            missing.append(f"{action}: {name} -- {exc}")
            continue
        path = tmp / f"{name}.svg"
        path.write_text(svg)
        jobs[action] = path
    rc = write_all(args.app, jobs, args.size, tint=(0xDF, 0xDF, 0xDF), sheet=args.sheet)
    for line in missing:
        print("MISSING", line)
    return rc or (1 if missing else 0)



def cmd_audit(args: argparse.Namespace) -> int:
    """Say, per profile and per key, where the picture on that key came from.

    The question this whole tool answers -- "is the deck showing the app's own icon?" --
    is not answerable by looking at a key, so it is answerable here.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from shortcuts import icons as icon_lib
    from shortcuts import opendeck
    from shortcuts.providers import resolve as resolve_shortcuts

    device = args.device or next(iter(opendeck.devices()), None)
    if device is None:
        sys.exit("no device under ~/.config/opendeck/profiles")
    mapping = opendeck.applications()
    totals: dict[str, int] = {}
    for identity in sorted(mapping):
        profile = mapping[identity].get(device)
        if profile is None:
            continue
        try:
            data = opendeck.load_profile(device, profile)
        except Exception:
            continue
        by_tokens = {sc.tokens: sc for sc in resolve_shortcuts(identity.split("#", 1)[0])}
        counts: dict[str, int] = {}
        strays = []
        for key in data.get("keys") or []:
            if not key:
                continue
            sc = by_tokens.get((key.get("settings") or {}).get("down") or "")
            if sc is None:
                counts["not a shortcut"] = counts.get("not a shortcut", 0) + 1
                continue
            origin = icon_lib.resolve(sc).origin
            counts[origin] = counts.get(origin, 0) + 1
            totals[origin] = totals.get(origin, 0) + 1
            if args.verbose and origin != "app":
                strays.append(f"      {sc.id}: {origin}")
        summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"{identity:34s} {summary}")
        for line in strays:
            print(line)
    print("TOTAL " + "  ".join(f"{k}={v}" for k, v in sorted(totals.items())))
    return 0



def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="app", required=True)
    o = sub.add_parser("onshape", help="Onshape's own SVG icon sprite")
    o.add_argument("--theme", default="dark", choices=["dark", "light"])
    o.add_argument("--size", type=int, default=96)
    o.add_argument("--sheet", help="also write a labelled contact sheet here")
    o.set_defaults(func=cmd_onshape)

    g = sub.add_parser("gtk", help="the Adwaita symbolic icons a GTK app shows in its menus")
    g.add_argument("--app", default="org.gnome.Nautilus", help="app-art folder to fill")
    g.add_argument("--size", type=int, default=96)
    g.add_argument("--sheet", help="also write a labelled contact sheet here")
    g.set_defaults(func=cmd_gtk)

    r = sub.add_parser("orca", help="OrcaSlicer's own SVGs, from its source tree")
    r.add_argument("--tree", help="path to resources/images (default: the first known checkout)")
    r.add_argument("--size", type=int, default=96)
    r.add_argument("--sheet", help="also write a labelled contact sheet here")
    r.set_defaults(func=cmd_orca)

    m = sub.add_parser("material", help="Google's Material Symbols, as Gmail draws them")
    m.add_argument("--app", default="gmail", help="app-art folder to fill")
    m.add_argument("--size", type=int, default=96)
    m.add_argument("--sheet", help="also write a labelled contact sheet here")
    m.set_defaults(func=cmd_material)

    a = sub.add_parser("audit", help="where each key's picture actually comes from")
    a.add_argument("--device", help="device id (default: the only one)")
    a.add_argument("-v", "--verbose", action="store_true", help="name every key that is not app art")
    a.set_defaults(func=cmd_audit)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
