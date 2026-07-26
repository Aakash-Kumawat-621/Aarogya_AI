# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder: install all Python dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip

# ── Install CPU-only torch FIRST (saves ~600MB vs GPU wheel) ──────────────────
# Lambda has no GPU — CPU wheel is mandatory and much smaller
RUN pip install \
        torch==2.3.1+cpu \
        torchvision==0.18.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu \
    --target /build/deps

# ── Install everything else (skip torch/torchvision — already installed) ──────
RUN grep -vE "^torch==|^torchvision==" requirements.txt > /tmp/requirements_no_torch.txt && \
    pip install \
        --target /build/deps \
        --retries 5 \
        -r /tmp/requirements_no_torch.txt

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
