# AGENTS.md

## Project

This repository is an Omarchy Quattro bar plugin. It provides a read-only view of selected local or remote Hermes Kanban boards.

## Working rules

- Preserve the read-only design. Do not add task mutation, credential management, privilege escalation, or SSH configuration changes.
- Keep Local mode as the default. Remote mode must use the user's existing OpenSSH configuration with strict host-key checking and non-interactive public-key authentication.
- Treat Hermes output and remote stderr as untrusted. Bound, validate, normalize, and allowlist data before rendering it.
- Never expose raw stderr, credentials, private-key paths, host details, or task bodies. Task bodies remain opt-in.
- Keep snapshots in memory. The only persisted plugin data is board selection under the user's XDG state directory.
- Do not add runtime dependencies without a clear need. The current helpers use Python's standard library.
- Treat `/usr/share/omarchy/` as read-only reference material. Never modify installed Omarchy files while developing this plugin.

## Code map

- `BarWidget.qml`, `Panel.qml`, and `StatusIcon.qml`: UI.
- `SnapshotStore.qml` and `Model.js`: state and presentation model.
- `bin/`: local and SSH snapshot transport.
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
