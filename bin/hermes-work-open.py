#!/usr/bin/env python3
"""Open local Hermes work items in Obsidian or a floating Nvim editor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any
from urllib.parse import quote

BOARD_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
MAX_JSON_BYTES = 8 * 1024 * 1024
TASK_TITLE_PREFIX = "TITLE: "
TASK_BODY_MARKER = "\n## BODY\n"
DEFAULT_VAULT = Path.home() / "Documents" / "Hermes-Memory"
STATE_ROOT = Path.home() / ".local" / "state" / "omarchy" / "hermes-work"


class WorkOpenError(RuntimeError):
    pass


def clean(value: Any, limit: int = 6000) -> str:
    text = "" if value is None else str(value)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)[:limit]


def validate_board(value: str) -> str:
    if not BOARD_RE.fullmatch(value):
        raise WorkOpenError("invalid board")
    return value


def validate_profile(value: str) -> str:
    if not PROFILE_RE.fullmatch(value):
        raise WorkOpenError("invalid profile")
    return value


def validate_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise WorkOpenError("invalid item id")
    return value


def validate_hermes(value: str) -> str:
    value = str(value or "hermes")
    if Path(value).is_absolute():
        if "\x00" in value:
            raise WorkOpenError("invalid Hermes executable")
        return value
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise WorkOpenError("invalid Hermes executable")
    return value


def run_json(command: list[str]) -> Any:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkOpenError(f"command failed: {command[0]}") from exc
    if result.returncode != 0:
        raise WorkOpenError(f"Hermes command exited {result.returncode}")
    if len(result.stdout.encode("utf-8", errors="replace")) > MAX_JSON_BYTES:
        raise WorkOpenError("Hermes response is too large")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkOpenError("Hermes returned invalid JSON") from exc


def profile_home(profile: str) -> Path:
    profile = validate_profile(profile)
    root = Path.home() / ".hermes"
    return root if profile == "default" else root / "profiles" / profile


def cron_path(profile: str) -> Path:
    path = profile_home(profile) / "cron" / "jobs.json"
    if not path.is_file():
        raise WorkOpenError(f"cron store not found for profile {profile}")
    return path


def load_cron_store(profile: str) -> tuple[Path, Any, list[dict[str, Any]]]:
    path = cron_path(profile)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise WorkOpenError("cron store is too large")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkOpenError("cron store is invalid JSON") from exc
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
    if not isinstance(jobs, list):
        raise WorkOpenError("cron store has an invalid shape")
    return path, raw, [job for job in jobs if isinstance(job, dict)]


def find_cron_job(profile: str, job_id: str) -> tuple[Path, dict[str, Any]]:
    job_id = validate_id(job_id)
    path, _raw, jobs = load_cron_store(profile)
    for job in jobs:
        if str(job.get("id") or "") == job_id:
            return path, job
    raise WorkOpenError(f"cron job {job_id} not found")


def cron_line(path: Path, job_id: str) -> int:
    patterns = (f'"id": "{job_id}"', f'"id":"{job_id}"', job_id)
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if any(pattern in line for pattern in patterns):
                return number
    except OSError:
        pass
    return 1


def hermes_task_show(hermes: str, board: str, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    board = validate_board(board)
    task_id = validate_id(task_id)
    raw = run_json([hermes, "kanban", "--board", board, "show", task_id, "--json"])
    if not isinstance(raw, dict):
        raise WorkOpenError("Hermes task response has an invalid shape")
    task = raw.get("task") if isinstance(raw.get("task"), dict) else raw
    if str(task.get("id") or "") != task_id:
        raise WorkOpenError(f"task {task_id} not found")
    return raw, task


def board_db_path(hermes: str, board: str) -> Path:
    board = validate_board(board)
    raw = run_json([hermes, "kanban", "boards", "list", "--json"])
    if not isinstance(raw, list):
        raise WorkOpenError("Hermes board catalog has an invalid shape")
    for item in raw:
        if isinstance(item, dict) and str(item.get("slug") or "") == board:
            candidate = item.get("db_path")
            if candidate:
                path = Path(str(candidate)).expanduser()
                if path.is_file():
                    return path.resolve()
            break
    root = Path.home() / ".hermes"
    path = root / "kanban.db" if board == "default" else root / "kanban" / "boards" / board / "kanban.db"
    if not path.is_file():
        raise WorkOpenError(f"Kanban database not found for board {board}")
    return path.resolve()


def safe_note_path(vault: Path, kind: str, scope: str, item_id: str) -> Path:
    vault = vault.expanduser().resolve()
    subdir = "Cron" if kind == "cron" else "Tasks"
    path = vault / "90 Hermes Control" / "Work Console" / subdir / f"{scope} - {item_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def markdown_scalar(value: Any) -> str:
    return clean(value, 4000).replace("\r", "")


def write_cron_reference(vault: Path, profile: str, job_id: str) -> Path:
    source, job = find_cron_job(profile, job_id)
    note = safe_note_path(vault, "cron", profile, job_id)
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        schedule = schedule.get("display") or schedule.get("expr") or json.dumps(schedule, ensure_ascii=False)
    skills = job.get("skills") or job.get("skill") or []
    if isinstance(skills, str):
        skills = [skills]
    prompt = markdown_scalar(job.get("prompt"))
    content = f"""# {markdown_scalar(job.get('name') or job_id)}

