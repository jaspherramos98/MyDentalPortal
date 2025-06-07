#!/bin/bash

# Create these files first
touch app.py                    # Main application file
touch config.py                 # Configuration
touch models.py                 # Database models
touch requirements.txt          # Dependencies
touch .env                     # Environment variables

# Create main directories
mkdir -p app/{models,routes,utils,forms}
mkdir -p static/{css,js,images,fonts}
mkdir -p templates/{auth,dashboard,clinics,patients,charts,treatments,components}
mkdir -p uploads/{patient_photos,xrays,documents}
mkdir -p logs
mkdir -p tests
mkdir -p scripts
mkdir -p docs

# Python package files
touch app/__init__.py

# Template files
touch templates/base.html
touch templates/auth/login.html
touch templates/dashboard/index.html
touch templates/patients/list.html

# Static files
touch static/css/main.css
touch static/js/main.js