# Hermes Kanban for Omarchy

A read-only Omarchy bar plugin for monitoring selected Hermes Kanban boards on a remote host.

The widget shows aggregate running and blocked state. Its panel lets you select multiple boards, inspect the Hermes status funnel, and expand running, blocked, review, and ready tasks. It refreshes through the Hermes CLI over SSH; it does not use dashboard cookies or issue mutating commands.

## Requirements

- Omarchy 4 with `omarchy-shell`
- `ssh`, `python3`, and `timeout` locally
- Non-interactive SSH public-key access to the remote Hermes host
- Hermes 0.20 or newer on the remote host

The default host is `ssh-ninalyx`. Verify it before installing:

```bash
ssh -F ~/.ssh/config -o BatchMode=yes ssh-ninalyx 'hermes version'
```

If Hermes is not on the non-interactive PATH, set the widget's **Remote Hermes executable** to its absolute path.

## Install

Commit this repository, then install its local Git URL:

```bash
omarchy plugin add file:///home/perro/dev/omarchy-hermes-kanban --enable --yes
```

The plugin is added to the right bar section. Move it with `omarchy bar move perro.hermes-kanban --section right` if needed.

To update the installed clone after committing local changes:

```bash
omarchy plugin update perro.hermes-kanban --yes
```

## Controls

- Left click: open or close the progress dashboard
- Middle/right click: refresh
- `R` while open: refresh
- `O` while open: launch Hermes Desktop
- Board picker: select any number of boards; the choice persists locally
- Task row: expand details and copy the task ID

Selection state is stored at `~/.local/state/omarchy/hermes-kanban.json`. Task snapshots are retained only in memory so remote task content is not cached to disk.

## Security

The helper validates its SSH alias, Hermes executable path, and board slugs before connecting. Each refresh uses one bounded SSH session with `BatchMode=yes` and strict host-key checking. The remote program invokes only:

```text
hermes kanban boards list --json
hermes kanban --board <slug> list --json
```

No password, private key, dashboard token, or OAuth cookie is stored by the plugin.

## Test

```bash
tests/run.sh
omarchy plugin validate .
qmllint -I /home/perro/.local/share/omarchy/shell BarWidget.qml Panel.qml
```
