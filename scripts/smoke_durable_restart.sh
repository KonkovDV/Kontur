#!/usr/bin/env bash
# Опциональный smoke: PNG sha256 переживает `docker compose restart core`.
# Не гейт CI. Store-boundary регрессия — backend/tests/test_object_store_durable.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE="${KONTUR_API:-http://127.0.0.1:8000/api/v1}"
AUTH="${KONTUR_SMOKE_AUTH:-INSPECTOR}"
PDF="${1:-}"

if [[ -z "$PDF" || ! -f "$PDF" ]]; then
  echo "usage: $0 <sample.pdf>   # compose уже up; JWT/legacy auth в KONTUR_SMOKE_AUTH" >&2
  exit 2
fi

hdr=(-H "Authorization: Bearer ${AUTH}")
create=$(curl -fsS "${hdr[@]}" -H 'Content-Type: application/json' \
  -d '{"object_id":"smoke-durable","completeness":{"PD":"UPLOADED","RD":"MISSING","ID":"MISSING"}}' \
  "$BASE/processes")
process_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["process_id"])' <<<"$create")
upload=$(curl -fsS "${hdr[@]}" -F "file=@${PDF}" -F "doc_stage=PD" \
  "$BASE/processes/${process_id}/files")
file_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["file_id"])' <<<"$upload")

# дождаться READY / страницы (простой poll)
for _ in $(seq 1 60); do
  if curl -fsS "${hdr[@]}" "$BASE/processes/${process_id}/files/${file_id}/pages/1.png" -o /tmp/kontur-smoke-before.png; then
    break
  fi
  sleep 2
done
[[ -f /tmp/kontur-smoke-before.png ]] || { echo "PNG before restart unavailable"; exit 1; }
before=$(sha256sum /tmp/kontur-smoke-before.png | awk '{print $1}')

docker compose restart core
for _ in $(seq 1 60); do
  if curl -fsS "$BASE/healthz" >/dev/null 2>&1 || curl -fsS "$BASE/../healthz" >/dev/null 2>&1; then
    break
  fi
  # healthz path may be /api/v1/healthz
  if curl -fsS "http://127.0.0.1:8000/api/v1/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS "${hdr[@]}" "$BASE/processes/${process_id}/files/${file_id}/pages/1.png" -o /tmp/kontur-smoke-after.png
after=$(sha256sum /tmp/kontur-smoke-after.png | awk '{print $1}')
echo "process_id=$process_id file_id=$file_id"
echo "before=$before"
echo "after=$after"
[[ "$before" == "$after" ]] || { echo "FAIL: PNG sha256 changed after restart"; exit 1; }
echo "OK: durable PNG survived compose restart core"
