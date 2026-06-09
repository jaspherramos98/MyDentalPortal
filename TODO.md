# MyDentalPortal — Project TODO

> Production medical software. Patient health data (PHI) is involved. Every change
> must preserve confidentiality, integrity, and access control.

## Completed work batches

### Phase 1 — Quick fixes ✅
- [x] Fix dashboard "This Week" appointment count (was never computed in `main.py`).
      (Also excludes cancelled appointments from today/upcoming/this-week.)
- [x] Add **Tooth Extraction** appointment type (modal, filter, legend, color) — applies to
      drag-to-schedule too (shared modal); server-side enum allowlist added.
- [x] Restore the X-ray section in the dental chart (restored to original sacred layout).
- [x] Add a **Settings** page (account info, profile edit, change password).

### Phase 2 — Patient detail tabs (secure file handling) ✅
- [x] **Prescription** tab — description text + optional image, stored in MongoDB GridFS.
- [x] **Others / Files** tab — upload png/jpg/jpeg/webp/heic/pdf/docx/pages/numbers/key with
      strict validation (extension allowlist + magic-byte sniff + Pillow decode + 16MB cap +
      sanitized names). Served only via authenticated, ownership-checked, attachment-forced route.
  - [x] Ability to name / rename an uploaded file.

### Phase 3 — Hardening ✅ (see pen-test summary below)
- [x] Security audit: auth on every route, clinic-ownership checks, upload validation,
      XSS, session cookie flags, CSRF on state-changing requests.
- [~] End-to-end test of all flows — code-level/structural verification done; **manual
      browser + MongoDB smoke test still owed by the user**.

### Deployment-readiness refactor ✅
- [x] Consolidated duplicated `login_required` / `verify_patient_access` / `user_clinic_ids` /
      `is_admin` / `admin_required` into `blueprints/utils/` (single source of truth).
- [x] Removed dead `bcrypt` dependency and now-unused imports.

---

## Security pen-test summary (code-level)

Passed:
- ✅ **Upload validation** rejects PHP webshells, JS, EXE, SVG, and extension-spoofed
     files (extension allowlist + magic-byte sniff + Pillow decode). Genuine PNG/JPG/PDF pass.
- ✅ **Auth** enforced on every protected route (shared `login_required`); admin routes gated.
- ✅ **CSRF** blocks all token-less POSTs (login/register/settings/etc.).
- ✅ **Access control** via `verify_patient_access` (clinic `owner_id` match) — single shared
     helper, applied consistently to patient/treatment/prescription/file routes.
- ✅ Security headers (nosniff, X-Frame-Options DENY, Referrer-Policy) on every response.

Fixed during pen test:
- ✅ **Stored XSS** in the appointments page: `patients_json|safe` (raw `json.dumps`) let a
     patient name like `</script>…` break out of the `<script>` block. Now `patients|tojson`,
     which escapes `<`/`>`/`&`/`'` for safe embedding. (Important once the customer-facing
     booking lets outsiders supply names.)

Hardening done:
- [x] **Login rate-limiting** — Flask-Limiter on `/login` POST: 10/min, 50/hr
      (verified trips to 429). NOTE: memory store = per-worker; use Redis storage_uri
      in a multi-worker production deploy.
- [x] **Content-Security-Policy** — pragmatic CSP set (allows cdnjs + inline for now).
      Future: remove `'unsafe-inline'` by moving inline JS/handlers to static files.
- [x] **Open-redirect hardening** — CSRF/413 handlers now only honour a same-origin
      `request.referrer`, else fall back to dashboard/login.
- [x] **Logout via POST** — `/logout` is POST + CSRF; navbar links are now forms.
- [x] **Debug off in production** — `app.run` reads debug from env and is force-disabled
      when `FLASK_ENV=production`; production still runs via gunicorn anyway.

Still owed (need the live host / your action):
- [ ] **Manual in-browser smoke test** with real credentials (login, CRUD, chart save,
      prescription/file upload, appointment cancel). Automated read-only checks pass, but
      authenticated page rendering couldn't be exercised here (no valid login creds).
- [ ] Ensure MongoDB Atlas connection uses TLS and a least-privilege DB user.
- [ ] Set strong `SECRET_KEY`, `FLASK_ENV=production`, and `ADMIN_EMAILS` on the host.
- [ ] (Optional) Move rate-limiter storage to Redis for multi-worker correctness.

## Pre-deployment to-do
1. **Account verification / approval gate.** ✅ DONE
   - New registrations are saved with `status: 'pending'` and cannot log in.
   - Admins (email in `ADMIN_EMAILS`, default `admin@dental.com`, or `role: 'admin'`)
     see an **Approvals** nav link → `/admin/registrations` to approve/reject.
   - Users created before this feature (no `status`) are grandfathered as approved.
   - To make another account an admin, set the `ADMIN_EMAILS` env var (comma-separated).

2. **Security hardening (from the Phase 3 audit).**
   - [x] **CSRF protection** — Flask-WTF `CSRFProtect` enabled app-wide. Every POST form
         carries a hidden `csrf_token`; fetch() calls send `X-CSRFToken` via a wrapper.
         Invalid/missing token → JSON 400 (fetch) or flash+redirect (forms).
   - [x] **SECRET_KEY** — ProductionConfig now refuses to boot if `SECRET_KEY` is unset
         (falls back to the known dev key). Still must set a strong key on Render/AWS.
   - [ ] **Debug off in production** — `python app.py` runs `debug=True`. Production must
         run via gunicorn with `FLASK_ENV=production` (ProductionConfig already sets DEBUG=False).
         Never expose the Werkzeug debugger publicly.
   - [x] **Server-side appointment `type` allowlist** — create defaults invalid types to
         `checkup`; update rejects invalid `type`/`status`/`priority` with 400.
   - [x] **413 handler** — oversized uploads now flash a clear message and redirect back.
   - [x] Security headers (nosniff / X-Frame-Options / Referrer-Policy) added globally.
   - [x] Uploads validated by extension + magic bytes + Pillow decode; stored in GridFS;
         served only via authenticated, ownership-checked, attachment-forced routes.

---

## Post-deployment to-do (future features)
1. **Customer-facing booking (Facebook Messenger / email integration)** — connected
   directly to the Appointments tab.
   - 1.1 Automated email / FB Messenger page for customers, wired to Appointments.
   - 1.2 Customer opens a chat with the FB page → welcome message + a private link
         only that customer can see/click.
   - 1.3 Clicking the link → customer picks an available appointment date.
   - 1.4 Customer enters basic personal details.
   - 1.5 Dentist is notified (e.g. via Messenger) to **accept or decline**.
   - 1.6 If declined → page messages the customer a phone number to call for more info.
   - 1.7 If accepted → page sends a link where the customer enters medical history.
         (Likely via a one-time code so the medical history saves against the right
          patient + personal info.)
   - 1.8 Accepted appointments are added automatically to the correct clinic's
         Appointments tab.

2. **AWS deployment.**
   - 2.1 Use as many beneficial AWS services as possible within the **free tier**
         (target: Elastic Beanstalk or ECS Fargate, MongoDB Atlas, S3 for files,
          CloudFront, SES for email).
