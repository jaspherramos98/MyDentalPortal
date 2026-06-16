# CLAUDE.md — Project Context for Claude Code
# This file gives Claude Code the full context of the Dental Portal project.
# It was generated from the initial build conversation on claude.ai (June 9, 2026).

## Project Overview
MyDentalPortal is a web-based dental clinic management system built for a real dental clinic
(JRAMOS DENTAL HUB, Obando, Bulacan, Philippines). It is currently used by one clinic but
architected for future multi-clinic and multi-user (role-based) expansion.

**This is production medical software. Patient health data is involved. Treat every change with care.**

## Tech Stack
- **Backend:** Python 3.11, Flask 2.3.3, Flask-PyMongo
- **Database:** MongoDB (local via Compass for dev, MongoDB Atlas for production)
- **Frontend:** Jinja2 templates, Bootstrap 5.3, Font Awesome 6.4, vanilla JS
- **Deployment:** Render (current), AWS (planned for resume/portfolio)
- **Entry point:** `gunicorn app:app` (Procfile)

## File Structure (Dental Portal v3 — current)
```
MyDentalPortal/
├── app.py              # Slim entry point (~120 lines) — creates Flask app, registers blueprints
├── extensions.py       # mongo = PyMongo() singleton — ALL blueprints import from here
├── config.py           # Config classes (Dev/Prod), get_config()
├── requirements.txt    # Clean deps — NO bson package (conflicts with pymongo)
├── Procfile            # web: gunicorn app:app
├── runtime.txt         # python-3.11.5
├── render.yaml         # Render deployment config
├── .env.example        # Template for environment variables
├── .gitignore
├── CLAUDE.md           # This file
├── blueprints/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py       # Blueprint registry
│   │   ├── auth.py           # Login, register, logout
│   │   ├── main.py           # Dashboard, index, account settings
│   │   ├── clinics.py        # Clinic CRUD + search + currency (PHP/USD)
│   │   ├── patients.py       # Patient CRUD, PDA form fields, pagination
│   │   ├── charts.py         # *** SACRED — dental chart, DO NOT modify chart logic ***
│   │   ├── treatments.py     # Treatment records CRUD + JSON API
│   │   ├── appointments.py   # Appointments CRUD + calendar API
│   │   ├── uploads.py        # Patient photos/files + prescriptions (GridFS)
│   │   ├── admin.py          # Registration approvals + user management
│   │   └── reports.py        # Performance/reports
│   ├── repositories/         # Thin data-access layer (Phase 3) — wraps mongo.db
│   │   ├── __init__.py
│   │   ├── patients.py       # get, get_for_owner (access seam), ensure_nested
│   │   ├── clinics.py        # owned_by, owned_ids, get_owned
│   │   └── charts.py         # get_by_patient, insert, upsert (chart plumbing)
│   ├── models/              # Boundary schemas (pydantic) — validate at the write edge
│   │   ├── __init__.py
│   │   └── patient.py        # PatientDoc / validate_patient (lenient, extra="allow")
│   └── utils/
│       └── __init__.py       # login_required, admin_required, is_admin +
│                             #   verify_patient_access/user_clinic_ids (delegate to repos)
├── static/
│   ├── css/main.css
│   ├── js/
│   │   └── main.js
│   ├── manifest.webmanifest  # PWA manifest (served at /manifest.webmanifest)
│   ├── sw.js                 # PWA service worker (served at /sw.js, root scope)
│   ├── offline.html          # PWA offline fallback (static, no PHI)
│   └── icons/                # PWA icons (192/512/maskable) — placeholder tooth
└── templates/
    ├── base.html               # Main layout with navbar
    ├── auth/login.html
    ├── auth/register.html
    ├── dashboard/index.html
    ├── clinics/list.html
    ├── clinics/create.html
    ├── clinics/edit.html
    ├── patients/list.html
    ├── patients/create.html    # Full PDA paper form fields
    ├── patients/detail.html    # 4 tabs: Medical, Dental, Treatment, Personal
    ├── patients/edit.html
    ├── charts/dental_chart.html  # *** SACRED — FDI cross-layout chart ***
    ├── treatments/add.html
    ├── treatments/edit.html
    ├── appointments.html       # Standalone page (own HTML/CSS/JS, doesn't extend base.html)
    └── errors/404.html, 500.html
```

## Critical Rules

