# Dockerfile — portable container for the MyDentalPortal Flask app.
# Production runs on Render's native Python runtime (not this image); keep this
# as a ready-to-run definition for any container host or a Linux staging box.

FROM python:3.11-slim

# Faster, cleaner Python in containers: no .pyc files, unbuffered stdout so
# logs show up immediately in the host's log stream.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (their own layer) so code changes don't force a
# full reinstall on every rebuild — much faster iteration.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY . .

# Run as an unprivileged user, not root. This app handles patient data, so we
# follow least-privilege even inside the container.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Gunicorn listens on 8000 inside the container.
EXPOSE 8000

# Production WSGI server (never `flask run`/Werkzeug in prod). Same tuning as
# the Render start command (render.yaml / Procfile) — keep them in sync.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "4", "--timeout", "120", \
     "--max-requests", "400", "--max-requests-jitter", "50", "--keep-alive", "75"]
