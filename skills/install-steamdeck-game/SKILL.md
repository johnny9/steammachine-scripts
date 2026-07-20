---
name: install-steamdeck-game
description: Deploy a local game build to a Steam Deck over SSH and add it to Steam as a non-Steam shortcut, preferring SteamGridDB or internet-sourced Steam Deck artwork before generated fallback art. Use when Codex needs to copy a compiled game or runtime directory to deck@steamdeck.local or another Deck host, fetch Steam grid art from the internet, install shortcut art, update the Deck's shortcuts.vdf, and restart Steam remotely.
---

# Install Steam Deck Game

## Overview

Use this skill to copy a local game runtime to a Steam Deck and register it as a Steam shortcut with poster, capsule, hero, logo, and icon art. This wraps the local `install-steam-shortcut` workflow with SSH, rsync, remote Steam config discovery, and Steam service restart.

## Workflow

1. Identify the local runtime directory and executable. Prefer copying the complete build/runtime directory that the executable expects as its working directory.
2. Choose the Deck target. Default host is `deck@steamdeck.local`; default destination is `/home/deck/Games/<slug>`.
3. Prepare Steam artwork locally with this priority: user-provided licensed art; SteamGridDB or other internet Steam-grid art; generated fallback art. `scripts/install_steamdeck_game.py` tries SteamGridDB first using public endpoints, then generates generic art if needed.
4. Copy the runtime and art to the Deck with `rsync`.
5. Stop Steam remotely, update the Deck's `shortcuts.vdf`, install grid artwork, then restart Steam.
6. Verify the shortcut text and grid files over SSH after restart.

## Main Command

```bash
python3 /path/to/skill/scripts/install_steamdeck_game.py \
  --host deck@steamdeck.local \
  --source /path/to/build-or-runtime-dir \
  --name "Game Name" \
  --exe-rel relative/path/to/executable \
  --remote-dir /home/deck/Games/game-name \
  --launch-options="--fullscreen"
```

Use SteamGridDB explicitly:

```bash
python3 /path/to/skill/scripts/install_steamdeck_game.py \
  --host deck@steamdeck.local \
  --source /path/to/runtime \
  --name "Game Name" \
  --exe-rel game-binary \
  --steamgrid-query "Game Name" \
  --launch-options="--fullscreen"
```

Pass `--steamgrid-game-id <id>` when the query could match the wrong game. Example learned during SM64EX setup: Super Mario 64 is SteamGridDB game id `37177`.

If `--exe-rel` is omitted, the script tries to pick a top-level executable from the source directory. Pass `--exe-rel` when there is more than one plausible executable.

Use prepared art:

```bash
python3 /path/to/skill/scripts/install_steamdeck_game.py \
  --host deck@steamdeck.local \
  --source /path/to/runtime \
  --name "Game Name" \
  --exe-rel game-binary \
  --art-dir /path/to/steam-art
```

## Remote Behavior

The installer:

- creates the remote destination directory
- syncs the local source with `rsync -az --delete`
- syncs artwork to `<remote-dir>/steam_art`
- uploads the shortcut updater to `/tmp`
- chooses the newest Steam config under the remote user's Steam userdata directories
- stops `app-steam@autostart.service` when present
- updates `shortcuts.vdf` with a backup
- installs grid art in the matching `config/grid` directory
- starts Steam again and waits for a Steam process
- treats SteamOS `app-steam@autostart.service` as a best-effort launcher. The unit can report `inactive` or be skipped by `exec-condition` while an actual Steam gamepad UI process is running; verify `pgrep -u "$USER" -x steam`, not only the service state.

## Compatibility Checks

After copying a Linux binary to the Deck, verify it on the Deck itself:

```bash
ssh deck@steamdeck.local 'file "$HOME/Games/game/game-binary"; ldd "$HOME/Games/game/game-binary"; "$HOME/Games/game/game-binary" --help || true'
```

If `ldd` or launch output says a `GLIBC_` version is not found, the binary was built against a newer host glibc than SteamOS provides. Fix by rebuilding inside an older/containerized toolchain, building natively on the Deck, or adjusting the build so it does not call a too-new symbol. In the SM64EX case, the host build required `sqrtf@GLIBC_2.43` while the Deck had glibc 2.41; rebuilding with generic x86-64 flags and `-fno-math-errno` removed that too-new libm requirement.

## SteamGridDB Public Endpoints

Prefer the bundled `fetch_steamgrid_art.py`; it does not require `STEAMGRIDDB_API_KEY`. It uses:

- `GET https://www.steamgriddb.com/api/public/search/autocomplete?term=<query>`
- `POST https://www.steamgriddb.com/api/public/search/assets`
- source attribution via `https://www.steamgriddb.com/game/<game_id>` and per-asset pages such as `/grid/<id>`, `/hero/<id>`, `/logo/<id>`, `/icon/<id>`

## Guardrails

- Request sandbox/network escalation for `ssh` and `rsync` when the environment requires it.
- Do not use `--delete` against a broad remote directory. Keep `--remote-dir` scoped to the game's own folder.
- If remote Steam config discovery finds the wrong account or multiple active accounts are plausible, inspect `~/.local/share/Steam/userdata/*/config` and pass the intended path through manual use of `update_shortcut.py`.
- Preserve any printed `backup=` path in the final answer.
- Report whether artwork came from SteamGridDB/internet sources, prepared files, or generation. Preserve `sources.json` in `<remote-dir>/steam_art` when sourced art is used.
- Use SteamGridDB/community Steam grid assets before generating. Generation is the fallback, not the primary source.
- For Steam Deck use, prefer launch option `--fullscreen` when the game supports it.
