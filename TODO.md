# MyDentalPortal — Project TODO

> Production medical software. Patient health data (PHI) is involved. Every change
> must preserve confidentiality, integrity, and access control.
>
> **GOAL: make this a fully deployable, production-level app and architecture.**
>
> **Working list — open items only.** Completed and now-live work has been removed;
> see git history for the full record (security pen-test, hardening, AWS go-live, etc.).
>
> **This list is ordered by execution flow, not by theme.** Items are sequenced so each
> step de-risks or unblocks the next. Each phase notes *why it sits here*. Items marked
> *(independent)* have no dependency and can be pulled forward as quick wins.

---

## 🟢 Now — testing phase (pre-broad-release)

> Still in deployed **testing**: only the owner + tester(s) can access the app. The flow
> below takes the app from "works for us" to "safe + tested + sound architecture."

### Phase 0 — Quick win (independent, do anytime)
- [x] **Profile + Settings pages** — *DONE 2026-06-15.* A real `main.settings` route + `settings.html`
      already existed (account info + profile update + change password); the navbar's two duplicate
      links (both → `main.settings`) were collapsed to a single **Account** link. No `#` placeholders
      remain.

### Phase 1 — Know your ground (cheap; informs everything after it)
- [x] **Confirm host config** — *DONE 2026-06-15.* All three hosts captured (full map in memory
      `host-config-db-wiring`). Render (long-term prod) → `dental-portal` (real PHI) ✓,
      `FLASK_ENV=production` ✓, `ADMIN_EMAILS`=owner gmail ✓. AWS EB live → `dental_portal_demo`
      (NOT empty `dental_portal` as the stale `.env.docker` claims — fix the file in Phase 2).
      Local → localhost/`dental_portal`, dev key. ⚠️ Carry-ins to Phase 2: shared admin Atlas
      password is exposed (plaintext in `.env`/`.env.docker`/`eb printenv`) → rotate; `.env.docker`
      is stale → correct; AWS EB has no `ADMIN_EMAILS` (only `admin@dental.com` is admin there).
- [x] **Manual in-browser smoke test (baseline)** — *DONE 2026-06-15, PASS on Render (HTTPS).*
      Login → dashboard, appointment cancel (`PUT 200`), chart save (`POST /charts/update 200`),
      file upload (`POST …/files/add 302`), photo serve (`200`), patient detail OK. Zero 5xx.
      Re-run as a gate after Phase 2 and after Phase 3.

### Phase 2 — Data & credential hygiene (highest PHI risk) — ✅ DONE 2026-06-15
> The booby-trap DBs are renamed, every host runs on a per-DB least-privilege user, and the
> shared admin password has been rotated and moved to a local-only maintenance file.
- [x] **Renamed the booby-trap DBs.** Was: `dental-portal` (hyphen, real) vs `dental_portal`
      (underscore, empty) vs `dental_portal_demo` — one-char-apart trap. Now: `dental-portal` →
      **`dental_portal_prod`**, `dental_portal_demo` → **`dental_portal_showcase`**, empty
      `dental_portal` **dropped**. Copied via `scripts/db_copy.py` (docs + indexes + GridFS,
      verified exact counts), repointed each host, then dropped originals via `scripts/db_drop.py`.
      Cluster now holds exactly `dental_portal_prod` + `dental_portal_showcase`.
- [x] **Least-privilege Atlas users.** Render → **`dpp_app`** (`readWrite` on `dental_portal_prod`
      only). AWS EB → **`dps_app`** (`readWrite` on `dental_portal_showcase` only). Isolation
      proven (`scripts/db_test_user.py`): `dps_app` reads showcase, correctly **denied** on prod.
      No deployed host uses the shared admin anymore.
- [x] **Rotated the shared admin password** (`jaspherramos98ADMIN`) — old one had leaked into
      `.env`/`.env.docker`/`eb printenv`. Now lives ONLY in git-ignored `.env.atlas-admin` (used by
      `scripts/db_*.py`). `.env.docker` rewritten to the scoped `dps_app` showcase user (no longer
      stale, no longer carries admin). Maintenance scripts default to `.env.atlas-admin`.
