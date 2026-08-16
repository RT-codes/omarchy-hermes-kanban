#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "remote_snapshot.py"
SPEC = importlib.util.spec_from_file_location("remote_snapshot", MODULE_PATH)
assert SPEC and SPEC.loader
REMOTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REMOTE)


class RemoteSnapshotTest(unittest.TestCase):
    def fake_hermes(self, directory: Path, invalid: bool = False) -> tuple[str, Path]:
        target = directory / "hermes"
        log = directory / "calls.jsonl"
        boards = json.dumps([
            {"slug": "alpha", "name": "Alpha", "is_current": True, "counts": {"running": 1}}
        ])
        tasks = json.dumps([
            {
                "id": "t_1",
                "title": "Running",
                "body": "Work",
                "assignee": "default",
                "status": "running",
                "priority": 2,
                "created_at": 10,
                "started_at": 20,
                "workspace_path": "/must/not/leak",
            }
        ])
        target.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            f"boards = {boards!r}\n"
            f"tasks = {tasks!r}\n"
            f"invalid = {invalid!r}\n"
            "with open(os.environ['FAKE_HERMES_LOG'], 'a', encoding='utf-8') as stream:\n"
            "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "print('nope' if invalid else (boards if 'boards' in sys.argv else tasks))\n",
            encoding="utf-8",
        )
        target.chmod(target.stat().st_mode | stat.S_IXUSR)
        return str(target), log

    def test_snapshot_uses_only_read_commands_and_filters_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes, log = self.fake_hermes(Path(tmp))
            old_log = os.environ.get("FAKE_HERMES_LOG")
            os.environ["FAKE_HERMES_LOG"] = str(log)
            try:
                payload = REMOTE.snapshot(hermes, ["alpha"])
            finally:
                if old_log is None:
                    os.environ.pop("FAKE_HERMES_LOG", None)
                else:
                    os.environ["FAKE_HERMES_LOG"] = old_log
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["boards"][0]["slug"], "alpha")
        self.assertEqual(payload["tasksByBoard"]["alpha"][0]["id"], "t_1")
        self.assertNotIn("workspace_path", payload["tasksByBoard"]["alpha"][0])
        self.assertEqual(calls, [
            ["kanban", "boards", "list", "--json"],
            ["kanban", "--board", "alpha", "list", "--json"],
        ])

    def test_invalid_json_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes, log = self.fake_hermes(Path(tmp), invalid=True)
            old_log = os.environ.get("FAKE_HERMES_LOG")
            os.environ["FAKE_HERMES_LOG"] = str(log)
            try:
                with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                    REMOTE.snapshot(hermes, [])
            finally:
                if old_log is None:
                    os.environ.pop("FAKE_HERMES_LOG", None)
                else:
                    os.environ["FAKE_HERMES_LOG"] = old_log

    def test_missing_hermes_is_an_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not found"):
            REMOTE.snapshot("/definitely/missing/hermes", [])


if __name__ == "__main__":
    unittest.main()
