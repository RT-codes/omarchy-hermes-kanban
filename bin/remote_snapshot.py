#!/usr/bin/env python3
"""Produce one read-only Hermes Kanban snapshot for the Omarchy plugin."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any


TASK_FIELDS = (
    "id",
    "title",
    "body",
    "assignee",
    "status",
    "priority",
    "created_at",
    "started_at",
)


def run_json(hermes: str, args: list[str]) -> Any:
    try:
        completed = subprocess.run(
            [hermes, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Hermes executable not found: {hermes}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Hermes command timed out: {' '.join(args)}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"Hermes command failed ({completed.returncode}): {detail[:400]}")

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Hermes emitted invalid JSON") from exc


def snapshot(hermes: str, selected_boards: list[str]) -> dict[str, Any]:
    boards = run_json(hermes, ["kanban", "boards", "list", "--json"])
    if not isinstance(boards, list):
        raise RuntimeError("Hermes board catalog was not a JSON array")

    tasks_by_board: dict[str, list[dict[str, Any]]] = {}
    for slug in selected_boards:
        tasks = run_json(hermes, ["kanban", "--board", slug, "list", "--json"])
        if not isinstance(tasks, list):
            raise RuntimeError(f"Hermes task list for {slug!r} was not a JSON array")
        tasks_by_board[slug] = [
            {field: task.get(field) for field in TASK_FIELDS}
            for task in tasks
            if isinstance(task, dict)
        ]

    return {
        "schemaVersion": 1,
        "fetchedAt": int(time.time()),
        "boards": boards,
        "tasksByBoard": tasks_by_board,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("remote_snapshot.py: expected HERMES_PATH [BOARD ...]", file=sys.stderr)
        return 2
    try:
        payload = snapshot(argv[1], argv[2:])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 11
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