- [x] **Re-verified after repointing.** Render smoke test PASS (BRETNEY + photo load from
      `dental_portal_prod`); AWS `/health` → `{"database":"connected","status":"healthy"}` on
      `dental_portal_showcase`.

### Phase 3 — Test safety net + architecture hardening (under test cover, before behavior changes)
> Tests come **before** the refactor: the service-layer refactor is the dangerous part, and a
> characterization test net lets you refactor safely instead of blind. Then harden the architecture
> while it's cheap — both items are explicitly **prerequisites for multi-staff** (Roadmap #2).
- [x] **Automated test suite — net in place (2026-06-15).** pytest + mongomock stood up
      (`requirements-dev.txt`, `pytest.ini`, `tests/conftest.py`); hermetic (no `app.py` import,
      no live DB). 23 tests pass: **(a) SACRED chart** default FDI structure + save route contract
      (auth, 404/403, persistence, read-only field stripping, both aliases) in `tests/test_charts.py`;
      **(b) access-control utils** (`is_admin`, `verify_patient_access`, `user_clinic_ids`,
      `login_required`, `admin_required`) in `tests/test_access_control.py`. This is the net for the
      refactor below — *expand it as the service layer lands.* (Routes beyond charts are not yet
      covered; add as needed.)
- [~] **Thin service/repository layer — Pass 1 DONE (2026-06-15).** Added `blueprints/repositories/`
      (`patients`, `clinics`, `charts`) of thin functions returning plain dicts. The access seam is
      centralized: `verify_patient_access`/`user_clinic_ids` (utils) now delegate to
      `patients.get_for_owner`/`clinics.owned_ids`, so every existing caller (treatments, uploads,
      patients, reports, appointments) routes through one place — multi-staff changes ONLY
      `get_for_owner` (owner_id → membership). `charts.py` inline owner-check removed (now via
      `verify_patient_access`); chart DB ops moved to `charts_repo` (SACRED shape/save-load logic
      untouched). `_ensure_nested` moved to `patients` repo. 33 tests pass + import smoke clean.
      **Pass 2 (mechanical, deferred):** migrate raw `mongo.db` queries in appointments, treatments,
      uploads, admin, reports, auth, main into repositories.
