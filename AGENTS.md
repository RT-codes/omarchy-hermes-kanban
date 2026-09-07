# AGENTS.md

## Project

This repository is an Omarchy Quattro bar plugin for monitoring Hermes Kanban work and scheduled jobs, with bounded local edit helpers for human-managed work notes.

## Working rules

- Keep Local mode as the default. Remote mode remains read-only and must use the user's existing OpenSSH configuration with strict host-key checking and non-interactive public-key authentication.
- Treat Hermes output and remote stderr as untrusted. Bound, validate, normalize, and allowlist data before rendering it.
- Never expose raw stderr, credentials, private-key paths, host details, or task bodies. Task bodies remain opt-in in snapshots.
- Local write actions must stay narrow and explicit. Human-managed Obsidian notes may sync cron prompt/schedule/enabled/skills and Kanban title/body only; runtime state remains Hermes-owned.
- Prefer Hermes' supported CLI/API mutation paths when available. Cron note sync uses `hermes cron edit/pause/resume`; do not directly mutate cron runtime bookkeeping.
- Kanban note sync may update title/body only, transactionally, and must record an `edited` event. Never let the note watcher mutate status, assignee, claims, runs, dependencies, worker state, or results.
- Do not add credential management, privilege escalation, destructive task/cron controls, or SSH configuration changes through the note layer.
- Keep snapshots in memory. Persist only board selection, bounded local backups/state, and human-managed Markdown notes under the configured Obsidian vault.
- Do not add runtime dependencies without a clear need. Helpers should remain Python standard-library + existing Omarchy/Hermes commands.
- Treat `/usr/share/omarchy/` as read-only reference material. Never modify installed Omarchy files while developing this plugin.

## Code map

- `BarWidget.qml`, `Panel.qml`, and `StatusIcon.qml`: UI.
- `SnapshotStore.qml` and `Model.js`: state and presentation model.
- `bin/hermes-kanban-snapshot` + `bin/snapshot_worker.py`: bounded local/SSH snapshot transport.
- `bin/hermes-work-note.py`: bootstrap/open human-managed Obsidian work notes.
- `bin/hermes-work-sync.py`: apply validated note changes back to Hermes.
- `bin/hermes-work-watch-install`: install the lightweight user timer that scans for note changes.
- `tests/`: Python, shell, asset, transport, and QML tests.

## Verification

Run before handing off changes:

```bash
./tests/run.sh
omarchy plugin validate .
qmllint -I /usr/lib/qt6/qml -I /usr/share/omarchy/shell \
  BarWidget.qml Panel.qml SnapshotStore.qml StatusIcon.qml tests/tst_Model.qml
```

Update `README.md`, `CHANGELOG.md`, and `manifest.json` when behavior or release metadata changes.
