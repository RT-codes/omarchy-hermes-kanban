#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

fake_hermes="$tmp_dir/hermes"
cat > "$fake_hermes" <<'PY'
#!/usr/bin/env python3
import json, sys
if "boards" in sys.argv:
    print(json.dumps([{"slug":"alpha","name":"Alpha","is_current":True,"counts":{"running":1}}]))
else:
    print(json.dumps([{"id":"t_1","title":"Run","body":"secret","status":"running"}]))
PY
chmod +x "$fake_hermes"

local_output=$("$repo_dir/bin/hermes-kanban-snapshot" snapshot --mode local --hermes "$fake_hermes" --board alpha)
jq -e '.schemaVersion == 2 and .tasksByBoard.alpha[0].body == ""' <<<"$local_output" >/dev/null

fake_ssh="$tmp_dir/ssh"
cat > "$fake_ssh" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_SSH_LOG"
case ${FAKE_SSH_MODE:-ok} in
  auth) exit 255 ;;
  fail) exit 4 ;;
esac
request=${!#}
python3 - "$request"
SH
chmod +x "$fake_ssh"

ssh_log="$tmp_dir/ssh.log"
remote_output=$(FAKE_HERMES_LOG="$tmp_dir/hermes.log" FAKE_SSH_LOG="$ssh_log" \
  HERMES_KANBAN_SSH_BIN="$fake_ssh" \
  "$repo_dir/bin/hermes-kanban-snapshot" snapshot --mode remote --host safe-alias \
  --hermes "$fake_hermes" --board alpha --include-task-bodies)
jq -e '.tasksByBoard.alpha[0].body == "secret"' <<<"$remote_output" >/dev/null

for required in \
  'BatchMode=yes' 'PreferredAuthentications=publickey' 'PasswordAuthentication=no' \
  'StrictHostKeyChecking=yes' 'ClearAllForwardings=yes' 'ForwardAgent=no' \
  'ForwardX11=no' 'PermitLocalCommand=no' 'ControlPath=none'; do
  grep -Fx "$required" "$ssh_log" >/dev/null
done

if HERMES_KANBAN_SSH_BIN="$fake_ssh" "$repo_dir/bin/hermes-kanban-snapshot" \
  snapshot --mode remote --host 'bad;touch-pwned' --hermes hermes 2>/dev/null; then
  echo "invalid host was accepted" >&2
  exit 1
fi

set +e
FAKE_SSH_MODE=auth HERMES_KANBAN_SSH_BIN="$fake_ssh" FAKE_SSH_LOG="$ssh_log" \
  "$repo_dir/bin/hermes-kanban-snapshot" snapshot --mode remote --host safe-alias --hermes hermes >/dev/null 2>&1
auth_status=$?
set -e
[[ $auth_status -eq 10 ]]