- [x] **Schema validation at the boundary — DONE (2026-06-15).** Added pydantic `PatientDoc` +
      `validate_patient` (`blueprints/models/patient.py`); patient **create** goes through
      `patient_repo.create()` → validation (guarantees nested skeleton + valid `clinic_id`, rejects
      malformed docs, preserves all extra/PDA fields via `extra="allow"`). Edit uses targeted
      dot-notation `$set` via `patient_repo.update_set()` (hardcoded keys can't malform structure).
      `pydantic==2.9.2` added to requirements. 42 tests pass.
  - ✅ **Patient field-name drift — RECONCILED (2026-06-15).** Audited create/edit forms, detail.html,
        `ensure_nested`, and `PatientDoc` against each other. Fixes: `ensure_nested` now backfills
        `medical_history.conditions` (was the dead `medical_conditions` — real latent crash on legacy
        data missing that sub-dict); removed dead `guardian_info` section from `ensure_nested` +
        `PatientDoc` (guardian fields live under `minor_info`). The `birthday`/`birthdate` difference
        is **not** a data bug — create's form *field* is `birthdate` but maps to stored
        `personal_info.birthday`; edit + detail use `birthday` consistently. Regression test added.
- [x] **Re-run the smoke test after the refactor — DONE 2026-06-16, PASS (local).** 52 unit tests pass +
      an HTTP smoke (`scripts/smoke_test.py`, stdlib-only) hit the real WSGI stack: **11/11, zero 5xx** —
      login, reads (dashboard, patients, patient detail, chart view, appointments, reports) and the
      WRITE paths through the refactored layer (SACRED chart save → `charts_repo.upsert`; appointment
      create → cancel → delete). No behavioral regression. Confirmed delete is a soft-delete
      (`is_active:false`+`deleted_at`). Re-run with `BASE_URL=http://localhost:5000 python scripts/smoke_test.py`
      against a local instance (refuses prod). ⏳ Not yet re-run against a deploy.

### Phase 4 — Access enforcement (foundation for multi-staff; rests on Phase 3)
> Enforce on the **refactored** service layer so checks live in centralized enforcement points
> (one place, not decorators scattered per route) — exactly what multi-staff swaps into. Tests
> from Phase 3 catch regressions from the behavior change.
- [x] **Enforce role-based access — DONE (2026-06-15).** Audited the full route surface: every route
      is `login_required` (only `register`/`logout`/`index` are intentionally public) and the admin
      blueprint is fully `admin_required` — coverage was already complete. Closed the real gaps:
      (1) login now enforces an account **lifecycle gate** (`account_block_reason` in `auth.py`:
      approved-only allow-list + `is_active`, legacy users grandfathered) — a deactivated/non-approved
      account can no longer log in; (2) added `role_required(*roles)` + `ROLE_ADMIN/DENTIST/STAFF`
      constants in `blueprints/utils/` as the multi-staff seam (admins implicitly satisfy any role).
      10 new tests (`tests/test_roles.py`), 52 total pass. Staff role not yet functionally used —
      that's roadmap #2 (multi-staff).

### Phase 5 — Mobile responsiveness (one codebase, responsive; desktop must not regress)
> Real-device testing surfaced mobile issues. Rule: fix via mobile-only `@media`/Bootstrap so desktop
> is unaffected; if a fix can't avoid touching desktop, confirm with owner first.
- [x] **Dental chart Save button blocked by the unsaved-changes banner — FIXED 2026-06-15.** base.html
      lifts `.save-btn` above the banner via `--unsaved-banner-h`. Improves desktop too; SACRED chart untouched.
- [x] **Appointments page mobile — FIXED 2026-06-15.** Swipeable week grid, fit-to-screen month grid,
      natural scrolling; **and** swapped the custom gradient nav for the shared Bootstrap navbar
      (hamburger on mobile, blue bar on desktop — owner-approved desktop change).
- [x] **Whole-app mobile pass — DONE 2026-06-15 (owner real-device testing).** 15 issues fixed across
      batches (all desktop-safe via `@media`/scoped selectors unless noted):
      edge-to-edge padding (central `.main-content` mobile padding); dashboard header buttons wrap +
      right-justify; patient-detail action btn-group wraps; patients-list avatar stays circular +
      removed redundant Quick Actions; dental chart header buttons wrap right + section-title bar made
      flush (no white corners) — both via base.html, SACRED file untouched; **appointments**: removed
      dead "Today" button, stats → 2×2 grid, legend moved below the grid (horizontal), sidebar toggle
      → bottom-left (no longer covers header), off-canvas sidebar bottom padding for drag-drop reach.
      *(Owner-approved desktop changes: appointments nav → shared Bootstrap navbar; stats grid + legend
      placement apply to desktop too.)* Note: patient-detail `table-sm` tables are 2-col key/value and
      fit mobile — NOT wrapped (wide list tables were already `.table-responsive`). ⏳ Owner to re-verify
      on device.
- [x] **Consistent navbar→title spacing — DONE 2026-06-15.** Added `padding-top:1.5rem` to
      `.main-content` (base.html) so every base-extending page matches the settings page's gap below the
      navbar (settings de-duped from `py-4` → `pb-4`). Desktop + mobile. (Appointments is standalone, not
      affected.)
- [x] **Appointments landscape-phone layout — DONE 2026-06-15.** Phone layout now triggers on short
      height too (`@media (max-width:768px), (max-height:500px)`); calendar forced full-width when sidebar
      off-canvas; toggle kept visible over `d-md-none`. (Landscape phones are wide >768px but short, so
      width-only breakpoint had left them on the broken desktop layout.)
- [x] **Appointments off-canvas sidebar now scrollable — FIXED 2026-06-16.** The drawer scrolls as
      ONE unit (filters → stats → patient list) on mobile + landscape. Root causes were two nested
      scrolls fighting the drawer's own scroll: `.search-box` was `position:sticky;top:0` (pinned the
      filter section, hiding everything below it) and `.patient-list` had its own
      `max-height:calc(100vh-400px);overflow-y:auto` (a nested scroll box that went *negative* on
      landscape, collapsing the list to ~0). Fix (all inside the existing phone media query, desktop
      untouched): anchored the fixed `.sidebar` to the full viewport (`top:0;bottom:0;height:auto;
      overflow-y:auto;-webkit-overflow-scrolling:touch`) and flattened the nested scrolls
      (`.sidebar .search-box{position:static}`, `.sidebar .patient-list{max-height:none;overflow:visible}`).
      Page renders 200. ⏳ Owner to re-verify drag-drop onto a date on a real phone (portrait + landscape).

