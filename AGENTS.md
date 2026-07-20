# Agent instructions

For installation, deployment, enablement, or hardware-validation requests, follow the **Agent installation contract** in `README.md` exactly.

- Work only on features the user explicitly selects.
- Confirm machine-specific configuration before installing or enabling a feature.
- Never overwrite an existing file under `/etc/steamos-scripts` without showing the diff and receiving explicit approval.
- Run `scripts/preflight` for every selected feature and resolve all errors before enabling it.
- Never enable `xbox-controller-bluetooth-reconnect.service`.
- Obtain approval before changing SteamOS read-only state, writing system files, or enabling/starting services.
- Verify the selected units, logs, and physical hardware behavior, then restore the read-only root filesystem.

For repository changes, run shell syntax checks, `systemd-analyze verify` on changed units, `git diff --check`, and a scan for personal or machine-identifying values before handing off.