> Hermes Work reference. The canonical cron record lives inside `{source}`.
> Use the **Nvim** button in Hermes Work to edit the original JSON record safely with backup + validation.

- **Kind:** cron
- **Profile:** `{profile}`
- **Job ID:** `{job_id}`
- **State:** {markdown_scalar(job.get('state') or ('scheduled' if job.get('enabled', True) else 'paused'))}
- **Enabled:** {bool(job.get('enabled', True))}
- **Schedule:** {markdown_scalar(schedule)}
- **Next run:** {markdown_scalar(job.get('next_run_at'))}
- **Last run:** {markdown_scalar(job.get('last_run_at'))}
- **Skills:** {', '.join(markdown_scalar(x) for x in skills)}
- **Source:** `{source}`

## Prompt

{prompt or '_No prompt._'}
"""
    note.write_text(content, encoding="utf-8")
    return note


def write_task_reference(vault: Path, hermes: str, board: str, task_id: str) -> Path:
    raw, task = hermes_task_show(hermes, board, task_id)
    db = board_db_path(hermes, board)
    note = safe_note_path(vault, "task", board, task_id)
    body = markdown_scalar(task.get("body"))
    result = markdown_scalar(task.get("result") or task.get("latest_summary") or raw.get("latest_summary"))
    content = f"""# {markdown_scalar(task.get('title') or task_id)}

> Hermes Work reference. This task is a row in Hermes' SQLite Kanban database, not a standalone file.
> Use the **Nvim** button in Hermes Work to edit the task title/body; the editor writes them back transactionally and records an `edited` event.

- **Kind:** Kanban task
- **Board:** `{board}`
- **Task ID:** `{task_id}`
- **Status:** {markdown_scalar(task.get('status'))}
- **Assignee:** {markdown_scalar(task.get('assignee') or 'unassigned')}
- **Priority:** {task.get('priority', 0)}
- **Database:** `{db}`

## Body

{body or '_No body._'}

## Result / latest summary

{result or '_No result yet._'}
"""
    note.write_text(content, encoding="utf-8")
    return note


def open_obsidian(note: Path) -> None:
    uri = "obsidian://open?path=" + quote(str(note.resolve()), safe="")
    try:
        subprocess.Popen(
            ["xdg-open", uri], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError as exc:
        raise WorkOpenError("could not launch Obsidian") from exc


def backup_path(kind: str, scope: str, item_id: str, suffix: str) -> Path:
    target = STATE_ROOT / "backups" / kind
    target.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return target / f"{scope}-{item_id}-{stamp}{suffix}"


def launch_floating_session(args: list[str]) -> None:
    helper = Path(__file__).resolve()
    command = shlex.join([sys.executable, str(helper), *args])
    try:
        subprocess.Popen(
            ["omarchy-launch-floating-terminal-with-presentation", command],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise WorkOpenError("could not launch Omarchy floating terminal") from exc


def render_task_editor(task: dict[str, Any], board: str, task_id: str) -> str:
    title = clean(task.get("title") or "", 1000).replace("\n", " ").strip()
    body = clean(task.get("body") or "", 100_000).replace("\r", "")
    return f"""# Hermes Kanban Task Editor

> Save and quit Nvim to apply **TITLE** and **BODY** to Hermes.
> Status/assignee/priority below are reference-only in this editor.

{TASK_TITLE_PREFIX}{title}

