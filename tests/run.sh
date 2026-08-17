#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

python3 -m py_compile "$repo_dir/bin/hermes-kanban-snapshot" "$repo_dir/bin/snapshot_worker.py"
bash -n "$repo_dir/tests/test_transport.sh" "$repo_dir/tests/run.sh"
python3 "$repo_dir/tests/test_snapshot_worker.py"
"$repo_dir/tests/test_transport.sh"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  /usr/lib/qt6/bin/qmltestrunner \
  -input "$repo_dir/tests" \
  -import "$repo_dir" \
  -import /usr/share/omarchy/shell
