#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import quote

VAULT = Path(os.environ.get("HERMES_WORK_VAULT", "~/Documents/Hermes-Memory")).expanduser()
CONTROL = VAULT / "90 Hermes Control"
CRON_ROOT = CONTROL / "Scheduled Jobs"
KANBAN_ROOT = CONTROL / "Kanban"
HERMES = os.environ.get("HERMES_WORK_HERMES", "hermes")
HERE = Path(__file__).resolve().parent
SYNC = HERE / "hermes-work-sync.py"

class NoteError(RuntimeError):
    pass

def clean(value, limit=100000):
    text = "" if value is None else str(value)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)[:limit]

def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._ -]+", "-", value).strip(" .-")
    return value[:90] or "Hermes Work"

def profile_home(profile: str) -> Path:
    root = Path.home() / ".hermes"
    return root if profile == "default" else root / "profiles" / profile

def load_cron(profile: str, job_id: str) -> dict:
    path = profile_home(profile) / "cron" / "jobs.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
    for job in jobs if isinstance(jobs, list) else []:
        if isinstance(job, dict) and str(job.get("id") or "") == job_id:
            return job
    raise NoteError(f"cron job {profile}/{job_id} not found")

def schedule_text(job: dict) -> str:
    s = job.get("schedule")
    if isinstance(s, str):
        return s
    if isinstance(s, dict):
        return str(s.get("display") or s.get("expr") or s.get("value") or "")
    return ""

def cron_note(profile: str, job_id: str) -> Path:
    job = load_cron(profile, job_id)
    name = clean(job.get("name") or job_id, 200).replace("\n", " ")
    folder = CRON_ROOT / profile
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_name(name)}.md"
    skills = job.get("skills") or job.get("skill") or []
    if isinstance(skills, str):
        skills = [skills]
    enabled = job.get("enabled", True) is not False and str(job.get("state") or "") != "paused"
    lines = [
        "---", "type: hermes-cron", f"profile: {profile}", f"job_id: {job_id}",
        f"name: {name}", f"schedule: {schedule_text(job)}", f"enabled: {'true' if enabled else 'false'}", "skills:",
    ]
    lines.extend(f"  - {clean(x,128)}" for x in skills)
    lines += ["---", "", f"# {name}", "", "# Prompt", "", clean(job.get("prompt")), ""]
    if not path.exists():
        path.write_text("\n".join(lines), encoding="utf-8")
    return path

def run_json(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise NoteError((p.stderr or p.stdout or "Hermes command failed").strip())
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as exc:
        raise NoteError("Hermes returned invalid JSON") from exc

def task_note(board: str, task_id: str) -> Path:
    raw = run_json([HERMES, "kanban", "--board", board, "show", task_id, "--json"])
    task = raw.get("task") if isinstance(raw.get("task"), dict) else raw
    if str(task.get("id") or "") != task_id:
        raise NoteError(f"task {board}/{task_id} not found")
    title = clean(task.get("title") or task_id, 300).replace("\n", " ")
    folder = KANBAN_ROOT / board
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_name(title)} - {task_id}.md"
    content = "\n".join([
        "---", "type: hermes-kanban-task", f"board: {board}", f"task_id: {task_id}", "---", "",
        f"# {title}", "", "# Title", "", title, "", "# Body", "", clean(task.get("body")), "",
        "## Runtime (Hermes-owned; do not edit expecting sync)", "",
        f"- Status: {clean(task.get('status'),64)}", f"- Assignee: {clean(task.get('assignee') or 'unassigned',128)}",
        f"- Priority: {task.get('priority',0)}", "",
    ])
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return path

def make_note(kind: str, scope: str, item_id: str) -> Path:
    return cron_note(scope, item_id) if kind == "cron" else task_note(scope, item_id)

def open_obsidian(path: Path) -> None:
    uri = "obsidian://open?path=" + quote(str(path.resolve()), safe="")
    subprocess.Popen(["xdg-open", uri], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def edit_nvim(path: Path) -> None:
    nvim = shlex.join(["nvim", str(path)])
    sync = shlex.join([sys.executable, str(SYNC), str(path)])
    command = f"{nvim}; rc=$?; if [ $rc -eq 0 ]; then {sync}; fi; exit $rc"
    subprocess.Popen(["omarchy-launch-floating-terminal-with-presentation", command], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["obsidian","nvim","bootstrap"])
    ap.add_argument("kind", choices=["cron","task"])
    ap.add_argument("scope")
    ap.add_argument("item_id")
    args = ap.parse_args()
    try:
        note = make_note(args.kind,args.scope,args.item_id)
        if args.action == "bootstrap":
            print(note)
        elif args.action == "obsidian":
            open_obsidian(note)
        elif args.action == "nvim":
            edit_nvim(note)
        return 0
    except Exception as exc:
        print(f"Hermes Work note: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
