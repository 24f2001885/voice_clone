# ==============================================================================
# VoxClone Multi-Stage Container Definition
# Target: runtime (production GPU CLI) | test (offline CPU test runner)
# ==============================================================================

FROM python:3.11-slim AS runtime

# System runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    pulseaudio-utils \
    git \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -g 1000 voxclone && \
    useradd -u 1000 -g voxclone -m -s /bin/bash voxclone

WORKDIR /app

# Layer cache: Install dependencies first
COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

# Copy project files
COPY pyproject.toml Makefile /app/
COPY migrations /app/migrations
COPY scripts /app/scripts
COPY src /app/src

# Install voxclone in editable mode without reinstalling dependencies
RUN pip install --no-deps -e .

# Environment configuration
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    HF_HUB_OFFLINE=1 \
    VOXCLONE_DATA_DIR=/app/data \
    VOXCLONE_PROFILES_DIR=/app/profiles \
    VOXCLONE_OUTPUTS_DIR=/app/outputs \
    VOXCLONE_INPUTS_DIR=/app/inputs \
    VOXCLONE_ENGINE=real

# Prepare storage directories and assign permissions
RUN mkdir -p /app/data /app/profiles /app/outputs /app/inputs /models && \
    chown -R voxclone:voxclone /app /models && \
    chmod 0700 /app/data /app/profiles /app/outputs

USER voxclone

CMD ["voxclone"]

# ==============================================================================
# Test Target: Offline, CPU-only execution with dev tools and fake engines
# ==============================================================================
FROM runtime AS test

USER root

# Install dev dependencies
RUN pip install --no-cache-dir \
    pytest>=8.0.0 \
    pytest-cov>=5.0.0 \
    pexpect>=4.9.0 \
    ruff>=0.4.0 \
    black>=24.3.0 \
    mypy>=1.9.0

COPY tests /app/tests
RUN chown -R voxclone:voxclone /app/tests

ENV VOXCLONE_ENGINE=fake \
    VOXCLONE_DATA_DIR=/tmp/voxclone-data

USER voxclone

CMD ["make", "test"]