- ID: `{task_id}`
- Board: `{board}`
- Status: {clean(task.get('status'), 64)}
- Assignee: {clean(task.get('assignee') or 'unassigned', 128)}
- Priority: {task.get('priority', 0)}
{TASK_BODY_MARKER}{body}
"""


def parse_task_editor(text: str) -> tuple[str, str]:
    title = None
    for line in text.splitlines():
        if line.startswith(TASK_TITLE_PREFIX):
            title = line[len(TASK_TITLE_PREFIX):].strip()
            break
    if not title:
        raise WorkOpenError("TITLE cannot be empty")
    if TASK_BODY_MARKER not in text:
        raise WorkOpenError("BODY marker is missing")
    body = text.split(TASK_BODY_MARKER, 1)[1]
    return title, body


def task_editor_path(board: str, task_id: str) -> Path:
    target = STATE_ROOT / "editors" / "tasks" / board
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{task_id}.md"


def sqlite_backup(db_path: Path, board: str, task_id: str) -> Path:
    backup = backup_path("tasks", board, task_id, ".db")
    source = sqlite3.connect(str(db_path), timeout=5)
    dest = sqlite3.connect(str(backup))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return backup


def apply_task_text(db_path: Path, task_id: str, original_title: str, original_body: str,
                    title: str, body: str) -> list[str]:
    changed: list[str] = []
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT title, body FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise WorkOpenError(f"task {task_id} no longer exists")
        current_title = str(row["title"] or "")
        current_body = str(row["body"] or "")
        if current_title != original_title or current_body != original_body:
            raise WorkOpenError("task changed in Hermes while the editor was open; refusing to overwrite it")
        sets: list[str] = []
        values: list[Any] = []
        if title != original_title:
            sets.append("title = ?")
            values.append(title.strip())
            changed.append("title")
        if body != original_body:
            sets.append("body = ?")
            values.append(body)
            changed.append("body")
        if sets:
            values.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
            conn.execute(
                "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'edited', NULL, ?)",
                (task_id, int(time.time())),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return changed


def edit_task_session(hermes: str, board: str, task_id: str) -> None:
    _raw, task = hermes_task_show(hermes, board, task_id)
    db = board_db_path(hermes, board)
    original_title = str(task.get("title") or "")
    original_body = str(task.get("body") or "")
    editor = task_editor_path(board, task_id)
    editor.write_text(render_task_editor(task, board, task_id), encoding="utf-8")
    result = subprocess.run(["nvim", str(editor)], check=False)
    if result.returncode not in (0, 130):
        raise WorkOpenError(f"Nvim exited {result.returncode}")
    if result.returncode == 130:
        print("Edit cancelled.")
        return
    title, body = parse_task_editor(editor.read_text(encoding="utf-8"))
    if title == original_title and body == original_body:
        print("No task changes to apply.")
        return
    backup = sqlite_backup(db, board, task_id)
    changed = apply_task_text(db, task_id, original_title, original_body, title, body)
    if changed:
        print(f"Updated {task_id}: {', '.join(changed)}")
        print(f"Backup: {backup}")
    else:
        print("No task changes to apply.")


def validate_cron_after_edit(path: Path, profile: str, job_id: str) -> None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkOpenError("saved cron file is not valid JSON") from exc
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
    if not isinstance(jobs, list):
        raise WorkOpenError("saved cron file does not contain a jobs list")
    if not any(isinstance(job, dict) and str(job.get("id") or "") == job_id for job in jobs):
        raise WorkOpenError("the edited cron job disappeared from jobs.json; use Hermes lifecycle controls to remove jobs")


def edit_cron_session(profile: str, job_id: str) -> None:
    source, _job = find_cron_job(profile, job_id)
    before = source.read_bytes()
    digest = hashlib.sha256(before).hexdigest()
    backup = backup_path("cron", profile, job_id, ".json")
    shutil.copy2(source, backup)
    line = cron_line(source, job_id)
    result = subprocess.run(["nvim", f"+{line}", str(source)], check=False)
    if result.returncode not in (0, 130):
        raise WorkOpenError(f"Nvim exited {result.returncode}")
    if result.returncode == 130:
        print("Edit cancelled.")
        return
    after = source.read_bytes()
    if hashlib.sha256(after).hexdigest() == digest:
        print("No cron changes to validate.")
        return
    try:
        validate_cron_after_edit(source, profile, job_id)
    except WorkOpenError:
        shutil.copy2(backup, source)
        print(f"Invalid cron edit; restored {backup}", file=sys.stderr)
        raise
    print(f"Cron JSON valid for {profile}/{job_id}.")
    print(f"Backup: {backup}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="hermes-work-open")
    parser.add_argument("action", choices=("obsidian", "nvim", "_edit-task", "_edit-cron"))
    parser.add_argument("kind", choices=("task", "cron"))
    parser.add_argument("scope")
    parser.add_argument("item_id")
    parser.add_argument("--hermes", default="hermes")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv[1:])
        hermes = validate_hermes(args.hermes)
        item_id = validate_id(args.item_id)
        scope = validate_board(args.scope) if args.kind == "task" else validate_profile(args.scope)

        if args.action == "obsidian":
            vault = Path(args.vault).expanduser()
            note = (write_task_reference(vault, hermes, scope, item_id)
                    if args.kind == "task" else write_cron_reference(vault, scope, item_id))
            open_obsidian(note)
            return 0

        if args.action == "nvim":
            launch_floating_session([
                "_edit-task" if args.kind == "task" else "_edit-cron",
                args.kind, scope, item_id, "--hermes", hermes, "--vault", args.vault,
            ])
            return 0

        if args.action == "_edit-task" and args.kind == "task":
            edit_task_session(hermes, scope, item_id)
            return 0
        if args.action == "_edit-cron" and args.kind == "cron":
            edit_cron_session(scope, item_id)
            return 0
        raise WorkOpenError("action/kind mismatch")
    except WorkOpenError as exc:
        print(f"Hermes Work: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
