#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "snapshot_worker.py"
SPEC = importlib.util.spec_from_file_location("snapshot_worker_test", MODULE_PATH)
assert SPEC and SPEC.loader
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class SnapshotWorkerTest(unittest.TestCase):
    def fake_hermes(self, directory: Path, invalid: bool = False) -> tuple[str, Path]:
        target = directory / "hermes"
        log = directory / "calls.jsonl"
        boards = json.dumps([
            {
                "slug": "alpha",
                "name": "Alpha\u0000 board",
                "description": "Example board",
                "is_current": True,
                "counts": {"running": 1, "done": 2},
                "db_path": "/must/not/leak",
                "default_workdir": "/must/not/leak",
            }
        ])
        tasks = json.dumps([
            {
                "id": "t_1",
                "title": "<b>Running</b>",
                "body": "Sensitive body",
                "assignee": "default",
                "status": "running",
                "priority": 2,
                "created_at": 10,
                "started_at": 20,
                "blocked_reason": "waiting",
                "dependencies": ["t_0"],
                "tags": ["system"],
                "workspace_path": "/must/not/leak",
            },
            {"id": "t_done", "title": "Done", "status": "done"},
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

    def with_log(self, log: Path):
        class LogContext:
            def __enter__(inner_self):
                inner_self.old = os.environ.get("FAKE_HERMES_LOG")
                os.environ["FAKE_HERMES_LOG"] = str(log)

            def __exit__(inner_self, *_args):
                if inner_self.old is None:
                    os.environ.pop("FAKE_HERMES_LOG", None)
                else:
                    os.environ["FAKE_HERMES_LOG"] = inner_self.old
        return LogContext()

    def test_snapshot_minimizes_boards_tasks_and_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes, log = self.fake_hermes(Path(tmp))
            with self.with_log(log), patch.object(WORKER.Path, "home", return_value=Path(tmp)):
                payload = WORKER.snapshot(hermes, ["alpha"])
            calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(payload["schemaVersion"], 3)
        self.assertEqual(set(payload["boards"][0]), {"slug", "name", "description", "is_current", "counts"})
        self.assertNotIn("\x00", payload["boards"][0]["name"])
        self.assertEqual([task["id"] for task in payload["tasksByBoard"]["alpha"]], ["t_1"])
        self.assertEqual(payload["tasksByBoard"]["alpha"][0]["body"], "")
        self.assertNotIn("workspace_path", payload["tasksByBoard"]["alpha"][0])
        self.assertEqual(payload["cronJobs"], [])
        self.assertEqual(calls, [
            ["kanban", "boards", "list", "--json"],
            ["kanban", "--board", "alpha", "list", "--json"],
        ])

    def test_bodies_are_explicit_and_bounded(self) -> None:
        task = WORKER.sanitize_task(
            {"id": "x", "title": "X", "body": "a" * 5000, "status": "blocked"}, True
        )
        self.assertEqual(len(task["body"]), 4000)
        self.assertIsNone(WORKER.sanitize_task({"id": "x", "status": "done"}, True))

    def test_cron_jobs_are_sanitized_from_jobs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cron_dir = home / ".hermes" / "cron"
            cron_dir.mkdir(parents=True)
            (cron_dir / "jobs.json").write_text(json.dumps([
                {
                    "id": "job_1",
                    "name": "Hardware watch",
                    "prompt": "Check second-hand listings",
                    "schedule": {"kind": "interval", "display": "every 2h"},
                    "skills": ["hardware-watch"],
                    "state": "scheduled",
                    "enabled": True,
                    "next_run_at": "2026-09-07T23:00:00Z",
                    "last_status": "ok",
                    "private_field": "must not leak",
                }
            ]), encoding="utf-8")
            with patch.object(WORKER.Path, "home", return_value=home):
                jobs = WORKER.load_cron_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["name"], "Hardware watch")
        self.assertEqual(jobs[0]["schedule"], "every 2h")
        self.assertEqual(jobs[0]["skills"], ["hardware-watch"])
        self.assertNotIn("private_field", jobs[0])

    def test_invalid_json_and_unknown_board_are_safe_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes, log = self.fake_hermes(Path(tmp), invalid=True)
            with self.with_log(log), patch.object(WORKER.Path, "home", return_value=Path(tmp)):
                with self.assertRaisesRegex(WORKER.SnapshotError, "invalid JSON"):
                    WORKER.snapshot(hermes, [])
        with tempfile.TemporaryDirectory() as tmp:
            hermes, log = self.fake_hermes(Path(tmp))
            with self.with_log(log), patch.object(WORKER.Path, "home", return_value=Path(tmp)):
                with self.assertRaisesRegex(WORKER.SnapshotError, "unavailable"):
                    WORKER.snapshot(hermes, ["missing"])

    def test_request_and_input_validation(self) -> None:
        request = {"hermesPath": "/opt/Hermes Agent/hermes", "boards": ["alpha"]}
        import base64
        encoded = base64.urlsafe_b64encode(json.dumps(request).encode()).decode().rstrip("=")
        self.assertEqual(WORKER.decode_request(encoded)["boards"], ["alpha"])
        self.assertEqual(WORKER.validate_hermes_path("hermes"), "hermes")
        self.assertEqual(WORKER.validate_hermes_path("/opt/Hermes Agent/hermes"), "/opt/Hermes Agent/hermes")
        with self.assertRaises(WORKER.SnapshotError):
            WORKER.validate_hermes_path("hermes;touch-pwned")
        with self.assertRaises(WORKER.SnapshotError):
            WORKER.validate_boards(["bad;touch-pwned"])
        with self.assertRaises(WORKER.SnapshotError):
            WORKER.validate_boards([f"b-{index}" for index in range(21)])

    def test_command_output_limit_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = Path(tmp) / "large"
            command.write_text("#!/usr/bin/env python3\nprint('x' * 4096)\n", encoding="utf-8")
            command.chmod(command.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(WORKER.SnapshotError, "too much data"):
                WORKER.run_capped([str(command)], max_output=1024)

    def test_untrusted_snapshot_is_re_sanitized(self) -> None:
        payload = WORKER.sanitize_payload({
            "schemaVersion": 3,
            "fetchedAt": 1,
            "boards": [{"slug": "alpha", "name": "Alpha", "db_path": "/leak"}],
            "tasksByBoard": {"alpha": [
                {"id": "x", "title": "X", "body": "secret", "status": "running", "path": "/leak"},
                {"id": "y", "title": "Y", "status": "done"},
            ]},
            "cronJobs": [{"id": "job", "name": "Job", "prompt": "hello", "secret": "no"}],
        }, ["alpha"], False)
        self.assertEqual(set(payload["boards"][0]), {"slug", "name", "description", "is_current", "counts"})
        self.assertEqual(payload["tasksByBoard"]["alpha"][0]["body"], "")
        self.assertEqual(len(payload["tasksByBoard"]["alpha"]), 1)
        self.assertNotIn("secret", payload["cronJobs"][0])


if __name__ == "__main__":
    unittest.main()
