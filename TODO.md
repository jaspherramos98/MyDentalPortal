# MyDentalPortal — Project TODO

> Production medical software. Patient health data (PHI) is involved. Every change
> must preserve confidentiality, integrity, and access control.
>
> **GOAL: make this a fully deployable, production-level app and architecture.**
>
> **Working list — open items only.** Completed and now-live work has been removed;
> see git history for the full record (Phases 0–5: settings page, host config, data &
> credential hygiene, test suite + repository layer Pass 1 + schema validation, access
> enforcement, mobile responsiveness — all DONE; security pen-test, hardening, AWS go-live).
>
> **This list is ordered by execution flow, not by theme.** Items are sequenced so each
> step de-risks or unblocks the next. Each phase notes *why it sits here*. Items marked
> *(independent)* have no dependency and can be pulled forward as quick wins.

---

## 🟢 Now — testing phase (pre-broad-release)

> Still in deployed **testing**: only the owner + tester(s) can access the app. Phases 0–5
> (foundations — security/data hygiene, test net + repository layer + schema validation, access
> enforcement, mobile) are DONE. Remaining work below takes the app from "works for us" to
> "production-grade ops + sound architecture."

### Phase 6 — Load / performance testing (Vegeta) — feeds the Render Starter decision
> Vegeta harness lives in `loadtest/` (added 2026-06-16). Baselines captured locally (public p95
> 3.5ms, authed read p95 10.6ms, both 100% 200s). **⚠️ PHI SAFETY: never run load against Render
> `dental_portal_prod`.** Target **local** or AWS **showcase** only; load-test read-only GETs.
- [ ] **Use results to size the deploy — BLOCKED on a Linux gunicorn target.** ⚠️ Local runs use the
      **Flask dev server (single-threaded)**; gunicorn is Unix-only and won't run on Windows, so the
      baselines measure app+DB *logic* latency under serialized load, NOT production concurrency or
      `--workers/--threads`. To validate worker count + the Render cold-start / Starter call with real
      numbers, run Vegeta against a **non-prod Linux gunicorn** box (never prod). No clean target right
      now (AWS showcase is HTTP-only + being torn down) — revisit when a staging env exists, or accept
      the Render Starter upgrade as a product decision regardless (already non-negotiable for clinic
      use per the Decision record below).

### Phase 7 — Operational maturity (production-readiness gates BEFORE broad release / Tier 3)
> The security/access/test/schema **foundations are in place** (Phases 0–4). These are the operational
> gaps between "works for us" and "production-grade ops." CI is GREEN; finish the repo pass under it.
- [ ] **Make CI a required check** — GitHub branch protection on `main` so a red suite **blocks merges**
      (until then the workflow only *signals*, it can't stop a push). *(Repo Settings → Branches →
      protect `main` → require the CI check.)* Owner/manual, one-time.
- [x] **Repository Pass 2 (mechanical) — DONE 2026-06-17.** Migrated all raw `mongo.db` queries into
      `blueprints/repositories/`. Makes the multi-staff access swap a true single-seam change.
      **Migrated:** appointments ✅, treatments ✅, users ✅ (2026-06-16) · **uploads** ✅
      (`repositories/uploads.py`: GridFS blobs + `prescriptions` + `patient_files`) · **main** dashboard
      + **reports** ✅ (aggregation helpers added to clinics/patients/appointments/treatments repos)
      (2026-06-17). Zero `mongo.db` left in `uploads.py`/`main.py`/`reports.py`. +14 repo tests
      (76 total, all green).
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
  **Render serves HTTPS for free** (auto-provisioned/renewed certs), so the PWA's HTTPS prerequisite is
  already met *on Render* — no Cloudflare / certbot / ALB needed. Don't invest in HTTPS on AWS EB.
  → **All PWA / standalone-app work targets the Render deployment.**
- **Free-tier spin-down (15 min idle, ~50s cold start):**
  - *Testing phase (now):* leave Render free tier as-is — only owner + tester use it.
  - *Production / broad release:* move to **Render Starter (~$7/mo, no spin-down)** — non-negotiable for
    clinic use. A keep-alive ping is a brittle stopgap, NOT a production answer.
  - **Why paid beats relying on the PWA:** the SW cache only loads the app *shell* instantly; the first
    *data* request still waits the full cold start. PWA masks the cold start cosmetically but can't fix
    data latency — only no-spin-down does. They stack; paid is the fix, PWA is the bonus.
- [ ] **(Broad-release gate)** Upgrade Render to Starter before opening the app beyond the tester.

---

## 🟡 Future Roadmap 1 (near-term)

**Recommended build order** (identity/access first, external intake last — Phase 3 architecture
hardening and Phase 4 access enforcement are the prerequisites for #2):

1. **Standalone app (online-first PWA) + token auth** — single source of truth in MongoDB;
   one installable codebase for phone + PC. The **token-auth** piece (JWT/API token alongside
   the current session-cookie auth) is the same identity layer multi-staff needs.
   **Sequence decided (2026-06-15): PWA installability FIRST (slice 1a DONE); token auth deferred to
   build alongside multi-staff (#2).**
   - [ ] (Phase 2, only if connectivity is flaky) **Read-only offline cache** via a PWA
         service worker — last-loaded data stays *viewable* offline; editing needs a
         connection. NOT two-way sync.
2. **Multi-staff clinic membership + roles** — **build before booking.** Restructures access
   (`owner_id` → membership), roles, permissions, and the audit log that everything leans on.
   Full spec in the detail section below. *(Prereqs: Phase 3 + Phase 4, both DONE.)*
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
