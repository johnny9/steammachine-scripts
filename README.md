# SteamOS systemd customizations

This repository contains SteamOS systemd units and helper scripts. It is **not** a generic installer: several services control specific hardware and require machine-specific configuration, device IDs, controller addresses, and power limits.

## Agent installation contract

When asked to install this repository, an agent must:

1. Ask which features the user wants. Do not assume every feature should be installed or enabled.
2. Collect and confirm the selected features' configuration values with the user: USB relay device or IDs, Bluetooth controller and USB IDs, RyzenAdj limits, desktop username, and external dependency paths.
3. Preserve every existing file under `/etc/steamos-scripts`; never replace configuration without showing the diff and receiving explicit approval.
4. Install program and unit files, then run `scripts/preflight` for every selected feature. Do not enable a feature unless its preflight passes.
5. Treat `steamos-readonly disable`, `sudo install`, and `systemctl enable` or `start` as state-changing operations. Get the user's approval before running them.
6. Reload systemd, then enable only the services the user explicitly selected.
7. Do not enable `xbox-controller-bluetooth-reconnect.service`; it is intentionally disabled and has no `[Install]` section.
8. Verify enabled units, their recent logs, and the actual hardware result. Re-enable SteamOS's read-only root filesystem when installation is complete.

## Contents

| Feature | Units | Installed files | Prerequisite / configuration |
| --- | --- | --- | --- |
| USB relay at boot, shutdown, sleep, and wake | `usb-relay.service`, `usb-relay-sleep.service` | `/usr/local/sbin/usb-relay`, `/etc/steamos-scripts/usb-relay.env` | Configure a stable device path, or explicitly choose automatic USB-ID discovery. |
| Ryzen CPU power limits | `ryzenadj.service`, `ryzenadj-tdp.service` | `/usr/local/sbin/apply-ryzenadj-limits`, `/etc/steamos-scripts/ryzenadj.env` | Install `/usr/bin/ryzenadj` and configure safe boot and resume limits for the target CPU. |
| Xbox Bluetooth / GameSir USB wake | `xbox-controller-bluetooth-wake.service`, `xbox-controller-bluetooth-sleep.service` | `/usr/local/sbin/xbox-controller-bluetooth-wake`, `/etc/steamos-scripts/controller-wake.env` | Pair the controller and configure its MAC address and USB IDs if necessary. Requires BlueZ and `bluetoothctl`. |
| Turn off RAM RGB in the user session | `ram-led-off.service` | `~/.local/bin/ram-led-off` | Install the `org.openrgb.OpenRGB` Flatpak. The script only runs when exactly two DRAM devices are detected. |
| LACT daemon | `lactd.service` | `/etc/steamos-scripts/lactd.env` | Install LACT's Flatpak and configure its user and daemon path. |
| PluginLoader | `plugin_loader.service` | `/etc/steamos-scripts/plugin-loader.env` | Install PluginLoader and configure its executable path. |

## Install

Run these commands from the repository root. They deploy the files but do **not** enable any system service.

SteamOS mounts its root filesystem read-only by default. Temporarily make it writable:

```bash
sudo steamos-readonly disable
```

Review the configuration templates before copying them:

```bash
sed -n '1,160p' scripts/etc/steamos-scripts/*.env.example
```

Install the scripts and units for the selected features. Run only the relevant groups. These commands do not install or replace configuration:

```bash
# USB relay
sudo install -Dm755 scripts/usr/local/sbin/usb-relay /usr/local/sbin/usb-relay
sudo install -Dm644 \
    systemd/system/usb-relay.service \
    systemd/system/usb-relay-sleep.service \
    -t /etc/systemd/system/

# RyzenAdj
sudo install -Dm755 scripts/usr/local/sbin/apply-ryzenadj-limits /usr/local/sbin/apply-ryzenadj-limits
sudo install -Dm644 \
    systemd/system/ryzenadj.service \
    systemd/system/ryzenadj-tdp.service \
    -t /etc/systemd/system/

# Bluetooth/USB controller wake
sudo install -Dm755 scripts/usr/local/sbin/xbox-controller-bluetooth-wake /usr/local/sbin/xbox-controller-bluetooth-wake
sudo install -Dm644 \
    systemd/system/xbox-controller-bluetooth-wake.service \
    systemd/system/xbox-controller-bluetooth-sleep.service \
    systemd/system/xbox-controller-bluetooth-reconnect.service \
    -t /etc/systemd/system/

# LACT daemon
sudo install -Dm644 systemd/system/lactd.service /etc/systemd/system/lactd.service

# PluginLoader
sudo install -Dm644 systemd/system/plugin_loader.service /etc/systemd/system/plugin_loader.service

# After all selected system units are installed
sudo systemctl daemon-reload
```

For each selected system feature, create its configuration only when absent. These commands deliberately preserve existing files:

```bash
sudo install -d -m755 /etc/steamos-scripts

if ! sudo test -e /etc/steamos-scripts/usb-relay.env; then
    sudo install -m644 scripts/etc/steamos-scripts/usb-relay.env.example /etc/steamos-scripts/usb-relay.env
fi
if ! sudo test -e /etc/steamos-scripts/ryzenadj.env; then
    sudo install -m644 scripts/etc/steamos-scripts/ryzenadj.env.example /etc/steamos-scripts/ryzenadj.env
fi
if ! sudo test -e /etc/steamos-scripts/controller-wake.env; then
    sudo install -m644 scripts/etc/steamos-scripts/controller-wake.env.example /etc/steamos-scripts/controller-wake.env
fi
if ! sudo test -e /etc/steamos-scripts/lactd.env; then
    sudo install -m644 scripts/etc/steamos-scripts/lactd.env.example /etc/steamos-scripts/lactd.env
fi
if ! sudo test -e /etc/steamos-scripts/plugin-loader.env; then
    sudo install -m644 scripts/etc/steamos-scripts/plugin-loader.env.example /etc/steamos-scripts/plugin-loader.env
fi
```

Only create the files needed by the selected features. Then edit those files and replace the relevant blank values with values confirmed by the user:

```bash
sudoedit /etc/steamos-scripts/usb-relay.env
sudoedit /etc/steamos-scripts/ryzenadj.env
sudoedit /etc/steamos-scripts/controller-wake.env
sudoedit /etc/steamos-scripts/lactd.env
sudoedit /etc/steamos-scripts/plugin-loader.env
```

For the relay, prefer `/dev/serial/by-id/...`; set `RELAY_DEVICE=auto` only after verifying the USB vendor and product IDs. RyzenAdj values are milliwatt and must be confirmed safe for the exact processor. An empty controller MAC is supported only when `bluetoothctl devices Paired` identifies the paired controller by an Xbox name.

Older versions used `/etc/usb-relay.conf`. If it exists, review and migrate its values into `/etc/steamos-scripts/usb-relay.env`; the current script intentionally does not read the legacy path.

Install the per-user OpenRGB script and unit as the desktop user (do not use `sudo` for these commands):

```bash
install -Dm755 scripts/home/user/.local/bin/ram-led-off "$HOME/.local/bin/ram-led-off"
install -Dm644 systemd/user/ram-led-off.service "$HOME/.config/systemd/user/ram-led-off.service"
systemctl --user daemon-reload
```

The generic `scripts/home/user` source path is only a template; the destination uses `$HOME`, and the unit's `%h` makes it portable to the current user.

## Preflight selected features

After installing files and editing configuration—but before enabling services—run preflight for exactly the selected features:

```bash
./scripts/preflight usb-relay
./scripts/preflight ryzenadj
./scripts/preflight controller-wake
./scripts/preflight ram-led
./scripts/preflight lactd
./scripts/preflight plugin-loader
```

Multiple feature names may be passed in one invocation. Run `ram-led` as the desktop user so it checks that user's Flatpak installation. Resolve every reported error before continuing. Hardware that is intentionally disconnected must be connected for preflight and the first start.

## Enable selected features

Enable only the features the user has reviewed and requested:

```bash
# USB relay
sudo systemctl enable usb-relay.service usb-relay-sleep.service

# RyzenAdj (only after its configured limits pass preflight)
sudo systemctl enable ryzenadj.service ryzenadj-tdp.service

# Bluetooth/USB controller wake
sudo systemctl enable xbox-controller-bluetooth-wake.service xbox-controller-bluetooth-sleep.service

# OpenRGB user-session action
systemctl --user enable ram-led-off.service

# Optional external integrations, only after their dependencies and paths work
sudo systemctl enable lactd.service
sudo systemctl enable plugin_loader.service
```

Start a service immediately only after its configuration is confirmed. For example:

```bash
sudo systemctl start usb-relay.service
systemctl --user start ram-led-off.service
```

Confirm the physical result after first start: relay state, retained controller wake, requested RyzenAdj values, RAM LEDs, or the external daemon's behavior. A running service alone is not proof that hardware configuration is correct.

## Verify and roll back

After enabling services, inspect the selected units' state and logs. Replace the example unit list with exactly the units selected during installation:

```bash
systemctl is-enabled usb-relay.service usb-relay-sleep.service
systemctl --user is-enabled ram-led-off.service  # only when RAM LED support was selected
sudo systemctl --failed
journalctl -b -u usb-relay.service -u usb-relay-sleep.service --no-pager
```

To turn off a feature without deleting its files, disable its unit(s), then reload systemd:

```bash
sudo systemctl disable --now usb-relay.service usb-relay-sleep.service
sudo systemctl daemon-reload
```

When all changes are complete, restore SteamOS's default protection:

```bash
sudo steamos-readonly enable
```

SteamOS updates may replace files under `/etc` and `/usr/local`; keep this repository available so the reviewed configuration can be reapplied.
