#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run(cmd: list[str], dry_run: bool = False, capture: bool = False) -> str:
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"+ {printable}")
    if dry_run:
        return ""
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    subprocess.run(cmd, check=True)
    return ""


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "game"


def remote_shell(host: str, command: str, dry_run: bool = False, capture: bool = False) -> str:
    return run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command], dry_run=dry_run, capture=capture)


def remote_exec(host: str, argv: list[str], dry_run: bool = False, capture: bool = False) -> str:
    return remote_shell(host, " ".join(shlex.quote(arg) for arg in argv), dry_run=dry_run, capture=capture)


def choose_executable(source: Path, exe_rel: str | None) -> tuple[Path, str]:
    source = source.resolve()
    if source.is_file():
        if exe_rel:
            raise SystemExit("--exe-rel is only valid when --source is a directory")
        return source.parent, source.name
    if not source.is_dir():
        raise SystemExit(f"Source does not exist: {source}")
    if exe_rel:
        exe = source / exe_rel
        if not exe.exists():
            raise SystemExit(f"--exe-rel does not exist under source: {exe_rel}")
        return source, exe_rel

    candidates: list[Path] = []
    for path in source.iterdir():
        if not path.is_file():
            continue
        mode = path.stat().st_mode
        if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            candidates.append(path)
    candidates = [p for p in candidates if not p.name.endswith((".so", ".dll", ".dylib"))]
    if len(candidates) == 1:
        return source, candidates[0].name
    if not candidates:
        raise SystemExit("Could not auto-detect a top-level executable. Pass --exe-rel.")
    names = ", ".join(p.name for p in candidates)
    raise SystemExit(f"Multiple executable candidates found: {names}. Pass --exe-rel.")


def detect_remote_config(host: str, dry_run: bool = False) -> str:
    code = (
        "from pathlib import Path\n"
        "roots=[Path.home()/'.local/share/Steam/userdata', Path.home()/'.steam/steam/userdata']\n"
        "configs=[]\n"
        "for root in roots:\n"
        "    if root.exists(): configs += [p for p in root.glob('*/config') if p.is_dir()]\n"
        "if not configs: raise SystemExit('no Steam userdata config dirs found')\n"
        "def score(p):\n"
        "    files=[x for x in [p/'shortcuts.vdf', p/'localconfig.vdf'] if x.exists()]\n"
        "    return max([x.stat().st_mtime for x in files] or [p.stat().st_mtime])\n"
        "print(max(configs, key=score))\n"
    )
    if dry_run:
        return "/home/deck/.local/share/Steam/userdata/0/config"
    return remote_exec(host, ["python3", "-c", code], capture=True)


def generate_art(name: str, subtitle: str, art_dir: Path, base: str | None, dry_run: bool) -> None:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "steam_art.py"),
        "--title",
        name,
        "--subtitle",
        subtitle,
        "--output-dir",
        str(art_dir),
    ]
    if base:
        cmd.extend(["--base", base])
    run(cmd, dry_run=dry_run)


