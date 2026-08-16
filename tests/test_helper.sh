#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

fake_ssh="$tmp_dir/ssh"
cat > "$fake_ssh" <<'SH'
#!/usr/bin/env bash
case ${FAKE_SSH_MODE:-ok} in
  ok) printf '%s\n' '{"schemaVersion":1,"fetchedAt":1,"boards":[],"tasksByBoard":{}}' ;;
  auth) exit 255 ;;
  timeout) sleep 3 ;;
esac
SH
chmod +x "$fake_ssh"

output=$(HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-remote" snapshot --host ssh-ninalyx --hermes hermes)
[[ $output == *'"schemaVersion":1'* ]]

if HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-remote" snapshot --host=-bad --hermes hermes 2>/dev/null; then
  echo "invalid host was accepted" >&2
  exit 1
fi

if HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-remote" snapshot --host ssh-ninalyx --hermes hermes --board 'bad;touch-pwned' 2>/dev/null; then
  echo "invalid board was accepted" >&2
  exit 1
fi

set +e
FAKE_SSH_MODE=auth HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-remote" snapshot --host ssh-ninalyx --hermes hermes >/dev/null 2>&1
auth_status=$?
FAKE_SSH_MODE=timeout HERMES_KANBAN_COMMAND_TIMEOUT_SEC=1 HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-remote" snapshot --host ssh-ninalyx --hermes hermes >/dev/null 2>&1
timeout_status=$?
set -e

[[ $auth_status -eq 10 ]]
[[ $timeout_status -eq 10 ]]
