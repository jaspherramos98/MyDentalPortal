# MyDentalPortal — Project TODO

> Production medical software. Patient health data (PHI) is involved. Every change
> must preserve confidentiality, integrity, and access control.
>
> **Working list — open items only.** Completed and now-live work has been removed;
> see git history for the full record (security pen-test, hardening, AWS go-live, etc.).

## 🟢 Now — testing phase (quick wins + still-owed security/deploy)

> Still in deployed **testing**: only the owner + tester(s) can access the app, so the
> security/deploy items and quick wins are grouped here as the pre-broad-release tasks.

- [ ] **Profile + Settings pages** — replace the placeholder `#` navbar dropdown links
      with real pages.
- [ ] **Enforce role-based access** (dentist / staff / admin) — `admin_required` exists in
      `blueprints/utils/` but isn't applied broadly yet. *(Foundation for multi-staff below.)*
- [ ] **Manual in-browser smoke test** with real credentials (login, CRUD, chart save,
      prescription/file upload, appointment cancel).
- [ ] **MongoDB Atlas** — confirm the connection uses TLS and a least-privilege DB user.
- [ ] Confirm strong `SECRET_KEY`, `FLASK_ENV=production`, and `ADMIN_EMAILS` are set on
      every host (Render + AWS EB).

## 🟡 Future Roadmap 1 (near-term)

**Recommended build order** (sequenced for smoother programming — identity/access first,
external intake last):

1. **Standalone app (online-first PWA) + token auth** — single source of truth in MongoDB;
   one installable codebase for phone + PC. The **token-auth** piece (JWT/API token alongside
   the current session-cookie auth) is the same identity layer multi-staff needs.
   - [ ] (Phase 2, only if connectivity is flaky) **Read-only offline cache** via a PWA
         service worker — last-loaded data stays *viewable* offline; editing needs a
         connection. NOT two-way sync.
2. **Multi-staff clinic membership + roles** — **build before booking.** Restructures access
   (`owner_id` → membership), roles, permissions, and the audit log that everything leans on.
   Full spec in the detail section below.
3. **Customer-facing booking** — **build after multi-staff.** Adds external users booking into
   clinics (dentist accept/decline + auto-routing to the correct clinic); depends on a settled
   role/clinic/permission model + the audit log, so doing it second avoids reworking
   who-can-accept / who-gets-notified. Full spec in the detail section below.

- [ ] **Terminate AWS Elastic Beanstalk** — `eb terminate mydentalportal-env`.
      Target window **~2026-07-15 to 2026-08-15** ("a month or 2"). *(Independent / time-based.)*

---

### Detail — Multi-staff: clinic membership + roles (spec'd 2026-06-11)

> Online-first means this is purely a **membership + roles** feature — NOT a sync/conflict
> problem. Simultaneous edits to the same record fall back to last-write-wins, which is fine
> for a small co-located clinic that coordinates verbally. Builds on the 🟢 "enforce
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
