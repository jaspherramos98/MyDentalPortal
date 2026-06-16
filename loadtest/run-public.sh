#!/usr/bin/env bash
# Public (unauthenticated) Vegeta baseline. No login required.
# Usage: [BASE_URL=...] [RATE=50] [DURATION=30s] bash loadtest/run-public.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5000}"
RATE="${RATE:-50}"
DURATION="${DURATION:-30s}"

# PHI guard — never hammer the production deploy (real patient data).
case "$BASE_URL" in
  *dental_portal_prod*|*onrender.com*)
    echo "REFUSING: BASE_URL ($BASE_URL) looks like production. Use local or the AWS showcase env." >&2
    exit 1 ;;
esac

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Rewrite the localhost default in the targets file to the chosen BASE_URL.
TARGETS="$(sed "s|http://127.0.0.1:5000|${BASE_URL}|g" "$DIR/targets-public.txt")"

echo ">>> Public load test: $BASE_URL @ ${RATE}/s for ${DURATION}"
echo "$TARGETS" | vegeta attack -rate="$RATE" -duration="$DURATION" | tee "$DIR/results-public.bin" | vegeta report
echo ">>> (latency histogram: vegeta report -type=hist[0,5ms,10ms,25ms,50ms,100ms] < loadtest/results-public.bin)"
