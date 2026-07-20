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

## Codex skill workflow

The directories under `skills/` are the source of truth for the installable Codex skills. Do not maintain a separate edited copy under `~/.codex/skills`.

- Confirm exactly which skill or skills the user wants before installing them.
- Run `./scripts/validate-codex-skills` before installation and after every skill change. Its checks include Python syntax and a scan for common personal or machine-identifying values.
- Check the destination with `./scripts/manage-codex-skills status SKILL...`, then install with `./scripts/manage-codex-skills install SKILL...`. The installer creates repository-backed links and must never replace an existing destination.
- If a destination conflicts, show the user the reported `diff -ru` before asking whether to migrate or remove it. Never replace it without explicit approval.
- Update skill files in this repository. Because managed installations are links, the installed skill immediately reflects the tracked source.
- Before handing off an update, run the repository checks, inspect `git status` and `git diff`, and confirm that only intended portable values are present.
- Commit and push skill updates only when the user requests publication. Commit the source under `skills/` and related installer or documentation changes, verify the branch's upstream with `git branch -vv`, then use `git push`. If the branch has no upstream, ask before creating one with `git push --set-upstream origin HEAD`.
