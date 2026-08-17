# Changelog

## 1.1.2

- Give Blocked a dedicated red palette instead of inheriting a theme's generic urgent color.
- Select the red variant with stronger contrast against the active popup surface.
- Add a tinted status cell, border, and task-row edge marker for non-color-only emphasis.

## 1.1.1

- Make the status asset guardrail pass ShellCheck in GitHub Actions.

## 1.1.0

- Replace abbreviated status captions with bundled Tabler SVG icons.
- Add status-and-count tooltips and accessible names to board summary cells.
- Animate the running icon when a board has active work.

## 1.0.2

- Make the bundled test runner work from checkout paths containing dots.

## 1.0.1

- Make the transport guardrail test portable to clean Ubuntu CI runners.

## 1.0.0

- Add local and remote Hermes modes with Local as the default.
- Support multiple selected boards with per-endpoint selection state.
- Harden SSH transport and encode remote request arguments.
- Minimize board and task data, disable task bodies by default, and enforce size limits.
- Share one in-memory snapshot process across monitor instances.
- Adopt the permanent marketplace plugin ID.
