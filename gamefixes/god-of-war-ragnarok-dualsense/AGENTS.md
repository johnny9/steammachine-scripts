# Agent instructions

These instructions apply to the God of War Ragnarök DualSense gamefix in this
directory. Read `README.md` completely before changing the machine.

## Required outcome

Configure Steam app `2322010` for native wired DualSense HID, adaptive
triggers, controller audio, and detailed haptics without allowing a Proton
game fix to force `SteamDeck=1`.

The final launch options must be exactly:

```text
PROTONFIXES_DISABLE=1 PROTON_MMDEV_FAKE_EXCLUSIVE=1 WINEDLLOVERRIDES="version=n,b" SteamDeck=0 %command%
```

The selected tool must be `Proton-EM-11-20260624-DS5`, and Steam Input must be
disabled for the game.

## Procedure

1. Discover the Steam root, every Steam library, the
   `appmanifest_2322010.acf` location, the game directory, the app's actual
   `compatdata/2322010` prefix, the active Steam account, and existing
   compatibility tools. Do not hardcode a username, account ID, library path,
   or assume the prefix is under the default Steam library.
2. Confirm the DualSense will be used over USB. Native detailed haptics are
   not validated here over Bluetooth.
3. Confirm trusted NoPSSDK files `PsPcSdk.dll` and `version.dll` are beside
   `GoWR.exe`. Do not fetch the withdrawn mod from an untrusted mirror or
   redistribute its binaries.
4. Locate the PSPC runtime's `libScePad.dll` inside that same app prefix under
   `pfx/drive_c/ProgramData/Sony Interactive Entertainment Inc/PSPC_SDK/S22/`.
   The runtime can be installed correctly in the prefix while remaining
   outside the game's DLL search path. Discover the installed version
   directory instead of hardcoding it. If there is exactly one trusted
   candidate and no destination file, copy it beside `GoWR.exe`, then verify
   that the source and destination hashes match. If multiple runtime versions
   or an existing destination are present, inspect them and obtain approval
   before choosing or overwriting anything. Never download `libScePad.dll`
   from a DLL site or take it from another game's prefix.
5. Download the pinned non-GE
   `Proton-EM-11-20260624-DS5.tar.gz` asset from the upstream `20260624`
   GitHub release and verify SHA-256
   `6dc70c7c3152c1119d5b059dc1e3d7cef83448f06c42b9456152499c70758792`.
6. Inspect an existing target directory instead of overwriting it. Otherwise,
   extract the archive under Steam's `compatibilitytools.d`.
7. Stop Steam and verify it is inactive before directly editing Steam VDF
   files. Back up each file first and retain the backup paths.
8. Configure app `2322010`, not a non-Steam shortcut:
   - Set `CompatToolMapping/2322010/name` in Steam's `config.vdf` to
     `Proton-EM-11-20260624-DS5`.
   - Set the app's `LaunchOptions` in the active account's
     `localconfig.vdf`, escaping embedded quotes as VDF requires.
   - Set or verify the per-game Steam Input override is disabled;
     `UseSteamControllerConfig` should be `0`.
   - Never edit `shortcuts.vdf` for this game.
9. Restart Steam and verify it preserved the compatibility mapping, launch
   options, and controller override.
10. Have the user connect the DualSense by USB before launch. Confirm that no
    `libScePad` runtime warning appears, then validate PlayStation prompts,
    adaptive triggers, and detailed haptics.
11. If haptics alone are missing, inspect the controller's PipeWire/ALSA card
    profiles. Prefer an existing four-channel/Analog Surround 4.0/Pro Audio
    profile. Do not create a system audio override until the existing profiles
    have been checked and the user approves that wider change.

## Guardrails

- Never set `SteamDeck=1` for this configuration. The bundled game fix and
  launcher behavior can then disable Sony HIDRAW access.
- Never remove `PROTONFIXES_DISABLE=1` while using the pinned archive; it
  still contains `protonfixes/gamefixes-steam/2322010.py`.
- Keep `PROTON_MMDEV_FAKE_EXCLUSIVE=1`; the upstream DS5 patch documents it
  for Ragnarok haptics.
- Keep `WINEDLLOVERRIDES="version=n,b"` while NoPSSDK's `version.dll` proxy
  is installed.
- Use only the `libScePad.dll` installed by Ragnarok's own PSPC runtime in the
  discovered AppID `2322010` prefix. Verify the copied file byte-for-byte.
- Do not set the DualSense as the default desktop audio sink.
- Do not delete a Proton prefix or user preferences without a backup and
  explicit approval.
- Do not overwrite a compatibility-tool directory, Steam VDF, NoPSSDK DLL,
  `libScePad.dll`, or audio configuration without inspecting the existing file
  and preserving a recoverable backup.
- Report the selected Steam root, game directory, app prefix, Proton version,
  `libScePad.dll` source and destination, final launch options, Steam Input
  state, validation result, hashes, and all backup paths.

## Repository hygiene

Documentation and automation added here must use portable paths such as
`$HOME` and discovered Steam libraries. Never commit a personal username,
Steam account ID, host address, credential, or local absolute home path.