### The Dental Chart is SACRED
- File: `templates/charts/dental_chart.html` and `blueprints/routes/charts.py`
- Uses FDI (ISO 3950) numbering — standard in the Philippines
- Cross layout with 4 quadrants: permanent teeth (11-48) + deciduous teeth (51-85)
- Segment color cycling: clear → blue → red → light_red → clear
- Status input boxes above/below teeth for condition codes
- Assessment sections: periodontal screening, occlusion, appliances, TMD, X-ray
- Save via JS fetch to `/charts/update/<patient_id>` or `/chart/update/<patient_id>`
- **DO NOT modify the chart's HTML structure, SVG paths, JavaScript color logic, or save/load flow**
- Only safe changes: import paths, url_for references, CSS styling, adding new assessment fields

### Patient Data Structure (matches PDA paper form)
Patients are stored with nested dicts. Always call `patient_repo.ensure_nested(patient)`
(`from blueprints.repositories import patients as patient_repo`) before template rendering.
Key nested paths: `personal_info`, `contact_info`, `dental_history`, `medical_history`,
`medical_history.allergies`, `medical_history.women_health`, `medical_history.conditions`,
`referral_info`, `minor_info`, `insurance_info`.

### Import Pattern
All blueprints import mongo from `extensions.py`:
```python
from extensions import mongo
```
NEVER import from `app.py` or `app_factory.py` (deleted).

### Data access — repository layer (Phase 3)
Prefer the thin repositories in `blueprints/repositories/` over raw `mongo.db` queries in routes,
especially for **patient access**: `verify_patient_access`/`user_clinic_ids` (in `utils/`) delegate to
`patients.get_for_owner` / `clinics.owned_ids`. That owner-scoped check is the **single seam** multi-staff
will change (owner_id → membership) — don't re-implement it inline in routes. Pass 1 migrated patients,
clinics, charts + the access seam; remaining blueprints (appointments, treatments, uploads, admin,
reports, auth, main) still query `mongo.db` directly and migrate in Pass 2.

