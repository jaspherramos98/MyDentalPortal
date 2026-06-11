# Dockerfile — containerizes the MyDentalPortal Flask app.
# Built once here, runnable anywhere: Elastic Beanstalk (now), and later
# ECS Fargate / App Runner with no changes. See CLAUDE.md for the AWS plan.

FROM python:3.11-slim

# Faster, cleaner Python in containers: no .pyc files, unbuffered stdout so
# logs show up immediately in CloudWatch.
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

# Gunicorn listens on 8000 inside the container. Elastic Beanstalk reads this
# EXPOSE line to know which port to route traffic to.
EXPOSE 8000

# Production WSGI server (never `flask run`/Werkzeug in prod). 3 workers is a
# sane default for a small free-tier instance.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "app:app"]
