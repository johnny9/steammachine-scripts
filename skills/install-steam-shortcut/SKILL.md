---
name: install-steam-shortcut
description: Install a local game or executable into Steam as a non-Steam shortcut, preferring SteamGridDB or internet-sourced Steam library artwork before generated fallback art. Use when Codex needs to add a locally installed game to Steam, update Steam shortcuts.vdf, install poster, capsule, hero, logo, or icon artwork into the Steam grid cache, fetch Steam grid art from the internet, or restart Steam so a shortcut appears.
---

# Install Steam Shortcut

## Overview

Use this skill to add or update a local non-Steam game shortcut with Steam Deck friendly artwork. Prefer a complete runtime directory as the working directory, not just a lone executable, unless the game is known to be self-contained.

## Workflow

1. Identify the executable, working directory, display name, launch options, and whether Steam is local or remote. For local-only installs, stay in this skill; for Steam Deck SSH deployment, use the `install-steamdeck-game` skill.
2. Prepare artwork with this priority: use user-provided licensed assets first; otherwise fetch SteamGridDB or other Steam-grid artwork from the internet; generate art only when suitable sourced art is unavailable. Prefer SteamGridDB via `scripts/fetch_steamgrid_art.py`; it uses SteamGridDB's public endpoints and does not require an API key.
3. Stop Steam before editing `shortcuts.vdf`. On SteamOS use `systemctl --user stop app-steam@autostart.service`; on desktop Linux use `steam -shutdown` or the local service manager. Wait until the main Steam process exits.
4. Run `scripts/update_shortcut.py` to add or update the shortcut and copy grid artwork.
5. Restart Steam and verify that the shortcut remains in `shortcuts.vdf` and the grid files exist.

## Scripts

Fetch SteamGridDB art:

```bash
python3 /path/to/skill/scripts/fetch_steamgrid_art.py \
  --query "Game Name" \
  --output-dir /tmp/game-steam-art \
  --allow-partial
```

The SteamGridDB public path learned from use:

- search games with `GET https://www.steamgriddb.com/api/public/search/autocomplete?term=<query>`
- search assets with `POST https://www.steamgriddb.com/api/public/search/assets`
- include filters like `styles`, `languages`, `dimensions`, `formats`, `order`, `game_id`, `static`, `animated`, `nsfw`, `epilepsy`, `humor`, `untagged`, `asset_type`, `page`, and `limit`
- use game pages such as `https://www.steamgriddb.com/game/37177` as source attribution

The fetch script saves `sources.json` with SteamGridDB asset pages, CDN URLs, authors, dimensions, hearts, and downloads. If SteamGridDB fails, use web or image search to find community grid assets manually before generating. Save downloaded assets into the same names listed below, and keep a short `sources.json` with source URLs. Do not generate art until this internet-sourced path has failed or produced unusable results.

Generate artwork:

```bash
python3 /path/to/skill/scripts/steam_art.py \
  --title "Game Name" \
  --subtitle "Native PC Port" \
  --output-dir /tmp/game-steam-art
```

Use a generated or existing base image:

```bash
python3 /path/to/skill/scripts/steam_art.py \
  --title "Game Name" \
  --base /path/to/base.png \
  --output-dir /tmp/game-steam-art
```

Install or update the shortcut:

```bash
python3 /path/to/skill/scripts/update_shortcut.py \
  --app-name "Game Name" \
  --exe /absolute/path/to/game \
  --start-dir /absolute/path/to/runtime-dir \
  --icon /tmp/game-steam-art/icon.png \
  --launch-options="--fullscreen" \
  --art-dir /tmp/game-steam-art
```

`update_shortcut.py` defaults to auto-detecting the newest local Steam userdata config under `~/.local/share/Steam/userdata` or `~/.steam/steam/userdata`. If there are multiple Steam users and the newest one is not clearly correct, pass `--shortcuts /path/to/shortcuts.vdf` explicitly.

## Artwork Names

The art script writes these files:

- `poster.png`: vertical library cover, copied as `<appid>p.png`
- `capsule.png`: horizontal capsule, copied as `<appid>.png`
- `hero.png` or `library_hero.png`: wide hero banner, copied as `<appid>_hero.png`
- `logo.png`: transparent logo, copied as `<appid>_logo.png`
- `icon.png`: shortcut icon, used in `shortcuts.vdf` and also copied as `<appid>_icon.png`

## Guardrails

- Do not edit `shortcuts.vdf` while Steam is running unless the user explicitly accepts the risk; Steam can overwrite manual edits.
- Always keep the script-created backup path from `update_shortcut.py` in the final answer.
- Report whether artwork came from SteamGridDB/internet sources, user-provided files, or generation. Preserve `sources.json` when sourced art is used.
- Use absolute paths in `Exe`, `StartDir`, and `icon`.
- Quote `--launch-options` as `--launch-options=--fullscreen` when the value starts with a dash.
- Do not use downloaded art as an image-generation reference unless the user has rights to it. Downloaded SteamGridDB/community art is for installing directly as shortcut artwork; generated fallback art should be stylistically generic unless the user supplies licensed references.