**Schema validation at the write edge (Phase 3):** new patient documents go through
`patient_repo.create()` → `validate_patient()` (pydantic `PatientDoc`), which guarantees the nested
section skeleton + a valid `clinic_id` and rejects malformed docs, while **preserving** all extra/PDA
fields (`extra="allow"`). The edit route uses targeted dot-notation `$set` via `patient_repo.update_set()`
(hardcoded keys can't structurally malform a doc). Reads still use `ensure_nested` for legacy tolerance.

### URL Naming Convention
All url_for() calls use blueprint namespaces:
- `url_for('auth.login')`, `url_for('auth.register')`, `url_for('auth.logout')`
- `url_for('main.dashboard')`
- `url_for('clinics.list_clinics')`, `url_for('clinics.create_clinic')`, `url_for('clinics.edit_clinic', clinic_id=...)`
- `url_for('patients.list_patients')`, `url_for('patients.patient_detail', patient_id=...)`
- `url_for('charts.view_chart', patient_id=...)`
- `url_for('treatments.add_treatment', patient_id=...)`
- `url_for('appointments.appointments')`

### Error Logging
All routes use `[DEBUG]` and `[ERROR]` prefixed print statements + `traceback.print_exc()`.
When a bug is reported, the terminal output with `[ERROR]` blocks is the primary debugging info.

### Currency
Each clinic has a `currency` field (default: `PHP`). Treatment amounts display in the clinic's currency.
Options: PHP (₱) and USD ($).

### Appointments Page
`appointments.html` is a **standalone page** — it does NOT extend `base.html`.
It has its own CSS and inline JavaScript; the calendar uses the `/appointments/api` endpoints.
Clinic and patient data are passed from Flask and rendered via Jinja `{% for %}` loops.
**Its top nav is now a COPY of base.html's Bootstrap navbar** (class `app-navbar`, kept `position:sticky`
so the calendar's `100vh-80px` layout holds) — so it collapses to a hamburger on mobile like every other
tab. Keep it in sync with `base.html` by hand. **Because it's standalone, PWA tags (manifest/theme/icon +
SW registration) are also duplicated into its `<head>` — keep both in sync.**
Mobile/landscape (phone layout triggers on `@media (max-width:768px), (max-height:500px)` — landscape
phones are wide but short): week view is a swipeable 7×82vw horizontal grid; month view keeps 7 columns
but shrinks cells; the filter sidebar is off-canvas (toggle bottom-left, forced visible over `d-md-none`);
calendar forced full-width; stats are a 2×2 grid; the legend moved BELOW the grid (horizontal). Desktop
unchanged except the owner-approved nav swap + stats-grid/legend placement.
The off-canvas sidebar scrolls as ONE unit (filters→stats→patient list, fixed 2026-06-16): on mobile it's
anchored to the full viewport (`top:0;bottom:0;overflow-y:auto`) and the previously-nested scrolls are
flattened (`.sidebar .search-box{position:static}`, `.sidebar .patient-list{max-height:none;overflow:visible}`)
— **don't reintroduce a sticky `.search-box` or a capped `.patient-list` inside the phone media query.**
On mobile the **calendar header is stacked** (view-toggle row above the info badges, each wrapping with a
steady gap) with tighter padding/smaller buttons; and the `#selectedDate` badge uses a **compact date
format on phones** (`Jun 16, 2026` via a `matchMedia` check in `showAppointmentModal`) so picking a patient
doesn't reflow the header and shove the calendar down. Desktop keeps the long `Tuesday, June 16, 2026` format.
Mobile drag-drop is intentionally NOT supported (HTML5 DnD doesn't fire on touch); the mobile flow is
**tap a patient card → appointment modal** (defaults to today; tapping a calendar day to pre-select a date
on touch is a known gap, deferred).

### PWA (online-first, Phase 3.5 / roadmap #1 slice 1a)
The app is installable. `app.py` serves `/manifest.webmanifest` and `/sw.js` (the latter from root with
`Service-Worker-Allowed: /` so its scope is the whole app). **`static/sw.js` caches ONLY the static app
shell** (`/static/*`, cache-first) — navigations are **network-only** with a static `offline.html`
fallback, and **data/authenticated HTML is NEVER cached** (online-first = single source of truth, no PHI
on device). Service workers need HTTPS (met on Render) or localhost. Icons are placeholders from
`scripts/gen_pwa_icons.py`. Deferred: offline DATA caching, token auth, push.

## Load / performance testing (Vegeta, added 2026-06-16)
Harness lives in `loadtest/` (TODO Phase 6). Uses [Vegeta](https://github.com/tsenart/vegeta)
for constant-rate HTTP load + latency histograms — feeds the gunicorn-worker / Render-Starter
sizing decisions.
- **⚠️ PHI SAFETY:** never load-test Render prod (`dental_portal_prod` = real PHI). Runners + the
  login helper refuse a prod-looking `BASE_URL` (`onrender.com`). Target **local** (`python app.py`)
  or the AWS **showcase** env only. Login is rate-limited (10/min) and POSTs are CSRF-protected, so
  the harness load-tests **read-only GETs**.
- `loadtest/run-public.sh` — unauthenticated baseline (`/health`, `/login` GET, manifest, static shell).
- `loadtest/login.py` — stdlib-only (no pip deps); logs in (handles CSRF + Flask `session` cookie),
  **verifies** it authenticated (re-requests `/dashboard`), discovers a real patient id, writes
  `loadtest/targets-authed.txt` (git-ignored — holds a live cookie).
- `loadtest/run-authed.sh` — runs `login.py` then attacks authed read paths (dashboard, patients,
  patient detail, appointments).
- Vegeta **v12.13.0 installed** at `~/.local/bin/vegeta.exe`. Use `BASE_URL=http://127.0.0.1:5000`
  (NOT `localhost` — Vegeta's Go resolver can fail to resolve `localhost`). ⚠️ Local runs use the
  **single-threaded Flask dev server** (gunicorn is Unix-only, no Windows), so numbers measure app+DB
  *logic* latency, NOT production concurrency/worker tuning — that needs a non-prod Linux gunicorn box.
- Local baselines 2026-06-16: public p95 3.5ms, authed read p95 10.6ms, both 100% 200s.

### Smoke test (`scripts/smoke_test.py`, added 2026-06-16)
Stdlib-only HTTP smoke over the real WSGI stack — the Phase 3 regression gate. Logs in, hits the main
read pages + the write paths through the refactored layer (SACRED chart save; appointment
create→cancel→delete). Refuses a prod-looking `BASE_URL`. Run against a local instance:
`BASE_URL=http://127.0.0.1:5000 python scripts/smoke_test.py` (11/11, zero 5xx as of 2026-06-16).
Note: the default admin (`admin@dental.com`/`admin123`) must be `status:approved`+`is_active:true` to
pass the Phase 4 login gate.

## Environment Variables (.env)
```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=<random-string>
MONGO_URI=mongodb://localhost:27017/dental_portal
TIMEZONE=Asia/Manila
DEFAULT_CURRENCY=PHP
```

## Default Admin Account
Created on first run if no users exist:
- Email: admin@dental.com
- Password: admin123
- Role: dentist

## Known Issues / TODO (as of v3)
- Patient detail may fail on legacy data with flat (non-nested) structures — `_ensure_nested()` handles this
- `appointments.html` has its own nav bar separate from `base.html` — should eventually be unified
- Role-based access **foundation enforced (Phase 4, 2026-06-15):** `login_required`/`admin_required`
  cover all routes (admin blueprint fully admin-gated); login enforces an account lifecycle gate
  (`account_block_reason` — approved-only + `is_active`, legacy users grandfathered); and
  `role_required(*roles)` + `ROLE_ADMIN/DENTIST/STAFF` constants exist in `blueprints/utils/` as the
  multi-staff seam (admins implicitly satisfy any role). The **staff** role isn't functionally used
  yet — the full **multi-staff membership + roles** design (permission matrix, access codes,
  admin-panel shape) is spec'd in TODO.md; build against that when implementing.
- The "offline version" is decided as an **online-first PWA** (single source of truth) + an optional
  read-only offline cache; two-way sync was rejected. See TODO.md.
- User dropdown has a single **Account** link → `main.settings` (`templates/settings.html`):
  account info + profile (name/specialty) update + change password. (Formerly two placeholder
  `#` links labeled Profile/Settings; collapsed to one Account link 2026-06-15.)

## Deployment
### Render (current)
- Push to GitHub → Render auto-deploys
- Set env vars in Render dashboard: SECRET_KEY, MONGO_URI, FLASK_ENV=production
- render.yaml is included for service definition
- Health check endpoint: GET /health

### AWS (LIVE)
- **Platform:** Elastic Beanstalk, Docker platform — config in `.elasticbeanstalk/config.yml`
- **Application:** `mydentalportal`  |  **Environment:** `mydentalportal-env`  |  **Region:** `ap-southeast-1` (Singapore)
- **Database:** MongoDB Atlas (`dental-portal-cluster`), DB **`dental_portal_showcase`** via the
  scoped user **`dps_app`** (`readWrite` on that DB only — cannot touch prod).
- **Deploy command:** `eb deploy mydentalportal-env` (run from project root; deploys the current git HEAD, so commit first)
- **Container:** `Dockerfile` builds the image; gunicorn binds `0.0.0.0:8000` (EB reads the `EXPOSE 8000` line). Runs as unprivileged `appuser`.
- **Env vars for the container:** live env is set via EB environment properties (`eb setenv` / `eb printenv`
  is authoritative). `.env.docker` (git-ignored) is a local mirror = the scoped `dps_app` showcase URI.
  `.dockerignore` keeps `.env*` and secrets out of the image build context.
- Requires the EB CLI (installed) and AWS credentials configured on the deploying machine.
- Future (not yet done): ECS Fargate / App Runner migration, S3 + CloudFront for static/photos.

### Database environments & credentials (hardened 2026-06-15)
One Atlas cluster (`dental-portal-cluster`), exactly two databases — each accessed by its own
least-privilege user (no shared admin on any deployed host):
- **`dental_portal_prod`** — real PHI (Render). User **`dpp_app`** (`readWrite` on this DB only).
  Render's `MONGO_URI` is set in the Render dashboard (env var, `sync:false`).
- **`dental_portal_showcase`** — demo data (AWS EB). User **`dps_app`** (`readWrite` on this DB only).
- The shared admin **`jaspherramos98ADMIN`** is for maintenance ONLY and lives in git-ignored
  **`.env.atlas-admin`** (cluster scope). No deployed host uses it. Rotate it there.
- **Maintenance scripts:** `scripts/db_inventory.py`, `db_copy.py`, `db_drop.py`, `db_test_user.py`
  (read the URI from `.env.atlas-admin` by default; never hardcode creds). Atlas DB-user management
  is control-plane only (UI/Admin API) — the driver cannot `createUser`.

## How to Run Locally
```bash
# Activate venv
.\venv\Scripts\Activate   # Windows
source venv/bin/activate   # Mac/Linux

# Install deps
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Edit .env with your MONGO_URI

# Run
python app.py
# Open http://localhost:5000
```

## Testing (added 2026-06-15, Phase 3)
```bash
pip install -r requirements-dev.txt   # pytest + mongomock (+ setuptools<81)
pytest                                # runs tests/ ; ~1s, no DB/network needed
```
- **Hermetic by design:** tests do NOT import `app.py` (it runs `init_database()` real
  DB writes at import). `tests/conftest.py` builds a minimal Flask app and points the shared
  `mongo` singleton at an in-memory **mongomock** DB, then registers the *real* `charts_bp`
  plus stub `auth`/`patients` blueprints (so `url_for` redirects resolve). No live cluster is
  ever touched.
- **Coverage so far (the highest-risk-to-regress paths):**
  `tests/test_access_control.py` — `is_admin`, `verify_patient_access`, `user_clinic_ids`,
  `login_required`, `admin_required`. `tests/test_charts.py` — the SACRED chart's default FDI
  structure + the save route contract (auth, 404/403, persistence, read-only field stripping,
  both URL aliases).
- **Note:** `mongomock 4.1.2` imports `pkg_resources`, removed in setuptools 81+, so
  `requirements-dev.txt` pins `setuptools<81`.