### Phase 6 — Load / performance testing (Vegeta) — feeds the Render Starter decision
> We have functional (smoke) + unit (52 tests) coverage but **no load/perf testing**. Vegeta
> (constant-rate HTTP load + latency histograms) fills that gap and produces the hard numbers
> behind the broad-release gate below (cold start, gunicorn worker tuning). Harness lives in
> `loadtest/` (added 2026-06-16).
> **⚠️ PHI SAFETY RULE: never run load against Render `dental_portal_prod`.** Target **local**
> (`python app.py`) or the AWS **showcase** env only. Login is rate-limited (10/min) and all
> POSTs are CSRF-protected, so load-test **read-only GETs**; the authed runner logs in once
> (handling CSRF) and reuses the session cookie.
- [x] **Vegeta binary installed — DONE 2026-06-16.** v12.13.0 at `~/.local/bin/vegeta.exe`
      (downloaded release zip, no elevation). NOTE: use `127.0.0.1` not `localhost` in `BASE_URL` —
      Vegeta's Go resolver can fail to resolve `localhost` (`lookup localhost on 8.8.8.8:53`); harness
      defaults switched to `127.0.0.1`.
- [x] **Baseline — public endpoints — DONE 2026-06-16 (local).** `run-public.sh` @ 50 req/s × 20s:
      **100% 200s**, p50 2.2ms / p95 3.5ms / p99 4.3ms / max 42ms.
- [x] **Authed read paths — DONE 2026-06-16 (local).** `run-authed.sh` @ 30 req/s × 20s across
      dashboard, patients, patient detail, appointments: **100% 200s**, p50 7.2ms / p95 10.6ms /
      p99 13.6ms / max 41ms. DB-backed pages ~3× static but still single-digit ms; no slow endpoints.
- [ ] **Use results to size the deploy — BLOCKED on a Linux gunicorn target.** ⚠️ Local runs use the
      **Flask dev server (single-threaded)**; gunicorn is Unix-only and won't run on Windows, so the
      numbers above measure app+DB *logic* latency under serialized load, NOT production concurrency or
      `--workers/--threads`. To validate worker count + the Render cold-start / Starter call with real
      numbers, run Vegeta against a **non-prod Linux gunicorn** box (never prod). No clean target right
      now (AWS showcase is HTTP-only + being torn down) — revisit when a staging env exists, or accept
      the Render Starter upgrade as a product decision regardless (it's already non-negotiable for
      clinic use per the Decision record below).

