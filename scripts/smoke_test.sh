#!/usr/bin/env bash
# End-to-end check of a running stack through the frontend proxy (what the browser uses):
# health, job submission, live progress over SSE, completion, video download with Range.
# Usage: scripts/smoke_test.sh [base_url]   (default http://127.0.0.1:3000)
set -euo pipefail
BASE="${1:-http://127.0.0.1:3000}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== health"
curl -fsS "$BASE/api/health" | tee "$TMP/health.json"; echo
jq -e '.status == "ok" and .worker.online' "$TMP/health.json" >/dev/null

echo "== submit"
curl -fsS -X POST "$BASE/api/jobs" -H 'Content-Type: application/json' \
  -d '{"prompt": "smoke test: a lighthouse at dusk", "preset": "draft", "seed": 1}' \
  | tee "$TMP/job.json"; echo
JOB_ID=$(jq -r .id "$TMP/job.json")

echo "== follow events (SSE through the proxy)"
# The stream ends by itself once the job is finished.
curl -fsS -N --max-time 300 "$BASE/api/jobs/$JOB_ID/events" > "$TMP/events.txt"
grep '^data: ' "$TMP/events.txt" | sed 's/^data: //' \
  | jq -c '{status, progress, queue_position}' | tee "$TMP/progress.txt"
grep -q '"status":"running"' "$TMP/progress.txt"
tail -n1 "$TMP/progress.txt" | jq -e '.status == "succeeded" and .progress == 1' >/dev/null

echo "== job"
curl -fsS "$BASE/api/jobs/$JOB_ID" > "$TMP/final.json"
jq -e '.video_url and .thumbnail_url' "$TMP/final.json" >/dev/null
VIDEO_URL=$(jq -r .video_url "$TMP/final.json")

echo "== video"
curl -fsS -D "$TMP/headers.txt" -o "$TMP/video.mp4" "$BASE$VIDEO_URL"
grep -qi '^content-type: video/mp4' "$TMP/headers.txt"
head -c 12 "$TMP/video.mp4" | grep -q ftyp
echo "video: $(stat -c %s "$TMP/video.mp4") bytes"

echo "== range request (seeking)"
CODE=$(curl -s -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' "$BASE$VIDEO_URL")
test "$CODE" = 206

echo "== download"
curl -fsS -D - -o /dev/null "$BASE$VIDEO_URL?download=true" | grep -qi '^content-disposition: attachment'

echo "smoke test passed for job $JOB_ID"
