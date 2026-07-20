#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import struct
import time
import zlib
from pathlib import Path

TYPE_OBJECT = 0
TYPE_STRING = 1
TYPE_INT = 2
TYPE_UINT64 = 7
TYPE_END = 8


def read_cstr(data: bytes, pos: int) -> tuple[str, int]:
    end = data.index(0, pos)
    return data[pos:end].decode("utf-8", errors="replace"), end + 1


def parse_object(data: bytes, pos: int) -> tuple[list[tuple[int, str, object]], int]:
    items: list[tuple[int, str, object]] = []
    while pos < len(data):
        typ = data[pos]
        pos += 1
        if typ == TYPE_END:
            return items, pos
        key, pos = read_cstr(data, pos)
        if typ == TYPE_OBJECT:
            val, pos = parse_object(data, pos)
        elif typ == TYPE_STRING:
            val, pos = read_cstr(data, pos)
        elif typ == TYPE_INT:
            val = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        elif typ == TYPE_UINT64:
            val = struct.unpack_from("<Q", data, pos)[0]
            pos += 8
        else:
            raise ValueError(f"Unsupported binary VDF type {typ} at offset {pos - 1}")
        items.append((typ, key, val))
    raise ValueError("Unexpected EOF while parsing binary VDF")


def emit_cstr(text: str) -> bytes:
    return text.encode("utf-8") + b"\x00"


def emit_object(items: list[tuple[int, str, object]]) -> bytes:
    out = bytearray()
    for typ, key, val in items:
        out.append(typ)
        out.extend(emit_cstr(key))
        if typ == TYPE_OBJECT:
            out.extend(emit_object(val))  # type: ignore[arg-type]
        elif typ == TYPE_STRING:
            out.extend(emit_cstr(str(val)))
        elif typ == TYPE_INT:
            out.extend(struct.pack("<I", int(val) & 0xFFFFFFFF))
        elif typ == TYPE_UINT64:
            out.extend(struct.pack("<Q", int(val) & 0xFFFFFFFFFFFFFFFF))
        else:
            raise ValueError(f"Unsupported binary VDF type {typ}")
    out.append(TYPE_END)
    return bytes(out)


def find_steam_config() -> Path:
    roots = [
        Path.home() / ".local/share/Steam/userdata",
        Path.home() / ".steam/steam/userdata",
    ]
    configs: list[Path] = []
    for root in roots:
        if root.exists():
            configs.extend(path for path in root.glob("*/config") if path.is_dir())
    if not configs:
        raise SystemExit("No Steam userdata config directory found. Pass --shortcuts explicitly.")

    def score(path: Path) -> float:
        existing = [p for p in [path / "shortcuts.vdf", path / "localconfig.vdf"] if p.exists()]
        if existing:
            return max(p.stat().st_mtime for p in existing)
        return path.stat().st_mtime

    return max(configs, key=score)


