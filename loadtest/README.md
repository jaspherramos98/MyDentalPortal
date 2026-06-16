# Load testing — Vegeta

Constant-rate HTTP load testing for MyDentalPortal, using
[Vegeta](https://github.com/tsenart/vegeta). Produces throughput + latency
histograms (p50/p95/p99) so we can size the deploy (gunicorn workers, Render
Starter vs free-tier cold start — see TODO Phase 6).

## ⚠️ PHI SAFETY — READ FIRST
**NEVER run load against the Render production deploy (`dental_portal_prod` = real
patient data).** It will stress real PHI and pollute metrics/logs.

Target one of:
- **Local** — `python app.py` → `http://127.0.0.1:5000` (recommended; default).
- **AWS showcase** env (`dental_portal_showcase`, demo data only).

The runners refuse to start if `BASE_URL` looks like the prod host.

> **Use `127.0.0.1`, not `localhost`.** Vegeta's Go HTTP client resolves hostnames
> via the system DNS; in some environments `localhost` fails to resolve (e.g.
> `lookup localhost on 8.8.8.8:53: no such host`). The literal IP skips DNS. All
> defaults here use `127.0.0.1`.

> **⚠️ Local runs use the Flask dev server (single-threaded), NOT gunicorn.**
> gunicorn is Unix-only (needs `fork`) and won't run on Windows, so local numbers
> measure **app + DB logic latency under serialized load** — useful to spot slow
> endpoints, but they do NOT characterize production concurrency. True
> worker-count / cold-start tuning must run against a **Linux gunicorn** target
> (a non-prod staging/showcase box) — never prod.

## Install Vegeta
- Windows: `scoop install vegeta`, or download the release `.zip` from
  https://github.com/tsenart/vegeta/releases and extract `vegeta.exe` onto PATH.
  (This repo's binary was installed to `~/.local/bin/vegeta.exe`, v12.13.0.)
- macOS: `brew install vegeta`
- Go: `go install github.com/tsenart/vegeta/v12@latest`

Verify: `vegeta --version`

## What's here
| File | Purpose |
|------|---------|
| `targets-public.txt` | Unauthenticated GET targets (health, login page, manifest, static shell). Absolute URLs use `http://127.0.0.1:5000` — edit if testing another host. |
| `run-public.sh` | Runs the public baseline (no login needed). |
| `login.py` | Logs in (handles CSRF + session cookie), writes `targets-authed.txt` with the `Cookie` header baked in. Read-only GET routes only. |
| `run-authed.sh` | Calls `login.py`, then runs Vegeta against the authed targets. |
| `.gitignore` | Keeps generated `targets-authed.txt` + `*.bin`/`*.json` results out of git (cookie = a live session). |

## Usage

### 1. Public baseline (no auth)
```bash
# defaults to http://127.0.0.1:5000, 50 req/s for 30s
bash loadtest/run-public.sh
# or override:
RATE=100 DURATION=20s BASE_URL=http://127.0.0.1:5000 bash loadtest/run-public.sh
```

### 2. Authenticated read paths
```bash
# logs in with the default local admin, then load-tests read-only GETs
EMAIL=admin@dental.com PASSWORD=admin123 bash loadtest/run-authed.sh
```
`login.py` needs `requests` (already transitively available; `pip install requests`
if missing).

## Reading the output
Vegeta prints a report like:
```
Requests   [total, rate]   1500, 50.03
Latencies  [mean, p50, p95, p99, max]  4.2ms, 3.8ms, 7.1ms, 12ms, 45ms
Success    [ratio]         100.00%
Status Codes [code:count]  200:1500
```
Watch **p95/p99** (tail latency) and **Success ratio**. On Render free tier the
first request after idle eats the ~50s cold start — run a warm-up hit first, or
that single request skews `max`.
