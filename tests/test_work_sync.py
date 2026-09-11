#!/usr/bin/env python3

from pathlib import Path
import json
import os
import sqlite3
import subprocess
import tempfile


REPO = Path(__file__).resolve().parents[1]
SYNC = REPO / "bin/hermes-work-sync.py"


def run_sync(note: Path, home: Path, vault: Path):
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["HERMES_WORK_VAULT"] = str(vault)

    return subprocess.run(
        ["python3", str(SYNC), str(note)],
        env=env,
        text=True,
        capture_output=True,
    )


def read_body(db: Path) -> str:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT body FROM tasks WHERE id='t_test'"
        ).fetchone()[0]
    finally:
        conn.close()


with tempfile.TemporaryDirectory(prefix="hermes-work-sync-test-") as raw:
    root = Path(raw)
    home = root / "home"
    vault = home / "Documents/Hermes-Memory"
    notes = vault / "90 Hermes Control/Kanban/default"

    (home / ".hermes").mkdir(parents=True)
    notes.mkdir(parents=True)

    db = home / ".hermes/kanban.db"

    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            body TEXT
        );

        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            kind TEXT,
            payload TEXT,
            created_at INTEGER
        );
        """
    )

    conn.execute(
        "INSERT INTO tasks(id,title,body) VALUES (?,?,?)",
        ("t_test", "Original title", "OLD BODY"),
    )
    conn.commit()
    conn.close()

    note = notes / "test - t_test.md"

    nested_body = """## What this is

This belongs inside the task body.

## Why

Level-two headings must not terminate a level-one Body section.

### Acceptance detail

Level-three headings must remain inside it too.

## Return

Report the result."""

    note.write_text(
        f"""---
type: hermes-kanban-task
board: default
task_id: t_test
---

# Title

Original title

# Body

{nested_body}

# Runtime

- Status: running
""",
        encoding="utf-8",
    )

    result = run_sync(note, home, vault)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert read_body(db) == nested_body

    print("PASS 1: nested ##/### headings remain inside # Body")

    conn = sqlite3.connect(db)
    payload = json.loads(
        conn.execute(
            "SELECT payload FROM task_events ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    )
    conn.close()

    assert payload == {
        "fields": ["body"],
        "source": "hermes-work-sync",
        "body_length": len(nested_body),
    }

    print("PASS 2: edited event records source and changed field")

    # A genuinely empty body must not destroy durable content.
    note.write_text(
        """---
type: hermes-kanban-task
board: default
task_id: t_test
---

# Title

Original title

# Body

# Runtime

- Status: running
""",
        encoding="utf-8",
    )

    result = run_sync(note, home, vault)

    assert result.returncode != 0
    assert "REFUSED empty body sync" in result.stderr
    assert read_body(db) == nested_body

    print("PASS 3: genuinely empty body is refused")
    print("PASS 4: durable body survives refused sync")

    # A missing Body section must also fail closed.
    note.write_text(
        """---
type: hermes-kanban-task
board: default
task_id: t_test
---

# Title

Original title

# Runtime

- Status: running
""",
        encoding="utf-8",
    )

    result = run_sync(note, home, vault)

    assert result.returncode != 0
    assert "missing # Body section" in result.stderr
    assert read_body(db) == nested_body

    print("PASS 5: missing Body section is refused")

print()
print("ALL HERMES WORK SYNC REGRESSION CHECKS PASS")
