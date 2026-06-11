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
│   │   ├── main.py           # Dashboard, index
│   │   ├── clinics.py        # Clinic CRUD + search + currency (PHP/USD)
│   │   ├── patients.py       # Patient CRUD, PDA form fields, pagination
│   │   ├── charts.py         # *** SACRED — dental chart, DO NOT modify chart logic ***
│   │   ├── treatments.py     # Treatment records CRUD + JSON API
│   │   └── appointments.py   # Appointments CRUD + calendar API
│   ├── models/
│   │   └── __init__.py
│   └── utils/
│       └── __init__.py
├── static/
│   ├── css/main.css
│   └── js/
│       └── main.js
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
Patients are stored with nested dicts. Always use `_ensure_nested(patient)` before template rendering.
Key nested paths: `personal_info`, `contact_info`, `dental_history`, `medical_history`,
`medical_history.allergies`, `medical_history.women_health`, `medical_history.conditions`,
`referral_info`, `minor_info`, `insurance_info`.

### Import Pattern
All blueprints import mongo from `extensions.py`:
```python
from extensions import mongo
```
NEVER import from `app.py` or `app_factory.py` (deleted).

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
It has its own nav bar, CSS, and inline JavaScript. The calendar uses the `/appointments/api` endpoints.
Clinic and patient data are passed from Flask and rendered via Jinja `{% for %}` loops.

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
- Role-based access (dentist vs staff vs admin) is prepared in the user model but not enforced yet
- Profile and Settings pages in the user dropdown are placeholder links (#)

## Deployment
### Render (current)
- Push to GitHub → Render auto-deploys
- Set env vars in Render dashboard: SECRET_KEY, MONGO_URI, FLASK_ENV=production
- render.yaml is included for service definition
- Health check endpoint: GET /health

### AWS (LIVE)
- **Platform:** Elastic Beanstalk, Docker platform — config in `.elasticbeanstalk/config.yml`
- **Application:** `mydentalportal`  |  **Environment:** `mydentalportal-env`  |  **Region:** `ap-southeast-1` (Singapore)
- **Database:** MongoDB Atlas (`dental-portal-cluster`)
- **Deploy command:** `eb deploy mydentalportal-env` (run from project root; deploys the current git HEAD, so commit first)
- **Container:** `Dockerfile` builds the image; gunicorn binds `0.0.0.0:8000` (EB reads the `EXPOSE 8000` line). Runs as unprivileged `appuser`.
- **Env vars for the container:** `.env.docker` (git-ignored — holds SECRET_KEY + Atlas MONGO_URI; NEVER commit it). `.dockerignore` keeps `.env*` and secrets out of the image build context.
- Requires the EB CLI (installed) and AWS credentials configured on the deploying machine.
- Future (not yet done): ECS Fargate / App Runner migration, S3 + CloudFront for static/photos.

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
