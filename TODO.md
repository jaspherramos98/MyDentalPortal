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
  - ⚠️ **Found while doing this — patient field-name drift (latent bug, NOT yet fixed):** the create
        form writes `medical_history.conditions` but `ensure_nested` creates `medical_conditions`;
        create reads birthday from `f.get('birthdate')` while edit uses `f.get('birthday')`; create
        writes `minor_info` while `ensure_nested` also lists `guardian_info`. Not renamed (would risk
        the detail template). Decide a canonical field set and reconcile form/template/schema as a
        focused follow-up before broad release.
- [ ] **Re-run the smoke test** after the refactor — confirm no behavioral regression. *(Local/pre-deploy;
      refactor+schema are behavior-preserving for valid input, covered by 42 tests. Not yet deployed.)*

### Phase 4 — Access enforcement (foundation for multi-staff; rests on Phase 3)
> Enforce on the **refactored** service layer so checks live in centralized enforcement points
> (one place, not decorators scattered per route) — exactly what multi-staff swaps into. Tests
> from Phase 3 catch regressions from the behavior change.
- [ ] **Enforce role-based access** (dentist / staff / admin) — `admin_required` exists in
      `blueprints/utils/` but isn't applied broadly yet.

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
