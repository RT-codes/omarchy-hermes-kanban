#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

bash -n "$repo_dir/bin/hermes-kanban-remote" "$repo_dir/tests/test_helper.sh" "$repo_dir/tests/run.sh"
python3 -m unittest "$repo_dir/tests/test_remote_snapshot.py"
"$repo_dir/tests/test_helper.sh"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  /usr/lib/qt6/bin/qmltestrunner \
  -input "$repo_dir/tests" \
  -import "$repo_dir" \
  -import /home/perro/.local/share/omarchy/shell
