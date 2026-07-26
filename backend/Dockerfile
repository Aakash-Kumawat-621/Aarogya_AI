# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder: install all Python dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10 AS builder

# Env flags — keep image lean
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Copy only requirements first (layer cache — only re-runs if requirements change)
COPY requirements.txt .

# Install into a local dir so we can copy selectively to the final stage
RUN pip install --upgrade pip && \
    pip install --target /build/deps -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Final Lambda image
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/var/task

WORKDIR /var/task

# Copy installed packages from builder
COPY --from=builder /build/deps ./

# Copy application code
COPY app/ ./app/

# Lambda entry point — Mangum wraps FastAPI
CMD ["app.main.handler"]
