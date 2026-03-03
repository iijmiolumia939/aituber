#!/usr/bin/env bash
set -euo pipefail
INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | python -c 'import json,sys;print(json.load(sys.stdin).get("toolName",""))')"
TOOL_ARGS_RAW="$(echo "$INPUT" | python -c 'import json,sys;print(json.load(sys.stdin).get("toolArgs",""))')"
deny(){ local reason="$1"; python - <<PY
import json
print(json.dumps({"permissionDecision":"deny","permissionDecisionReason":${reason!r}}))
PY
exit 0; }
if [[ "$TOOL_NAME" == "bash" ]]; then
  cmd="$(echo "$TOOL_ARGS_RAW" | python -c 'import json,sys; import json as j; s=sys.stdin.read();
try: print(j.loads(s).get("command",""))
except: print("")')"
  if echo "$cmd" | grep -Eqi "(rm\s+-rf\s+/|rm\s+-rf\s+\.|del\s+/s|format\s|mkfs\.|shutdown\s|reboot\s)"; then
    deny "Dangerous command detected"
  fi
fi
if [[ "$TOOL_NAME" == "edit" ]]; then
  path="$(echo "$TOOL_ARGS_RAW" | python -c 'import json,sys; import json as j; s=sys.stdin.read();
try: print(j.loads(s).get("path",""))
except: print("")')"
  if echo "$path" | grep -Eqi "^(Unity/|Assets/|ProjectSettings/|OBS/|obs/)"; then
    deny "Editing Unity/OBS paths requires explicit user request"
  fi
fi
echo '{"permissionDecision":"allow"}'
