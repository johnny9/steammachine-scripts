#!/usr/bin/env python3
"""Add one base Nintendo Switch game to Steam through Eden."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import struct
import time
import zlib
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - Python < 3.11
    raise SystemExit("Python 3.11 or newer is required for TOML config support") from exc


TYPE_OBJECT = 0
TYPE_STRING = 1
TYPE_INT = 2
TYPE_UINT64 = 7
TYPE_END = 8
ROM_SUFFIXES = {".xci", ".nsp"}
AUX_COMPONENT = re.compile(r"(^|[\s_.-])(updates?|dlc|mods?|patches)([\s_.-]|$)", re.IGNORECASE)
NONZERO_VERSION = re.compile(r"\[v(\d+)\]", re.IGNORECASE)


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def expand_path(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(str(value))).expanduser()


def require_file(value: str | os.PathLike[str], label: str) -> Path:
    path = expand_path(value).resolve(strict=True)
    if not path.is_file():
        fail(f"{label} is not a file: {path}")
    return path


def require_directory(value: str | os.PathLike[str], label: str) -> Path:
    path = expand_path(value).resolve(strict=True)
    if not path.is_dir():
        fail(f"{label} is not a directory: {path}")
    return path


def load_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    if not path.is_file():
        fail(f"Config path is not a file: {path}")
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"Cannot read config {path}: {exc}")
    if not isinstance(payload, dict):
        fail(f"Config must contain a TOML table: {path}")
    return payload


def option(cli_value: object, config: dict[str, object], key: str, default: object = None) -> object:
    if cli_value is not None:
        return cli_value
    return config.get(key, default)


def normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def clean_title(path: Path) -> str:
    title = re.sub(r"\[[^]]*\]", " ", path.stem)
    title = re.sub(r"\((usa|eur|europe|jpn|japan|world|en(?:,[a-z]{2})*)\)", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"[_\s]+", " ", title).strip(" ._-")
    return title or path.stem


def is_auxiliary(path: Path, rom_root: Path) -> bool:
    relative = path.relative_to(rom_root)
    if any(AUX_COMPONENT.search(component) for component in relative.parts):
        return True
    lowered = path.name.lower()
    if "[update" in lowered or "[dlc" in lowered or "title update" in lowered:
        return True
    version = NONZERO_VERSION.search(path.name)
    if path.suffix.lower() == ".nsp" and version and int(version.group(1)) != 0:
        return True
    return False


def candidate_score(query: str, path: Path) -> float:
    query_norm = normalized_title(query)
    title_norm = normalized_title(clean_title(path))
    if not query_norm or not title_norm:
        return 0.0
    ratio = difflib.SequenceMatcher(None, query_norm, title_norm).ratio()
    query_tokens = set(query_norm.split())
    title_tokens = set(title_norm.split())
    token_score = len(query_tokens & title_tokens) / max(1, len(query_tokens))
    substring = 1.0 if query_norm in title_norm or title_norm in query_norm else 0.0
    return max(ratio, token_score * 0.92, substring * 0.96)


def list_base_roms(rom_root: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in rom_root.rglob("*")
        if path.is_file() and path.suffix.lower() in ROM_SUFFIXES and not is_auxiliary(path, rom_root)
    )


def choose_rom(rom_root: Path, query: str | None, explicit_rom: str | None) -> Path:
    if explicit_rom:
        rom = require_file(explicit_rom, "ROM")
        if rom.suffix.lower() not in ROM_SUFFIXES:
            fail(f"ROM must be an .xci or .nsp file: {rom}")
        try:
            rom.relative_to(rom_root)
        except ValueError:
            fail(f"ROM is outside the configured ROM root {rom_root}: {rom}")
        if is_auxiliary(rom, rom_root):
            fail(f"Refusing an update, DLC, mod, or nonzero-version NSP as a base game: {rom}")
        return rom

    if not query:
        fail("Pass --game to search the ROM root or --rom for an exact base-game file")
    base_roms = list_base_roms(rom_root)
    ranked = sorted(((candidate_score(query, path), path) for path in base_roms), reverse=True)
    matches = [(score, path) for score, path in ranked if score >= 0.45]
    if not matches:
        available = "\n".join(f"  {path}" for path in base_roms) or "  (none)"
        fail(f"No base ROM matched {query!r} under {rom_root}. Candidates:\n{available}")
    if len(matches) > 1 and matches[0][0] - matches[1][0] < 0.05:
        ambiguous = "\n".join(f"  score={score:.3f} {path}" for score, path in matches[:8])
        fail(f"ROM selection is ambiguous; rerun with --rom and the exact base-game path:\n{ambiguous}")
    return matches[0][1]


def slugify(value: str, rom: Path) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "switch-game"
    identity = zlib.crc32(str(rom).encode("utf-8")) & 0xFFFFFFFF
    return f"{base[:64]}-{identity:08x}"


def steam_processes() -> list[str]:
    found: list[str] = []
    proc = Path("/proc")
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            comm = (item / "comm").read_text(encoding="utf-8").strip()
            cmdline = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if comm == "steam" or comm == "steamwebhelper" or re.search(r"(^|/)steam(\s|$)", cmdline):
            found.append(f"pid={item.name} {cmdline or comm}")
    return found


def steam_configs() -> list[Path]:
    roots = [Path.home() / ".local/share/Steam/userdata", Path.home() / ".steam/steam/userdata"]
    unique: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for config in root.glob("*/config"):
            if config.is_dir():
                resolved = config.resolve()
                unique[str(resolved)] = resolved
    return sorted(unique.values())


def choose_shortcuts(value: str | None) -> Path:
    if value and value != "auto":
        path = expand_path(value).resolve()
        if path.name != "shortcuts.vdf":
            fail(f"--shortcuts must name shortcuts.vdf: {path}")
        if not path.parent.is_dir():
            fail(f"Steam config directory does not exist: {path.parent}")
        return path
    configs = steam_configs()
    if not configs:
        fail("No local Steam userdata config found; pass --shortcuts explicitly")
    if len(configs) != 1:
        choices = "\n".join(f"  {config / 'shortcuts.vdf'}" for config in configs)
        fail(f"Multiple Steam users were found; pass --shortcuts explicitly:\n{choices}")
    return configs[0] / "shortcuts.vdf"


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
            value, pos = parse_object(data, pos)
        elif typ == TYPE_STRING:
            value, pos = read_cstr(data, pos)
        elif typ == TYPE_INT:
            value = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        elif typ == TYPE_UINT64:
            value = struct.unpack_from("<Q", data, pos)[0]
            pos += 8
        else:
            raise ValueError(f"Unsupported binary VDF type {typ} at offset {pos - 1}")
        items.append((typ, key, value))
    raise ValueError("Unexpected EOF while parsing binary VDF")


def emit_cstr(text: str) -> bytes:
    return text.encode("utf-8") + b"\x00"


def emit_object(items: list[tuple[int, str, object]]) -> bytes:
    output = bytearray()
    for typ, key, value in items:
        output.append(typ)
        output.extend(emit_cstr(key))
        if typ == TYPE_OBJECT:
            output.extend(emit_object(value))  # type: ignore[arg-type]
        elif typ == TYPE_STRING:
            output.extend(emit_cstr(str(value)))
        elif typ == TYPE_INT:
            output.extend(struct.pack("<I", int(value) & 0xFFFFFFFF))
        elif typ == TYPE_UINT64:
            output.extend(struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF))
        else:
            raise ValueError(f"Unsupported binary VDF type {typ}")
    output.append(TYPE_END)
    return bytes(output)


def load_shortcuts(path: Path) -> list[tuple[int, str, object]]:
    if not path.exists() or path.stat().st_size == 0:
        return [(TYPE_OBJECT, "shortcuts", [])]
    data = path.read_bytes()
    root, pos = parse_object(data, 0)
    if pos != len(data):
        raise ValueError(f"Trailing data in {path}: parsed {pos}, size {len(data)}")
    if len(root) != 1 or root[0][0] != TYPE_OBJECT or root[0][1] != "shortcuts":
        raise ValueError(f"Expected a top-level shortcuts object in {path}")
    return root


def field(entry: list[tuple[int, str, object]], name: str) -> object | None:
    for _, key, value in entry:
        if key == name:
            return value
    return None


def compute_appid(app_name: str, exe_field: str, used: set[int]) -> int:
    seed = exe_field + app_name
    for counter in range(1000):
        suffix = "" if counter == 0 else f":{counter}"
        appid = (zlib.crc32((seed + suffix).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
        if appid not in used:
            return appid
    raise RuntimeError("Unable to allocate a unique Steam shortcut app ID")


def shortcut_entry(
    appid: int,
    app_name: str,
    launcher: Path,
    start_dir: Path,
    launch_options: str,
    icon: str,
    collection: str,
) -> list[tuple[int, str, object]]:
    tags = [(TYPE_STRING, "0", collection)] if collection else []
    return [
        (TYPE_INT, "appid", appid),
        (TYPE_STRING, "AppName", app_name),
        (TYPE_STRING, "Exe", f'"{launcher}"'),
        (TYPE_STRING, "StartDir", f'"{start_dir}/"'),
        (TYPE_STRING, "icon", icon),
        (TYPE_STRING, "ShortcutPath", ""),
        (TYPE_STRING, "LaunchOptions", launch_options),
        (TYPE_INT, "IsHidden", 0),
        (TYPE_INT, "AllowDesktopConfig", 1),
        (TYPE_INT, "AllowOverlay", 1),
        (TYPE_INT, "OpenVR", 0),
        (TYPE_INT, "Devkit", 0),
        (TYPE_STRING, "DevkitGameID", ""),
        (TYPE_INT, "DevkitOverrideAppID", 0),
        (TYPE_INT, "LastPlayTime", 0),
        (TYPE_STRING, "FlatpakAppID", ""),
        (TYPE_STRING, "sortas", ""),
        (TYPE_OBJECT, "tags", tags),
    ]


def backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_suffix(path.suffix + f".bak-{stamp}")
    counter = 1
    while candidate.exists():
        candidate = path.with_suffix(path.suffix + f".bak-{stamp}-{counter}")
        counter += 1
    return candidate


def update_shortcuts(
    path: Path,
    app_name: str,
    launcher: Path,
    start_dir: Path,
    launch_options: str,
    icon: str,
    collection: str,
) -> tuple[int, Path | None]:
    root = load_shortcuts(path)
    entries = list(root[0][2])  # type: ignore[arg-type]
    exe_field = f'"{launcher}"'
    used = {
        int(field(entry, "appid"))
        for typ, _, entry in entries
        if typ == TYPE_OBJECT and field(entry, "appid") is not None  # type: ignore[arg-type]
    }
    kept: list[tuple[int, str, object]] = []
    reused_appid: int | None = None
    for typ, key, value in entries:
        if typ != TYPE_OBJECT:
            kept.append((typ, key, value))
            continue
        existing_name = field(value, "AppName")  # type: ignore[arg-type]
        existing_exe = field(value, "Exe")  # type: ignore[arg-type]
        if existing_name == app_name or existing_exe in {exe_field, str(launcher)}:
            reused_appid = int(field(value, "appid") or 0)  # type: ignore[arg-type]
            continue
        kept.append((typ, key, value))
    appid = reused_appid or compute_appid(app_name, exe_field, used)
    kept.append(
        (
            TYPE_OBJECT,
            "",
            shortcut_entry(
                appid,
                app_name,
                launcher,
                start_dir,
                launch_options,
                icon,
                collection,
            ),
        )
    )
    renumbered = [(typ, str(index), value) for index, (typ, _, value) in enumerate(kept)]
    payload = emit_object([(TYPE_OBJECT, "shortcuts", renumbered)])

    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if path.exists():
        backup = backup_path(path)
        shutil.copy2(path, backup)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return appid, backup


def atomic_symlink(target: str, link: Path) -> None:
    if link.exists() and link.is_dir() and not link.is_symlink():
        fail(f"Cannot replace directory with Eden symlink: {link}")
    temporary = link.with_name(link.name + ".tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, link)


def install_eden(source: Path, data_dir: Path, mode: str) -> Path:
    if mode == "direct":
        return source
    emulator_dir = data_dir / "emulators"
    emulator_dir.mkdir(parents=True, exist_ok=True)
    stable = emulator_dir / "Eden.AppImage"
    if mode == "copy":
        versioned = emulator_dir / source.name
        if source != versioned:
            temporary = versioned.with_name(versioned.name + ".tmp")
            shutil.copy2(source, temporary)
            temporary.chmod(temporary.stat().st_mode | 0o111)
            os.replace(temporary, versioned)
        else:
            versioned.chmod(versioned.stat().st_mode | 0o111)
        atomic_symlink(versioned.name, stable)
    elif mode == "symlink":
        atomic_symlink(str(source), stable)
    else:  # argparse and config validation should prevent this
        fail(f"Unsupported Eden install mode: {mode}")
    return stable


def write_launcher(path: Path, eden: Path, fullscreen: bool) -> None:
    arguments = [shlex.quote(str(eden))]
    if fullscreen:
        arguments.append("-f")
    arguments.extend(["-g", '"$ROM"'])
    script = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "if [[ $# -ne 1 ]]; then",
            '  echo "Usage: $0 ROM_PATH" >&2',
            "  exit 2",
            "fi",
            "",
            'ROM="$1"',
            'ROM="$(realpath -- "$ROM")"',
            "",
            f"EDEN={shlex.quote(str(eden))}",
            '[[ -x "$EDEN" ]] || { echo "Eden is missing or not executable: $EDEN" >&2; exit 1; }',
            '[[ -f "$ROM" ]] || { echo "Switch game is missing: $ROM" >&2; exit 1; }',
            "exec " + " ".join(arguments),
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(script, encoding="utf-8")
    temporary.chmod(0o755)
    os.replace(temporary, path)


def copy_art(art_dir: Path | None, data_dir: Path, slug: str) -> Path | None:
    stable_art = data_dir / "artwork" / slug
    if art_dir is None:
        return stable_art if stable_art.is_dir() else None
    if art_dir.resolve() == stable_art.resolve():
        return stable_art
    stable_art.mkdir(parents=True, exist_ok=True)
    for source in art_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, stable_art / source.name)
    return stable_art


def install_art(appid: int, art_dir: Path | None, grid_dir: Path) -> list[Path]:
    if art_dir is None:
        return []
    grid_dir.mkdir(parents=True, exist_ok=True)
    mapping = [
        (("capsule.png", "grid.png", "horizontal.png"), f"{appid}.png"),
        (("poster.png", "cover.png", "vertical.png"), f"{appid}p.png"),
        (("library_hero.png", "hero.png", "banner.png"), f"{appid}_hero.png"),
        (("logo.png",), f"{appid}_logo.png"),
        (("icon.png",), f"{appid}_icon.png"),
    ]
    installed: list[Path] = []
    for names, destination_name in mapping:
        source = next((art_dir / name for name in names if (art_dir / name).is_file()), None)
        if source is None:
            continue
        destination = grid_dir / destination_name
        shutil.copy2(source, destination)
        installed.append(destination)
    return installed


def verify_entry(
    path: Path,
    app_name: str,
    appid: int,
    launcher: Path,
    launch_options: str,
    collection: str,
) -> None:
    root = load_shortcuts(path)
    matches = [
        value
        for typ, _, value in root[0][2]  # type: ignore[index]
        if typ == TYPE_OBJECT and field(value, "AppName") == app_name  # type: ignore[arg-type]
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {app_name!r} shortcut after writing, found {len(matches)}")
    entry = matches[0]
    expected = {
        "appid": appid,
        "Exe": f'"{launcher}"',
        "LaunchOptions": launch_options,
    }
    for key, value in expected.items():
        if field(entry, key) != value:  # type: ignore[arg-type]
            raise RuntimeError(f"Shortcut verification failed for {key}: {field(entry, key)!r} != {value!r}")  # type: ignore[arg-type]
    tags = field(entry, "tags")  # type: ignore[arg-type]
    if collection and collection not in [value for typ, _, value in (tags or []) if typ == TYPE_STRING]:
        raise RuntimeError(f"Shortcut verification failed: missing collection {collection!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="~/.config/switch-steam/config.toml")
    parser.add_argument("--eden", default=None, help="Eden AppImage or executable path")
    parser.add_argument("--rom-root", default=None, help="Directory searched recursively for base ROMs")
    parser.add_argument("--game", default=None, help="Game title or distinctive title fragment")
    parser.add_argument("--rom", default=None, help="Exact base .xci or .nsp path")
    parser.add_argument("--app-name", default=None, help="Official Steam display and artwork name")
    parser.add_argument("--shortcuts", default=None, help="Exact shortcuts.vdf path, or auto")
    parser.add_argument("--art-dir", default=None, help="Artwork directory with Steam grid filenames")
    parser.add_argument("--data-dir", default=None, help="Stable emulator, launcher, and artwork directory")
    parser.add_argument("--install-mode", choices=("copy", "symlink", "direct"), default=None)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--fullscreen", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--allow-steam-running", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config_path = expand_path(args.config)
    config = load_config(config_path)

    eden_value = option(args.eden, config, "eden")
    rom_root_value = option(args.rom_root, config, "rom_root")
    if not eden_value:
        fail(f"Eden path is required via --eden or {config_path}")
    if not rom_root_value:
        fail(f"ROM root is required via --rom-root or {config_path}")
    eden_source = require_file(str(eden_value), "Eden")
    if not os.access(eden_source, os.X_OK):
        fail(f"Eden is not executable; run chmod +x on: {eden_source}")
    rom_root = require_directory(str(rom_root_value), "ROM root")
    rom = choose_rom(rom_root, args.game, args.rom)
    app_name = args.app_name or clean_title(rom)
    if not app_name.strip():
        fail("Steam display name cannot be empty")

    data_value = option(args.data_dir, config, "data_dir", "~/.local/share/switch-steam")
    mode = str(option(args.install_mode, config, "install_mode", "copy"))
    collection = str(option(args.collection, config, "collection", "Nintendo Switch"))
    fullscreen = bool(option(args.fullscreen, config, "fullscreen", True))
    shortcut_value = option(args.shortcuts, config, "steam_shortcuts", "auto")
    if mode not in {"copy", "symlink", "direct"}:
        fail(f"install_mode must be copy, symlink, or direct; got {mode!r}")
    data_dir = expand_path(str(data_value)).resolve()
    shortcuts = choose_shortcuts(str(shortcut_value) if shortcut_value else "auto")
    art_source = require_directory(args.art_dir, "Artwork directory") if args.art_dir else None
    slug = slugify(app_name, rom)
    installed_eden = eden_source if mode == "direct" else data_dir / "emulators/Eden.AppImage"
    launcher = data_dir / "launchers" / "switch-launch"

    plan = {
        "app_name": app_name,
        "rom": str(rom),
        "rom_root": str(rom_root),
        "eden_source": str(eden_source),
        "eden_installed": str(installed_eden),
        "install_mode": mode,
        "launcher": str(launcher),
        "shortcuts": str(shortcuts),
        "collection": collection,
        "fullscreen": fullscreen,
        "art_source": str(art_source) if art_source else None,
        "data_dir": str(data_dir),
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    running = steam_processes()
    if running and not args.allow_steam_running:
        details = "\n".join(f"  {process}" for process in running[:20])
        fail(f"Steam is running. Shut it down before editing shortcuts.vdf:\n{details}")

    installed_eden = install_eden(eden_source, data_dir, mode)
    write_launcher(launcher, installed_eden, fullscreen)
    stable_art = copy_art(art_source, data_dir, slug)
    launch_options = json.dumps(str(rom))
    icon_path = stable_art / "icon.png" if stable_art and (stable_art / "icon.png").is_file() else None
    appid, backup = update_shortcuts(
        shortcuts,
        app_name,
        launcher,
        rom.parent,
        launch_options,
        str(icon_path) if icon_path else "",
        collection,
    )
    installed_art = install_art(appid, stable_art, shortcuts.parent / "grid")
    verify_entry(
        shortcuts,
        app_name,
        appid,
        launcher,
        launch_options,
        collection,
    )

    result = dict(plan)
    result.update(
        {
            "eden_installed": str(installed_eden),
            "appid": appid,
            "backup": str(backup) if backup else None,
            "art_dir": str(stable_art) if stable_art else None,
            "art_installed": [str(path) for path in installed_art],
            "verified": True,
        }
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
