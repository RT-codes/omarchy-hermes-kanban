#!/usr/bin/env python3
"""Read-only, size-bounded Hermes Kanban snapshot worker."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
from typing import Any


SCHEMA_VERSION = 2
STATUS_ORDER = ("triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done")
DETAIL_STATUSES = frozenset(("ready", "running", "blocked", "review"))
BOARD_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_BOARDS = 100
MAX_SELECTED_BOARDS = 20
MAX_TASKS_PER_BOARD = 500
MAX_COMMAND_OUTPUT = 8 * 1024 * 1024
MAX_SNAPSHOT_OUTPUT = 2 * 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 12


class SnapshotError(RuntimeError):
    """Expected, user-safe collection failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def clean_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    return text[:limit]


def validate_hermes_path(value: Any) -> str:
    path = clean_text(value, 512)
    if not path or path != str(value):
        raise SnapshotError("configuration", "Hermes executable is invalid")
    if os.path.isabs(path):
        if "\x00" in path:
            raise SnapshotError("configuration", "Hermes executable is invalid")
        return path
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", path):
        raise SnapshotError("configuration", "Hermes executable name is invalid")
    return path


def validate_boards(values: Any) -> list[str]:
    if not isinstance(values, list) or len(values) > MAX_SELECTED_BOARDS:
        raise SnapshotError("configuration", "Too many selected boards")
    boards: list[str] = []
    seen: set[str] = set()
    for value in values:
        slug = str(value)
        if not BOARD_SLUG_RE.fullmatch(slug):
            raise SnapshotError("configuration", "Board selection is invalid")
        if slug not in seen:
            boards.append(slug)
            seen.add(slug)
    return boards


def run_capped(
    command: list[str],
    *,
    input_bytes: bytes | None = None,
    max_output: int = MAX_COMMAND_OUTPUT,
    timeout: float = COMMAND_TIMEOUT_SECONDS,
) -> tuple[int, str, str]:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SnapshotError("hermes-not-found", "Hermes executable was not found") from exc

    selector = selectors.DefaultSelector()
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    started = time.monotonic()

    try:
        if input_bytes is not None:
            assert process.stdin is not None
            process.stdin.write(input_bytes)
            process.stdin.close()
        while selector.get_map():
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                process.kill()
                process.wait()
                raise SnapshotError("hermes-timeout", "Hermes command timed out")
            for key, _ in selector.select(min(remaining, 0.25)):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                chunks[key.data].extend(data)
                if len(chunks["stdout"]) + len(chunks["stderr"]) > max_output:
                    process.kill()
                    process.wait()
                    raise SnapshotError("response-too-large", "Hermes returned too much data")
        return_code = process.wait()
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
        process.stderr.close()

    return (
        return_code,
        chunks["stdout"].decode("utf-8", errors="replace"),
        chunks["stderr"].decode("utf-8", errors="replace"),
    )


