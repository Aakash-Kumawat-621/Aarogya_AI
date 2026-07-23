FROM public.ecr.aws/lambda/python:3.11

# ── System dependencies ────────────────────────────────────────────────────────
RUN dnf install -y \
    gcc \
    gcc-c++ \
    libgomp \
    && dnf clean all

# ── Set working directory ──────────────────────────────────────────────────────
WORKDIR ${LAMBDA_TASK_ROOT}

# ── Install Python dependencies ────────────────────────────────────────────────
COPY requirements.txt .

# Install torch CPU version first (smaller than GPU, required for Lambda)
RUN pip install --no-cache-dir torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Install all other packages
RUN pip install --no-cache-dir -r requirements.txt

# Download scispaCy medical NLP model
RUN pip install --no-cache-dir \
    https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz

# ── Copy application code ──────────────────────────────────────────────────────
COPY app/ ${LAMBDA_TASK_ROOT}/app/

# ── Lambda handler ─────────────────────────────────────────────────────────────
CMD ["app.main.handler"]
