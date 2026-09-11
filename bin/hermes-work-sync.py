#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from typing import Any

VAULT = Path(os.environ.get("HERMES_WORK_VAULT", "~/Documents/Hermes-Memory")).expanduser()
CONTROL = VAULT / "90 Hermes Control"
CRON_ROOT = CONTROL / "Scheduled Jobs"
KANBAN_ROOT = CONTROL / "Kanban"
HERMES = os.environ.get("HERMES_WORK_HERMES", "hermes")

class SyncError(RuntimeError):
    pass

def run(cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(cmd, text=True, capture_output=True, env=env, check=False)
    if p.returncode != 0:
        raise SyncError((p.stderr or p.stdout or "command failed").strip())
    return p

def profile_home(profile: str) -> Path:
    root = Path.home() / ".hermes"
    return root if profile == "default" else root / "profiles" / profile

def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise SyncError("missing YAML-style frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise SyncError("unterminated frontmatter")
    head = text[4:end]
    body = text[end + 5:]
    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw in head.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_list:
            data.setdefault(current_list, []).append(line[4:].strip().strip('"\''))
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            raise SyncError(f"unsupported frontmatter line: {line}")
        key, value = m.group(1), m.group(2).strip()
        current_list = None
        if value == "":
            data[key] = []
            current_list = key
        elif value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
        else:
            data[key] = value.strip('"\'')
    return data, body

def section(text: str, heading: str) -> str:
    """Return one Markdown section while preserving nested subsections.

    A level-1 section ends only at the next level-1 heading, so content such
    as ``# Body`` may safely contain ``##`` subsections. A level-2 section
    ends at the next level-1 or level-2 heading.
    """
    marker = f"# {heading}\n"
    pos = text.find(marker)
    level = 1

    if pos < 0:
        marker = f"## {heading}\n"
        pos = text.find(marker)
        level = 2

    if pos < 0:
        return ""

    start = pos + len(marker)
    rest = text[start:]

    if level == 1:
        boundary = re.search(r"\n#\s+", rest)
    else:
        boundary = re.search(r"\n#{1,2}\s+", rest)

    return (rest[:boundary.start()] if boundary else rest).strip()

def cron_store(profile: str) -> tuple[Path, dict[str, Any]]:
    path = profile_home(profile) / "cron" / "jobs.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
    if not isinstance(jobs, list):
        raise SyncError("invalid cron store")
    return path, {str(j.get("id")): j for j in jobs if isinstance(j, dict) and j.get("id")}

def cron_display_schedule(job: dict[str, Any]) -> str:
    s = job.get("schedule")
    if isinstance(s, str):
        return s
    if isinstance(s, dict):
        return str(s.get("display") or s.get("expr") or s.get("value") or "")
    return ""

def sync_cron(path: Path) -> str:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    profile = str(meta.get("profile") or "default")
    job_id = str(meta.get("job_id") or "")
    schedule = str(meta.get("schedule") or "").strip()
    enabled = bool(meta.get("enabled", True))
    skills = meta.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    prompt = section(body, "Prompt")
    if not job_id or not schedule or not prompt:
        raise SyncError("cron file needs job_id, schedule and # Prompt")
    _store, jobs = cron_store(profile)
    live = jobs.get(job_id)
    if not live:
        raise SyncError(f"cron job {job_id} not found in profile {profile}")
    env = os.environ.copy()
    env["HERMES_HOME"] = str(profile_home(profile))
    cmd = [HERMES, "cron", "edit", job_id]
    if cron_display_schedule(live) != schedule:
        cmd += ["--schedule", schedule]
    if str(live.get("prompt") or "") != prompt:
        cmd += ["--prompt", prompt]
    live_skills = live.get("skills") or live.get("skill") or []
    if isinstance(live_skills, str):
        live_skills = [live_skills]
    if list(live_skills) != list(skills):
        if skills:
            for skill in skills:
                cmd += ["--skill", str(skill)]
        else:
            cmd += ["--clear-skills"]
    if len(cmd) > 4:
        run(cmd, env=env)
    live_enabled = live.get("enabled", True) is not False and str(live.get("state") or "") != "paused"
    if enabled != live_enabled:
        run([HERMES, "cron", "resume" if enabled else "pause", job_id], env=env)
    return f"cron {profile}/{job_id} synced"

def board_db(board: str) -> Path:
    root = Path.home() / ".hermes"
    path = root / "kanban.db" if board == "default" else root / "kanban" / "boards" / board / "kanban.db"
    if not path.is_file():
        raise SyncError(f"Kanban DB not found for {board}")
    return path

def sync_task(path: Path) -> str:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    board = str(meta.get("board") or "default")
    task_id = str(meta.get("task_id") or "")

    title_section = section(body, "Title")
    title = title_section.splitlines()[0].strip() if title_section else ""

    # `section()` intentionally returns "" both for a missing section and an
    # empty section. Keep those cases fail-safe for task bodies: this process
    # runs automatically, so ambiguity must never become a destructive clear.
    body_heading_present = "# Body\n" in body or "## Body\n" in body
    task_body = section(body, "Body")

    if not task_id or not title:
        raise SyncError("task file needs task_id and # Title")

    if not body_heading_present:
        raise SyncError(
            f"task {board}/{task_id}: missing # Body section; "
            "refusing to infer an empty body"
        )

    db = board_db(board)
    conn = sqlite3.connect(str(db), timeout=5)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            "SELECT title, body FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()

        if not row:
            raise SyncError(f"task {task_id} not found")

        live_title = str(row["title"] or "")
        live_body = str(row["body"] or "")

        # Critical safety boundary:
        # an automatic note sync may replace a body with another body,
        # but it may never turn a durable non-empty body into nothing.
        if live_body and not task_body:
            raise SyncError(
                f"task {board}/{task_id}: REFUSED empty body sync; "
                f"live Kanban body is non-empty ({len(live_body)} chars)"
            )

        changed_fields: list[str] = []

        if live_title != title:
            changed_fields.append("title")

        if live_body != task_body:
            changed_fields.append("body")

        if not changed_fields:
            conn.rollback()
            return f"task {board}/{task_id} unchanged"

        conn.execute(
            "UPDATE tasks SET title=?, body=? WHERE id=?",
            (title, task_body, task_id),
        )

        payload: dict[str, Any] = {
            "fields": changed_fields,
            "source": "hermes-work-sync",
        }

        if "body" in changed_fields:
            payload["body_length"] = len(task_body)

        conn.execute(
            """
            INSERT INTO task_events (task_id, kind, payload, created_at)
            VALUES (?, 'edited', ?, ?)
            """,
            (
                task_id,
                json.dumps(payload, ensure_ascii=False),
                int(time.time()),
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return (
        f"task {board}/{task_id} synced "
        f"({', '.join(changed_fields)})"
    )

def sync_file(path: Path) -> str:
    path = path.expanduser().resolve()
    if CRON_ROOT.resolve() in path.parents:
        return sync_cron(path)
    if KANBAN_ROOT.resolve() in path.parents:
        return sync_task(path)
    raise SyncError("file is outside Hermes Work control folders")

def sync_all() -> list[str]:
    out: list[str] = []
    for root in (CRON_ROOT, KANBAN_ROOT):
        if root.exists():
            for p in sorted(root.rglob("*.md")):
                try:
                    out.append(sync_file(p))
                except Exception as exc:
                    out.append(f"ERROR {p.name}: {exc}")
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    args = ap.parse_args()
    try:
        if args.path:
            print(sync_file(Path(args.path)))
        else:
            for line in sync_all():
                print(line)
        return 0
    except Exception as exc:
        print(f"Hermes Work sync: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
