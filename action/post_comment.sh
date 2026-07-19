#!/usr/bin/env bash
set -euo pipefail

marker='<!-- receipts-trust-card -->'
event_path="${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH is required}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
token="${GITHUB_TOKEN:?GITHUB_TOKEN is required}"
card_path="${RECEIPTS_CARD_PATH:?RECEIPTS_CARD_PATH is required}"
curl_bin="${CURL_BIN:-curl}"
pr_number="$(python3 - "$event_path" <<'PY'
import json, sys
event = json.load(open(sys.argv[1], encoding="utf-8"))
print(event["pull_request"]["number"])
PY
)"
api="https://api.github.com/repos/$repo/issues/$pr_number/comments"
payload="$(python3 - "$card_path" "$marker" <<'PY'
import json, sys
card = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({"body": sys.argv[2] + "\n" + card}))
PY
)"

headers=(-H "Authorization: Bearer $token" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")
comments="$($curl_bin -fsSL "${headers[@]}" "$api")"
comment_id="$(printf '%s' "$comments" | python3 -c '
import json, sys
marker = sys.argv[1]
for comment in json.load(sys.stdin):
    if marker in comment.get("body", ""):
        print(comment["id"])
        break
' "$marker")"
if [[ -n "$comment_id" ]]; then
  method=PATCH
  endpoint="$api/$comment_id"
else
  method=POST
  endpoint="$api"
fi
if [[ "${RECEIPTS_DRY_RUN:-false}" == "true" ]]; then
  echo "DRY RUN: $method $endpoint"
  exit 0
fi
"$curl_bin" -fsSL -X "$method" "${headers[@]}" -H "Content-Type: application/json" --data "$payload" "$endpoint" >/dev/null
echo "Receipts Trust Card ${method,,}ed for PR #$pr_number."
