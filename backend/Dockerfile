FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for PostgreSQL client libs and key-based Ansible SSH.
# sshpass is intentionally NOT installed — use SSH keys only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    openssh-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# ansible-core + ansible-runner for Celery worker (Phase 6 execution).
# Host SSH keys are mounted at runtime — never copied into the image.
RUN pip install "ansible-core>=2.16,<2.18" "ansible-runner>=2.3,<3"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