### Phase 7 — Operational maturity (production-readiness gates BEFORE broad release / Tier 3)
> The security/access/test/schema **foundations are in place** (Phases 0–4). These are the operational
> gaps between "works for us" and "production-grade ops." Do **CI first** so the big Tier-3 features
> (multi-staff, booking) are built under a green test gate instead of blind.
- [x] **CI pipeline — pytest on push + PR (DONE 2026-06-16, verified GREEN).** `.github/workflows/ci.yml`:
      ubuntu + Python 3.11, installs `requirements-dev.txt`, runs `pytest` (hermetic — mongomock, no
      DB/network). Cancels superseded runs per ref. First run failed (bare `pytest` doesn't put the
      project root on `sys.path` → `ModuleNotFoundError: extensions`; local passed only via
      `python -m pytest`); fixed with `pythonpath = .` in `pytest.ini` (reproduced + verified in a
      `python:3.11` Docker container, then green on GitHub).
- [ ] **Make CI a required check** — GitHub branch protection on `main` so a red suite **blocks merges**
      (until then the workflow only *signals*, it can't stop a push). *(Repo Settings → Branches →
      protect `main` → require the CI check.)* Owner/manual, one-time.
- [~] **Repository Pass 2 (mechanical)** — migrate raw `mongo.db` queries into `blueprints/repositories/`.
      Carried from Phase 3; makes the multi-staff access swap a true single-seam change. Done by PR/collection:
      - [x] **appointments** (2026-06-16) — `repositories/appointments.py` (get/find_in_range/
            find_active_on_day/insert/update_set/soft_delete) + `patients.active_in_clinics`; route now
            uses appt/clinic/patient repos, zero `mongo.db` left in `appointments.py`. +5 repo tests
            (57 total), live smoke 11/11.
      - [x] **treatments** (2026-06-16) — `repositories/treatments.py` (get/list_for_patient/insert/
            update_set/delete); `treatments.py` (add/edit/mark-paid/delete/JSON-API) now uses it, zero
            `mongo.db` left. +3 repo tests (60 total), smoke 11/11 + treatments JSON API 200.
      - [x] **users** (2026-06-16) — `repositories/users.py` (get/get_by_email/create/update_set/
            list_by_status/list_all_no_password/set_status_if_pending); migrated `auth.py` (login/register),
            `admin.py` (registrations/approve/reject/users/reset-password), and `main.py` **settings**
            (get user + profile/password update). `main.py` dashboard aggregations stay for the line below.
            +4 repo tests (64 total), smoke 11/11 + /settings + /admin/registrations + /admin/users all 200.
      - [ ] uploads (files/GridFS) · [ ] main dashboard + reports (aggregations).
      *(Expand tests as each route moves.)*
- [ ] **Observability / error tracking** — capture unhandled 5xx off-box (Sentry free tier or at least
      structured logging shipped somewhere durable); Render stdout is ephemeral/not searchable. **Must-have:**
      error tracking. **Nice-to-have:** Prometheus + Grafana dashboards (latency/error-rate/throughput) —
      strong portfolio signal, pairs with the Vegeta harness.
- [ ] **DB backup + restore DRILL** — confirm a recoverable backup of `dental_portal_prod` exists (Atlas
      backups + `scripts/backup_data.py`) **and actually test a restore**. Untested backups don't count.
      *(PHI — non-negotiable before broad release.)*
- [ ] **Real load test vs a Linux gunicorn target** — see Phase 6 (blocked on a non-prod Linux box);
      needed to size `--workers/--threads` and validate the cold-start / Render-Starter call with real numbers.
- [ ] **PWA browser verification** — "Install app" prompt + Lighthouse PWA pass on the Render (HTTPS)
      deploy. Carried from Roadmap #1 slice 1a.

### Decision record — Hosting + HTTPS (settled 2026-06-13; no action until broad release)
- **Long-term host = Render**, not AWS (EB was for portfolio and is being torn down — see 🟡).
  **Render serves HTTPS for free** (auto-provisioned/renewed certs on `*.onrender.com` and custom
  domains), so the PWA's HTTPS prerequisite is already met *on Render* — no Cloudflare / certbot /
  ALB needed. Don't invest in HTTPS on AWS EB (HTTP-only and going away).
  → **All PWA / standalone-app work targets the Render deployment.**
