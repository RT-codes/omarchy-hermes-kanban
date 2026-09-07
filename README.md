# Hermes Kanban for Omarchy

A read-only Omarchy Quattro bar widget for monitoring Hermes work: selected Kanban boards plus scheduled Hermes cron jobs. Hermes may run locally or on a remote host reached through an existing OpenSSH configuration.

This fork preserves the original plugin's compact Omarchy styling and read-only safety model while extending the panel into a small **Hermes Work** console.

![Hermes Kanban panel with sanitized fixture data](preview.png)

The panel shows aggregate workflow counts and the running, blocked, review, and ready tasks for any number of selected boards. Below the board sections it shows scheduled cron jobs, including their real prompt/instruction, schedule, state, next/last run, skills, delivery/workdir, and recent failure state. Local mode is the safe default. Task bodies remain excluded unless explicitly enabled.

Board summaries use bundled, theme-colored [Tabler Icons](assets/tabler/README.md) for each Hermes status, so they remain legible without relying on a particular Nerd Font. Hover an icon to see its full status label and count.

## Requirements

- Omarchy Quattro with `omarchy-shell`
- Hermes Agent 0.20 or newer on the selected host
- Python 3 locally and, for Remote mode, on the remote host
- OpenSSH client and non-interactive public-key authentication for Remote mode

The plugin uses only Python's standard library. It does not install packages, create services, request privileges, or manage SSH keys.

## Fork development workflow

The editable source checkout lives in your Projects folder:

```text
~/Projects/omarchy-hermes-kanban
```

Omarchy runs its own installed checkout under:

```text
~/.config/omarchy/plugins/io.github.davidojedalopez.hermes-kanban
```

**Edit, commit, pull, and push only in `~/Projects/omarchy-hermes-kanban`.** Treat the copy under `~/.config/omarchy/plugins/` as Omarchy-managed runtime state.

For this fork the normal flow is:

```bash
cd ~/Projects/omarchy-hermes-kanban
git pull
# edit / test / commit / push
omarchy plugin update io.github.davidojedalopez.hermes-kanban
```

## Install

For Rowan's fork:

```bash
omarchy plugin add https://github.com/RT-codes/omarchy-hermes-kanban.git --enable
```

Original upstream:

```text
https://github.com/davidojedalopez/omarchy-hermes-kanban
```

The permanent plugin ID remains `io.github.davidojedalopez.hermes-kanban` for compatibility with Omarchy's installed-plugin identity.

## Configure

Open Omarchy's bar settings and configure the Hermes Work widget:

- **Hermes host:** `Local` or `Remote`; defaults to `Local`.
- **Hermes executable:** `hermes` or an absolute executable path on the selected host.
- **Remote SSH host:** an OpenSSH host or alias, used only in Remote mode.
- **Show task bodies:** off by default to minimize task content entering the shell.
- **Refresh intervals:** 15 seconds while open and 120 seconds in the background by default.

Board selection is available inside the panel and is stored separately for each local or remote endpoint.

### Scheduled jobs

Hermes currently does not provide a reliable JSON form of `hermes cron list`, so the snapshot helper reads Hermes' own profile-local cron store read-only (`~/.hermes/cron/jobs.json` for the default profile), then allowlists and sanitizes the fields rendered in the panel.

Cron jobs are never edited by this version of the plugin. The Scheduled section can show:

- job name and ID
- schedule and lifecycle state
- next and last run
- last run status/error
- full bounded prompt/instruction
- attached skills
- delivery target
- work directory
- model/provider/script metadata when explicitly pinned

## Controls

- Left click: open or close the Hermes Work panel
- Middle or right click: refresh
- `R` while open: refresh
- `O` while open: launch the local Hermes Desktop application
- Task row: expand task details and copy the task ID
- Scheduled row: expand cron details and copy the cron job ID

Selection state is stored at `~/.local/state/omarchy/hermes-kanban.json`. Work snapshots stay in memory and are not written to disk.

## Security model

Omarchy plugins run unsandboxed with the current user's permissions. This plugin narrows its runtime behavior as follows:

- Executes only Hermes' read-only Kanban JSON commands.
- Reads Hermes' cron jobs file read-only; it does not edit `jobs.json`.
- Invokes Hermes without a local shell.
- Encodes Remote-mode request data before it reaches the remote login shell.
- Requires strict host-key checking and public-key, non-interactive SSH authentication.
- Disables TTYs, passwords, keyboard-interactive authentication, agent/X11/port forwarding, local commands, and SSH connection sharing.
- Allowlists board, task, and cron fields; removes control characters; and caps inputs, strings, tasks/jobs, command output, and final snapshots.
- Renders Hermes-derived strings as plain text.
- Converts command failures into stable messages instead of showing raw remote stderr.
- Keeps task bodies opt-in.

The configured OpenSSH host entry remains trusted user configuration. It may intentionally contain a `ProxyJump` or `ProxyCommand`; review it before allowing an unsandboxed plugin to use it. See [SECURITY.md](SECURITY.md) for reporting and trust boundaries.

## Remove

```bash
omarchy plugin remove io.github.davidojedalopez.hermes-kanban
```

Removing the plugin does not delete its board-selection state. Remove it separately if desired:

```bash
gio trash ~/.local/state/omarchy/hermes-kanban.json
```

## Development

```bash
./tests/run.sh
omarchy plugin validate .
qmllint -I /usr/lib/qt6/qml -I /usr/share/omarchy/shell \
  BarWidget.qml Panel.qml SnapshotStore.qml StatusIcon.qml tests/tst_Model.qml
```

The test suite covers local and remote transports, exact SSH guardrails, schema/state handling, cron sanitization, data minimization, command validation, and the QML presentation model.
