FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# Migrations run automatically on startup (alembic upgrade head)
COPY alembic.ini ./
COPY migrations ./migrations

# data/ (database, backups, logs) is a volume — see docker-compose.yml
RUN mkdir -p /app/data
VOLUME ["/app/data"]

CMD ["python", "-m", "eventum_hq"]
