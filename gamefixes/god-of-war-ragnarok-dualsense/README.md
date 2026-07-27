# God of War Ragnarök DualSense haptics

This is the known-working SteamOS/Linux setup for native wired DualSense
input, adaptive triggers, controller audio, and detailed haptics in the Steam
release of God of War Ragnarök.

- Steam app ID: `2322010`
- Proton build: `Proton-EM-11-20260624-DS5`
- Controller connection: USB
- Steam Input: disabled for this game
- NoPSSDK proxy DLL: enabled as native, then builtin

## Why every part is needed

Ragnarök needs native HID access to see the DualSense instead of an emulated
Xbox controller. Its detailed haptics are audio-driven and also need the
DualSense-aware `mmdevapi` patches in
[`xzn/proton-ds5-haptic`](https://github.com/xzn/proton-ds5-haptic).

GE/EM Proton builds include a `2322010.py` game fix which sets `SteamDeck=1`
to work around PlayStation PC SDK startup errors. Their Proton launcher then
sets `PROTON_DISABLE_HIDRAW` for Sony controllers when both the app ID and
`SteamDeck=1` match. That makes the game lose native DualSense HID support.

The working combination is:

1. Use the non-GE `Proton-EM` DS5 build.
2. Disable its bundled per-game Proton fixes with `PROTONFIXES_DISABLE=1`.
3. Keep `SteamDeck=0`, so the launcher's direct HID-disable condition is
   false.
4. Use NoPSSDK's `version.dll` proxy and its Wine DLL override instead of the
   `SteamDeck=1` PlayStation SDK workaround.
5. Enable the DS5 build's fake exclusive audio path with
   `PROTON_MMDEV_FAKE_EXCLUSIVE=1`.
6. Disable Steam Input so the game receives the physical DualSense HID
   device.

## Prerequisites

- The Steam version of God of War Ragnarök is installed.
- A DualSense is connected by USB before the game starts.
- A trusted copy of NoPSSDK is available. The original project was withdrawn,
  so this repository does not download or redistribute the mod.

NoPSSDK must place both of these files beside `GoWR.exe`:

```text
PsPcSdk.dll
version.dll
```

Use Steam's **Manage > Browse local files** to find the actual game directory.
Do not assume it is in the default Steam library.

## Install the pinned DS5 Proton build

The known-good upstream release is
[`20260624`](https://github.com/xzn/proton-ds5-haptic/releases/tag/20260624).
Use the `Proton-EM` asset, not the `GE-Proton` asset.

```bash
ds5_work_dir="$(mktemp -d)"
ds5_archive="$ds5_work_dir/Proton-EM-11-20260624-DS5.tar.gz"
steam_root="${STEAM_ROOT:-$HOME/.local/share/Steam}"

curl -fL \
  -o "$ds5_archive" \
  https://github.com/xzn/proton-ds5-haptic/releases/download/20260624/Proton-EM-11-20260624-DS5.tar.gz

printf '%s  %s\n' \
  6dc70c7c3152c1119d5b059dc1e3d7cef83448f06c42b9456152499c70758792 \
  "$ds5_archive" |
  sha256sum -c -

mkdir -p "$steam_root/compatibilitytools.d"
test ! -e "$steam_root/compatibilitytools.d/Proton-EM-11-20260624-DS5"
tar -xzf "$ds5_archive" -C "$steam_root/compatibilitytools.d"
```

The published archive is `532358430` bytes. The checksum command must report
`OK`. Stop if the target directory already exists; inspect the existing
installation instead of merging an archive over it.

Steam only discovers compatibility tools at startup. Fully restart Steam
after extraction.

## Configure Ragnarok in Steam

Open **God of War Ragnarök > Properties** and set all three items below.

### Compatibility

Enable **Force the use of a specific Steam Play compatibility tool**, then
select:

```text
Proton-EM-11-20260624-DS5
```

### Controller

Set the per-game Steam Input override to:

```text
Disable Steam Input
```

### General launch options

Enter this as one line:

```text
PROTONFIXES_DISABLE=1 PROTON_MMDEV_FAKE_EXCLUSIVE=1 WINEDLLOVERRIDES="version=n,b" SteamDeck=0 %command%
```

Do not change `SteamDeck=0` to `SteamDeck=1`. Do not omit
`PROTONFIXES_DISABLE=1`; the pinned `Proton-EM` archive still contains the
per-game fix that sets `SteamDeck=1`.

## Verify before launch

1. Confirm `PsPcSdk.dll` and `version.dll` are beside `GoWR.exe`.
2. Confirm the selected compatibility tool is
   `Proton-EM-11-20260624-DS5`.
3. Confirm Steam Input is disabled for Ragnarok.
4. Connect the DualSense over USB before pressing Play.
5. Confirm the launch options still exactly contain all four assignments:
   `PROTONFIXES_DISABLE`, `PROTON_MMDEV_FAKE_EXCLUSIVE`,
   `WINEDLLOVERRIDES`, and `SteamDeck=0`.

Expected behavior:

- The game shows PlayStation button prompts.
- Adaptive triggers work.
- Detailed effects are felt through the controller instead of only generic
  rumble.
- Normal game audio continues through the chosen speakers or headphones.

## Audio troubleshooting

Do not make the DualSense the default desktop audio output. The DS5 Proton
patches let the game associate the controller's HID and audio endpoints.

If native input and adaptive triggers work but detailed haptics do not:

1. Confirm `PROTON_MMDEV_FAKE_EXCLUSIVE=1` is present.
2. Check that Linux exposes the wired controller as a four-channel or Pro
   Audio device:

   ```bash
   wpctl status
   pactl list cards short
   pactl list cards
   ```

3. If the controller card is using a stereo-only profile, select an available
   four-channel, Analog Surround 4.0, or Pro Audio profile. Profile names vary
   by PipeWire/ALSA release, so inspect the card's advertised profiles before
   using `pactl set-card-profile`.
4. Disconnect and reconnect the controller, then restart the game.

Only add a WirePlumber or ALSA override if no four-channel profile is
available. Preserve and document the original audio configuration before
doing so; the known-working SteamOS setup did not require a system audio
override.

## Safe low-level Steam configuration

Steam's UI is preferred. For automated configuration, note that Ragnarok is a
native Steam app, not a non-Steam shortcut:

- Launch options are stored in the active user's
  `userdata/<account-id>/config/localconfig.vdf` under app `2322010`.
- The compatibility tool mapping is stored in Steam's `config/config.vdf`
  under `CompatToolMapping/2322010`.
- `shortcuts.vdf` is not involved.

Stop Steam before editing either VDF and wait until it is fully inactive:

```bash
systemctl --user stop app-steam@autostart.service
```

If that unit does not exist, use Steam's **Exit** action or `steam -shutdown`.
Identify the active Steam account instead of choosing the newest userdata
directory blindly. Back up both VDF files with a timestamp, edit only app
`2322010`, restart Steam, and verify that Steam preserved the values.

The required compatibility mapping name is:

```text
Proton-EM-11-20260624-DS5
```

The launch-options value inside VDF escapes the inner quotes:

```text
PROTONFIXES_DISABLE=1 PROTON_MMDEV_FAKE_EXCLUSIVE=1 WINEDLLOVERRIDES=\"version=n,b\" SteamDeck=0 %command%
```

For the active user, the controller override should report
`UseSteamControllerConfig` as `0` for app `2322010`.

## Recovery

- If the game reports a PlayStation PC SDK startup error, verify the two
  NoPSSDK files and the `version=n,b` override. Do not work around it by
  enabling `SteamDeck=1`.
- If the game shows Xbox prompts, recheck the USB connection and disable
  Steam Input.
- If a newer DS5 Proton release is tested, inspect its
  `protonfixes/gamefixes-steam/2322010.py` and its `proton` launcher for
  `SteamDeck` and `PROTON_DISABLE_HIDRAW` behavior before changing these
  launch options.
- Do not delete the game's Proton prefix as a first troubleshooting step.
  Prefix deletion can remove local state; back it up before any reset.
