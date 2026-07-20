---
name: add-switch-games-to-steam
description: Add locally dumped Nintendo Switch games to desktop Linux Steam as individual non-Steam shortcuts launched by Eden, with configurable Eden and ROM-library paths, safe base-game selection, SteamGridDB artwork, a Nintendo Switch collection tag, and backed-up shortcuts.vdf edits. Use when Codex needs to configure an Eden AppImage, find a base .xci or .nsp while excluding updates/DLC/mods, add or refresh a Switch game in Steam, or diagnose a generated Eden Steam shortcut.
---

# Add Switch Games to Steam

Add one Steam entry per base Switch game. Keep the Eden executable and ROM root configurable; never assume a username or fixed directory.

## Workflow

1. Resolve the requested game, Eden executable, ROM root, Steam account, and whether Steam is local. This skill targets local desktop Linux; use the Steam Deck deployment skill for a remote Deck.
2. Use only game dumps, keys, firmware, updates, and DLC the user is authorized to use. Do not source copyrighted game content.
3. Confirm the Eden file is executable. Prefer a PGO AppImage when multiple builds of the same version exist, unless it fails on the host.
4. Stop Steam before writing `shortcuts.vdf`. Run `steam -shutdown`, then wait until `pgrep -a -i steam` is empty. In a managed Codex sandbox, perform that process check at the host permission level because the sandbox PID namespace may hide the desktop Steam process. Do not trust a sandbox-local negative result.
5. Fetch complete artwork with `scripts/fetch_steamgrid_art.py`. Use the official display name as the query and preserve `sources.json`.
6. Run `scripts/add_switch_game.py` with explicit `--eden`, `--rom-root`, and `--game` values, or store defaults in the optional TOML config. Pass `--shortcuts` explicitly when more than one Steam user is present.
7. Restart Steam and verify the entry, artwork, launch command, and `Nintendo Switch` collection. When Steam is launched outside a managed PID namespace, confirm it with a host-level process check.

## Configure Paths

All paths are configurable through flags. For repeat use, create `~/.config/switch-steam/config.toml`:

```toml
eden = "/absolute/path/to/Eden.AppImage"
rom_root = "/absolute/path/to/Switch"
install_mode = "copy"
collection = "Nintendo Switch"
```

Optional keys are `steam_shortcuts`, `data_dir`, `install_mode`, `collection`, and `fullscreen`. Command-line flags override config values.

Validate selection without changing files:

```bash
python3 scripts/add_switch_game.py \
  --eden /path/to/Eden.AppImage \
  --rom-root /path/to/Switch \
  --game "Tears of the Kingdom" \
  --app-name "The Legend of Zelda: Tears of the Kingdom" \
  --dry-run
```

The selector recursively considers `.xci` and `.nsp` files, rejects paths marked as updates, DLC, or mods, and treats nonzero `[vN]` NSPs as update candidates. If selection remains ambiguous, pass `--rom` with the exact base-game path; never guess between plausible files.

## Fetch Artwork

```bash
python3 scripts/fetch_steamgrid_art.py \
  --query "The Legend of Zelda: Tears of the Kingdom" \
  --output-dir /tmp/totk-steam-art \
  --allow-partial
```

Prefer SteamGridDB or user-provided artwork. Do not generate replacement art until sourced artwork is unavailable or unusable. The installer copies artwork and attribution into its stable data directory.

## Add or Update the Shortcut

```bash
python3 scripts/add_switch_game.py \
  --eden /path/to/Eden.AppImage \
  --rom-root /path/to/Switch \
  --game "Tears of the Kingdom" \
  --app-name "The Legend of Zelda: Tears of the Kingdom" \
  --shortcuts /path/to/Steam/userdata/STEAM_ID/config/shortcuts.vdf \
  --art-dir /tmp/totk-steam-art
```

The script installs a stable Eden path, creates a unique launcher per game, updates only the matching Steam entry, assigns the collection tag, copies available poster/capsule/hero/logo/icon assets, backs up an existing `shortcuts.vdf`, and prints all resulting paths.

Use `--install-mode copy` by default so deleting the original download does not break Steam. Use `symlink` when the emulator is maintained at a stable external path, or `direct` only when the supplied Eden path itself is stable.

## Guardrails

- Keep updates, DLC, and mods out of shortcut selection; install them inside Eden instead.
- Use absolute, resolved paths in launchers and Steam metadata.
- Do not auto-select a Steam account when multiple distinct `shortcuts.vdf` files exist.
- Treat the script's Steam-running check as defense in depth. In sandboxed execution, shut Steam down and verify at host level before invoking the script.
- Keep the printed backup path in the final report.
- Report the selected ROM, Eden source and installed path, Steam account path, app ID, collection, and artwork source.
- If Eden cannot open a display over SSH, configure the shortcut without launching the GUI and test it later from the active desktop session.
