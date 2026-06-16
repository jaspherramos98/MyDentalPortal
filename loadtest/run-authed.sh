#!/usr/bin/env bash
# Authenticated read-path Vegeta test. Logs in via login.py (CSRF + cookie),
# then attacks read-only GET routes.
# Usage: [BASE_URL=...] [EMAIL=...] [PASSWORD=...] [RATE=30] [DURATION=30s] bash loadtest/run-authed.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"
RATE="${RATE:-30}"
DURATION="${DURATION:-30s}"

case "$BASE_URL" in
  *dental_portal_prod*|*onrender.com*)
    echo "REFUSING: BASE_URL ($BASE_URL) looks like production. Use local or the AWS showcase env." >&2
    exit 1 ;;
esac

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">>> Logging in and generating authed targets..."
BASE_URL="$BASE_URL" python "$DIR/login.py"

echo ">>> Authed load test: $BASE_URL @ ${RATE}/s for ${DURATION}"
vegeta attack -targets="$DIR/targets-authed.txt" -rate="$RATE" -duration="$DURATION" \
  | tee "$DIR/results-authed.bin" | vegeta report