- **Free-tier spin-down (15 min idle, ~50s cold start):**
  - *Testing phase (now):* leave Render free tier as-is. Only the owner + tester use it, so
    spin-down doesn't matter — don't even bother with a keep-alive pinger.
  - *Production / broad release:* move to **Render Starter (~$7/mo, no spin-down)** — treat as
    non-negotiable for clinic use. A keep-alive ping (`/health` every ~10 min via
    UptimeRobot/cron-job.org) is only a brittle stopgap, NOT a production answer.
  - **Why paid beats relying on the PWA:** the service-worker cache only loads the app *shell*
    instantly; the first *data* request (open a patient/chart/appointments) still waits the full
    cold start. The PWA masks the cold start cosmetically but can't fix data latency — only
    no-spin-down does. The two stack; paid is the fix, PWA is the bonus on top.
- [ ] **(Broad-release gate)** Upgrade Render to Starter before opening the app beyond the tester.

---

## 🟡 Future Roadmap 1 (near-term)

**Recommended build order** (identity/access first, external intake last — Phase 3 architecture
hardening and Phase 4 access enforcement above are the prerequisites for #2):

1. **Standalone app (online-first PWA) + token auth** — single source of truth in MongoDB;
   one installable codebase for phone + PC. The **token-auth** piece (JWT/API token alongside
   the current session-cookie auth) is the same identity layer multi-staff needs.
   **Sequence decided (2026-06-15): PWA installability FIRST (slice 1a); token auth deferred to
   build alongside multi-staff (#2).**
   - [x] **Slice 1a — installable, online-first PWA (app shell only). DONE 2026-06-15.**
         Shipped: `static/manifest.webmanifest` (+ `/manifest.webmanifest` route), brand-blue tooth
         icons via `scripts/gen_pwa_icons.py` (192/512/maskable — placeholders, replace with a designed
         icon; also fixed the `/favicon.ico 404`), `static/sw.js` (online-first: navigations network-only
         w/ `offline.html` fallback, `/static/*` cache-first, data/PHI NEVER cached) served at `/sw.js`
         with `Service-Worker-Allowed: /`, and wiring in `base.html` + `appointments.html`. 52 tests
         still pass. ⏳ **Browser verification still owed:** "Install app" prompt + Lighthouse PWA pass
         on the Render (HTTPS) deploy.
         - Out of scope (deferred): offline DATA caching, token auth, push notifications.
   - [ ] (Phase 2, only if connectivity is flaky) **Read-only offline cache** via a PWA
         service worker — last-loaded data stays *viewable* offline; editing needs a
         connection. NOT two-way sync.
2. **Multi-staff clinic membership + roles** — **build before booking.** Restructures access
   (`owner_id` → membership), roles, permissions, and the audit log that everything leans on.
   Full spec in the detail section below. *(Prereqs: Phase 3 + Phase 4 above.)*
3. **Customer-facing booking** — **build after multi-staff.** Adds external users booking into
   clinics (dentist accept/decline + auto-routing to the correct clinic); depends on a settled
   role/clinic/permission model + the audit log, so doing it second avoids reworking
   who-can-accept / who-gets-notified. Full spec in the detail section below.

- [ ] **Terminate AWS Elastic Beanstalk** — `eb terminate mydentalportal-env`.
      Target window **~2026-07-15 to 2026-08-15** ("a month or 2"). *(Independent / time-based —
      not blocked by anything above; just don't tear it down before you're confident on Render.)*

---

### Detail — Multi-staff: clinic membership + roles (spec'd 2026-06-11)

> Online-first means this is purely a **membership + roles** feature — NOT a sync/conflict
> problem. Simultaneous edits to the same record fall back to last-write-wins, which is fine
> for a small co-located clinic that coordinates verbally. Builds on the Phase 4 "enforce
> role-based access" item, and swaps cleanly because access checks are already centralized in
> `blueprints/utils/` (`verify_patient_access`, `user_clinic_ids`, `is_admin`).

**Three roles:** App Admin · Dentist (clinic owner) · Staff (assistant/receptionist).

**Onboarding:**
- [ ] App Admin approves a registering dentist *(gate already exists: `ADMIN_EMAILS` / Approvals)*.
- [ ] Dentist generates a **staff access code** → staff registers/links with it → membership row
      links staff to that dentist's clinic(s).

**Data model:**
- [ ] Add a `memberships` collection (user_id ↔ clinic_id ↔ role); change access from
      "is `owner_id` me?" to membership-based. Staff linked to a dentist get all that dentist's
      clinics (per-clinic scoping is a later extension).

**Staff permissions:**
- ✅ view/create/edit patients · full appointments · view+add+full-edit treatments ·
  **edit the dental chart** (existing save flow only — never touch chart internals) ·
  view/upload files & photos · edit clinical notes.
- 🟠 **Pricing = propose, dentist confirms:** staff may enter/edit a treatment's price
  (`amount`), but it stays **pending until a dentist confirms**. Needs a price-confirmation
  state (`price_confirmed` + who/when) and a dentist review/confirm UI.
- ❌ generate access codes / invite or manage staff (dentist-only) · create/edit/delete clinics
  or settings · **delete** patients/records (dentist/admin only — keep this default) ·
  confirm pricing (dentist-only) · app-admin functions.
- **Payments/balance ledger** (when built): staff **record payments received, append-only**;
  cannot edit/void existing entries (corrections/refunds = dentist only); everything stamped +
  shown in the dentist's activity log.

**App Admin powers (global superset of dentist abilities):**
- [ ] Approve/reject dentists (existing) AND approve/oversee staff; generate codes for any dentist.
- [ ] View every dentist + their linked staff; view/act on any clinic's data (global switch).
- [ ] Account lifecycle (activate/deactivate/suspend); role management (promote to dentist,
      grant/revoke admin, revoke/reassign staff); revoke/regenerate access codes; manage any clinic.
- Reserved to admin only: granting admin rights, approving dentists, acting across other
  dentists' data, deactivating dentist accounts.

**Admin panel shape:**
- [ ] List all registered dentists → click a dentist → dropdown of staff linked to that dentist.
      Users view shows role (dentist vs staff) + linkage.

**Audit trail / activity log (required):**
- [ ] **DB-backed `audit_log` collection** (NOT Render stdout — those stay for debugging only;
      ephemeral/monolithic/not user-scoped, don't try to organize them by dentist). Stamp records
      with `created_by` / `updated_by`; write entries with `actor_user_id`, `actor_role`, owning
      dentist/clinic, `action`, `entity_type`, `entity_id`, `timestamp`.
- [ ] **Nested viewer scope (one log, three views):** staff see none · dentist sees their own
      clinic(s)' activity (self + their staff) · **app admin sees all, grouped by dentist →
      expand → that dentist's actions + their staff's** (admin panel + activity feed).
- [ ] Build-time: **PHI hygiene** (log the action, not sensitive values) + **pagination /
      retention** policy. Same mechanism powers pricing-confirmation review and payments oversight.

---

### Detail — Customer-facing booking (FB Messenger / email integration)

> Wired to the Appointments tab. Build **after** multi-staff so it slots into a settled
> role/clinic/permission model + audit log.

- [ ] Automated email / FB Messenger page for customers.
- [ ] Customer opens a chat → welcome message + a private link only that customer can see.
- [ ] Clicking the link → customer picks an available appointment date.
- [ ] Customer enters basic personal details.
- [ ] Dentist is notified to **accept or decline**.
- [ ] If declined → message the customer a phone number to call.
- [ ] If accepted → send a link to enter medical history (one-time code so it saves
      against the right patient + personal info).
- [ ] Accepted appointments auto-added to the correct clinic's Appointments tab.

## 🔵 Far future (only when worth paying for)
- [ ] **Scaling that costs money** — Redis (accurate multi-worker rate limiting),
      load balancer + HTTPS, bigger DB tier, multi-clinic at scale, CDN / object storage.
