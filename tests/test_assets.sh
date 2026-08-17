#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
status_dir="$repo_dir/assets/status"
expected=(
  alert-octagon
  calendar-time
  circle-check
  eye-check
  inbox
  list-check
  loader-2
  player-play
)

test "$(find "$status_dir" -maxdepth 1 -name '*.svg' | wc -l)" -eq "${#expected[@]}"

for icon in "${expected[@]}"; do
  file="$status_dir/$icon.svg"
  test -f "$file"
  grep -Fq 'stroke="#ffffff"' "$file"
  ! grep -Fq 'currentColor' "$file"
done

test -s "$repo_dir/assets/tabler/LICENSE"
grep -Fq 'Tabler Icons v3.46.0' "$repo_dir/assets/tabler/README.md"