def fetch_steamgrid_art(name: str, art_dir: Path, query: str | None, game_id: int | None, api_key: str, dry_run: bool) -> bool:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "fetch_steamgrid_art.py"),
        "--query",
        query or name,
        "--output-dir",
        str(art_dir),
        "--allow-partial",
    ]
    if game_id is not None:
        cmd.extend(["--game-id", str(game_id)])
    if api_key:
        cmd.extend(["--api-key", api_key])
    try:
        run(cmd, dry_run=dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"SteamGridDB artwork fetch failed; falling back to generated art: {exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="deck@steamdeck.local")
    parser.add_argument("--source", required=True, help="Local runtime directory, or a single executable")
    parser.add_argument("--name", required=True)
    parser.add_argument("--exe-rel", default=None)
    parser.add_argument("--remote-dir", default=None)
    parser.add_argument("--launch-options", default="--fullscreen")
    parser.add_argument("--art-dir", default=None)
    parser.add_argument("--base-art", default=None)
    parser.add_argument("--subtitle", default="Steam Deck")
    parser.add_argument("--steamgrid-query", default=None)
    parser.add_argument("--steamgrid-game-id", type=int, default=None)
    parser.add_argument("--steamgriddb-api-key", default=os.environ.get("STEAMGRIDDB_API_KEY", ""))
    parser.add_argument("--no-steamgrid", action="store_true")
    parser.add_argument("--require-steamgrid", action="store_true")
    parser.add_argument("--skip-restart", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source_root, exe_rel = choose_executable(Path(args.source), args.exe_rel)
    remote_dir = args.remote_dir or f"/home/deck/Games/{slug(args.name)}"
    remote_art = f"{remote_dir.rstrip('/')}/steam_art"
    remote_exe = f"{remote_dir.rstrip('/')}/{exe_rel}"

    if args.art_dir:
        art_dir = Path(args.art_dir).resolve()
    else:
        art_dir = Path(tempfile.mkdtemp(prefix=f"{slug(args.name)}-steam-art-"))
        fetched = False
        if not args.no_steamgrid and not args.base_art:
            fetched = fetch_steamgrid_art(
                args.name,
                art_dir,
                args.steamgrid_query,
                args.steamgrid_game_id,
                args.steamgriddb_api_key,
                args.dry_run,
            )
        if args.require_steamgrid and not fetched:
            raise SystemExit("SteamGridDB artwork was required but could not be fetched")
        if not fetched:
            generate_art(args.name, args.subtitle, art_dir, args.base_art, args.dry_run)

    remote_shell(args.host, f"mkdir -p {shlex.quote(remote_dir)} {shlex.quote(remote_art)}", dry_run=args.dry_run)
    source_arg = str(source_root) + ("/" if source_root.is_dir() else "")
    run(["rsync", "-az", "--delete", source_arg, f"{args.host}:{remote_dir.rstrip('/')}/"], dry_run=args.dry_run)
    run(["rsync", "-az", "--delete", str(art_dir) + "/", f"{args.host}:{remote_art}/"], dry_run=args.dry_run)
    run(["rsync", "-az", str(SCRIPT_DIR / "update_shortcut.py"), f"{args.host}:/tmp/update_steam_shortcut.py"], dry_run=args.dry_run)

    config_dir = detect_remote_config(args.host, dry_run=args.dry_run)
    shortcuts = f"{config_dir}/shortcuts.vdf"
    grid = f"{config_dir}/grid"

    if not args.skip_restart:
        stop = (
            "systemctl --user stop app-steam@autostart.service || steam -shutdown || true; "
            "for i in $(seq 1 30); do "
            "if ! pgrep -u \"$USER\" -x steam >/dev/null 2>&1; then break; fi; "
            "sleep 1; done"
        )
        remote_shell(args.host, stop, dry_run=args.dry_run)

    update_cmd = [
        "python3",
        "/tmp/update_steam_shortcut.py",
        "--shortcuts",
        shortcuts,
        "--grid-dir",
        grid,
        "--art-dir",
        remote_art,
        "--app-name",
        args.name,
        "--exe",
        remote_exe,
        "--start-dir",
        remote_dir,
        "--icon",
        f"{remote_art}/icon.png",
        f"--launch-options={args.launch_options}",
    ]
    update_output = remote_exec(args.host, update_cmd, dry_run=args.dry_run, capture=not args.dry_run)
    if update_output:
        print(update_output)

    if not args.skip_restart:
        start = (
            "systemctl --user start app-steam@autostart.service || true; "
            "for i in $(seq 1 45); do "
            "if pgrep -u \"$USER\" -x steam >/dev/null 2>&1; then break; fi; "
            "sleep 1; done; "
            "if ! pgrep -u \"$USER\" -x steam >/dev/null 2>&1; then "
            "nohup steam -silent >/tmp/steam-start.log 2>&1 & "
            "for i in $(seq 1 45); do "
            "if pgrep -u \"$USER\" -x steam >/dev/null 2>&1; then break; fi; "
            "sleep 1; done; "
            "fi; "
            "printf 'service='; systemctl --user is-active app-steam@autostart.service || true; "
            "printf 'steam_pids='; pgrep -u \"$USER\" -x steam | tr '\\n' ' ' || true; printf '\\n'"
        )
        remote_shell(args.host, start, dry_run=args.dry_run)

    print(f"remote_dir={remote_dir}")
    print(f"remote_exe={remote_exe}")
    print(f"remote_art={remote_art}")
    print(f"shortcuts={shortcuts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