def load_shortcuts(path: Path) -> list[tuple[int, str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        return [(TYPE_OBJECT, "shortcuts", [])]
    data = path.read_bytes()
    root, pos = parse_object(data, 0)
    if pos != len(data):
        raise ValueError(f"Trailing data in {path}: parsed {pos}, size {len(data)}")
    if len(root) != 1 or root[0][0] != TYPE_OBJECT or root[0][1] != "shortcuts":
        raise ValueError("Expected top-level shortcuts object")
    return root


def get_field(entry: list[tuple[int, str, object]], name: str) -> object | None:
    for _, key, val in entry:
        if key == name:
            return val
    return None


def compute_appid(app_name: str, exe_field: str, used: set[int]) -> int:
    seed = exe_field + app_name
    for counter in range(1000):
        suffix = "" if counter == 0 else f":{counter}"
        appid = (zlib.crc32((seed + suffix).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
        if appid not in used:
            return appid
    raise RuntimeError("Unable to allocate unique shortcut appid")


def make_entry(appid: int, app_name: str, exe: str, start_dir: str, icon: str, launch_options: str):
    exe_field = f'"{exe}"'
    start_field = f'"{start_dir.rstrip("/")}/"'
    return [
        (TYPE_INT, "appid", appid),
        (TYPE_STRING, "AppName", app_name),
        (TYPE_STRING, "Exe", exe_field),
        (TYPE_STRING, "StartDir", start_field),
        (TYPE_STRING, "icon", icon),
        (TYPE_STRING, "ShortcutPath", ""),
        (TYPE_STRING, "LaunchOptions", launch_options),
        (TYPE_INT, "IsHidden", 0),
        (TYPE_INT, "AllowDesktopConfig", 1),
        (TYPE_INT, "AllowOverlay", 1),
        (TYPE_INT, "openvr", 0),
        (TYPE_INT, "Devkit", 0),
        (TYPE_STRING, "DevkitGameID", ""),
        (TYPE_INT, "DevkitOverrideAppID", 0),
        (TYPE_INT, "LastPlayTime", 0),
        (TYPE_STRING, "FlatpakAppID", ""),
        (TYPE_STRING, "sortas", ""),
        (TYPE_OBJECT, "tags", []),
    ]


def update_shortcuts(path: Path, app_name: str, exe: str, start_dir: str, icon: str, launch_options: str) -> tuple[int, Path | None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = load_shortcuts(path)
    entries = list(root[0][2])  # type: ignore[arg-type]
    exe_field = f'"{exe}"'
    used = {
        int(get_field(entry, "appid"))
        for typ, _, entry in entries
        if typ == TYPE_OBJECT and get_field(entry, "appid") is not None
    }

    kept = []
    reused_appid: int | None = None
    for typ, key, val in entries:
        if typ != TYPE_OBJECT:
            kept.append((typ, key, val))
            continue
        app = get_field(val, "AppName")  # type: ignore[arg-type]
        existing_exe = get_field(val, "Exe")  # type: ignore[arg-type]
        if app == app_name or existing_exe in {exe_field, exe}:
            reused_appid = int(get_field(val, "appid") or 0)  # type: ignore[arg-type]
            continue
        kept.append((typ, key, val))

    appid = reused_appid or compute_appid(app_name, exe_field, used)
    kept.append((TYPE_OBJECT, str(len(kept)), make_entry(appid, app_name, exe, start_dir, icon, launch_options)))
    renumbered = [(typ, str(i), val) for i, (typ, _, val) in enumerate(kept)]
    out = emit_object([(TYPE_OBJECT, "shortcuts", renumbered)])

    backup = None
    if path.exists():
        backup = path.with_suffix(path.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(out)
    os.replace(tmp, path)
    return appid, backup


def first_existing(art_dir: Path, names: list[str]) -> Path | None:
    for name in names:
        path = art_dir / name
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def install_art(appid: int, art_dir: Path, grid_dir: Path) -> list[Path]:
    grid_dir.mkdir(parents=True, exist_ok=True)
    mapping = [
        (["capsule.png", "grid.png", "horizontal.png"], f"{appid}.png"),
        (["poster.png", "cover.png", "vertical.png"], f"{appid}p.png"),
        (["library_hero.png", "hero.png", "banner.png"], f"{appid}_hero.png"),
        (["logo.png"], f"{appid}_logo.png"),
        (["icon.png"], f"{appid}_icon.png"),
    ]
    installed: list[Path] = []
    for sources, dest_name in mapping:
        source = first_existing(art_dir, sources)
        if source is None:
            continue
        dest = grid_dir / dest_name
        shutil.copy2(source, dest)
        installed.append(dest)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shortcuts", default="auto", help="shortcuts.vdf path, or auto")
    parser.add_argument("--grid-dir", default=None)
    parser.add_argument("--art-dir", default=None)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--start-dir", required=True)
    parser.add_argument("--icon", default="")
    parser.add_argument("--launch-options", default="")
    args = parser.parse_args()

    if args.shortcuts == "auto":
        config = find_steam_config()
        shortcuts = config / "shortcuts.vdf"
    else:
        shortcuts = Path(args.shortcuts).expanduser()
        config = shortcuts.parent

    grid_dir = Path(args.grid_dir).expanduser() if args.grid_dir else config / "grid"
    icon = args.icon
    if not icon and args.art_dir:
        icon_path = Path(args.art_dir).expanduser() / "icon.png"
        icon = str(icon_path) if icon_path.exists() else ""

    appid, backup = update_shortcuts(
        shortcuts,
        args.app_name,
        str(Path(args.exe).expanduser()),
        str(Path(args.start_dir).expanduser()),
        icon,
        args.launch_options,
    )
    print(f"appid={appid}")
    if backup:
        print(f"backup={backup}")
    else:
        print("backup=")
    print(f"shortcuts={shortcuts}")

    if args.art_dir:
        installed = install_art(appid, Path(args.art_dir).expanduser(), grid_dir)
        for path in installed:
            print(f"art={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