def run_json(hermes: str, args: list[str]) -> Any:
    return_code, stdout, _stderr = run_capped([hermes, *args])
    if return_code != 0:
        raise SnapshotError("hermes-failed", f"Hermes command exited {return_code}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SnapshotError("invalid-response", "Hermes returned invalid JSON") from exc


def normalized_counts(value: Any) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    counts: dict[str, int] = {}
    for status in STATUS_ORDER:
        raw = source.get(status, 0)
        counts[status] = max(0, int(raw)) if isinstance(raw, (int, float)) else 0
    return counts


def sanitize_board(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    slug = clean_text(value.get("slug"), 64)
    if not BOARD_SLUG_RE.fullmatch(slug):
        return None
    return {
        "slug": slug,
        "name": clean_text(value.get("name") or slug, 160),
        "is_current": value.get("is_current") is True,
        "counts": normalized_counts(value.get("counts")),
    }


def sanitize_task(value: Any, include_bodies: bool) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    status = clean_text(value.get("status"), 16)
    if status not in DETAIL_STATUSES:
        return None
    task_id = clean_text(value.get("id"), 128)
    if not task_id:
        return None
    priority = value.get("priority", 0)
    created_at = value.get("created_at", 0)
    started_at = value.get("started_at", 0)
    return {
        "id": task_id,
        "title": clean_text(value.get("title") or "Untitled task", 300),
        "body": clean_text(value.get("body"), 2000) if include_bodies else "",
        "assignee": clean_text(value.get("assignee"), 128),
        "status": status,
        "priority": priority if isinstance(priority, (int, float)) else 0,
        "created_at": created_at if isinstance(created_at, (int, float)) else 0,
        "started_at": started_at if isinstance(started_at, (int, float)) else 0,
    }


def sanitize_payload(value: Any, selected_boards: list[str], include_bodies: bool) -> dict[str, Any]:
    selected_boards = validate_boards(selected_boards)
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA_VERSION:
        raise SnapshotError("invalid-response", "Hermes snapshot schema is invalid")
    raw_boards = value.get("boards")
    raw_tasks_by_board = value.get("tasksByBoard")
    if not isinstance(raw_boards, list) or not isinstance(raw_tasks_by_board, dict):
        raise SnapshotError("invalid-response", "Hermes snapshot shape is invalid")
    boards: list[dict[str, Any]] = []
    for raw_board in raw_boards[:MAX_BOARDS]:
        board = sanitize_board(raw_board)
        if board is not None:
            boards.append(board)
    known_slugs = {board["slug"] for board in boards}
    if any(slug not in known_slugs for slug in selected_boards):
        raise SnapshotError("unknown-board", "A selected board is unavailable")
    tasks_by_board: dict[str, list[dict[str, Any]]] = {}
    for slug in selected_boards:
        raw_tasks = raw_tasks_by_board.get(slug, [])
        if not isinstance(raw_tasks, list):
            raise SnapshotError("invalid-response", "Hermes task list is invalid")
        tasks: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            task = sanitize_task(raw_task, include_bodies)
            if task is not None:
                tasks.append(task)
                if len(tasks) >= MAX_TASKS_PER_BOARD:
                    break
        tasks_by_board[slug] = tasks
    fetched_at = value.get("fetchedAt", 0)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "fetchedAt": fetched_at if isinstance(fetched_at, (int, float)) else 0,
        "boards": boards,
        "tasksByBoard": tasks_by_board,
    }


def snapshot(hermes: str, selected_boards: list[str], include_bodies: bool = False) -> dict[str, Any]:
    hermes = validate_hermes_path(hermes)
    selected_boards = validate_boards(selected_boards)
    raw_boards = run_json(hermes, ["kanban", "boards", "list", "--json"])
    if not isinstance(raw_boards, list):
        raise SnapshotError("invalid-response", "Hermes board catalog is invalid")

    boards: list[dict[str, Any]] = []
    for raw_board in raw_boards[:MAX_BOARDS]:
        board = sanitize_board(raw_board)
        if board is not None:
            boards.append(board)

    known_slugs = {board["slug"] for board in boards}
    if any(slug not in known_slugs for slug in selected_boards):
        raise SnapshotError("unknown-board", "A selected board is unavailable")

    tasks_by_board: dict[str, list[dict[str, Any]]] = {}
    for slug in selected_boards:
        raw_tasks = run_json(hermes, ["kanban", "--board", slug, "list", "--json"])
        if not isinstance(raw_tasks, list):
            raise SnapshotError("invalid-response", "Hermes task list is invalid")
        tasks: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            task = sanitize_task(raw_task, include_bodies)
            if task is not None:
                tasks.append(task)
                if len(tasks) >= MAX_TASKS_PER_BOARD:
                    break
        tasks_by_board[slug] = tasks

    payload = sanitize_payload({
        "schemaVersion": SCHEMA_VERSION,
        "fetchedAt": int(time.time()),
        "boards": boards,
        "tasksByBoard": tasks_by_board,
    }, selected_boards, include_bodies)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_SNAPSHOT_OUTPUT:
        raise SnapshotError("response-too-large", "Hermes snapshot is too large")
    return payload


def decode_request(encoded: str) -> dict[str, Any]:
    if not encoded or len(encoded) > 16384 or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", encoded):
        raise SnapshotError("configuration", "Snapshot request is invalid")
    try:
        padding = "=" * (-len(encoded) % 4)
        value = json.loads(base64.urlsafe_b64decode(encoded + padding))
    except (ValueError, json.JSONDecodeError) as exc:
        raise SnapshotError("configuration", "Snapshot request is invalid") from exc
    if not isinstance(value, dict):
        raise SnapshotError("configuration", "Snapshot request is invalid")
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("HERMES_KANBAN_ERROR:configuration:Snapshot request is missing", file=sys.stderr)
        return 12
    try:
        request = decode_request(argv[1])
        payload = snapshot(
            request.get("hermesPath", "hermes"),
            request.get("boards", []),
            request.get("includeTaskBodies") is True,
        )
    except SnapshotError as exc:
        print(f"HERMES_KANBAN_ERROR:{exc.code}:{exc}", file=sys.stderr)
        return 11
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
