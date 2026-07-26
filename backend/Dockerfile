# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Builder
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /build

# Install gcc/g++ and development headers for compilation
RUN yum install -y gcc gcc-c++ make cmake && yum clean all

COPY requirements.txt .

RUN pip install --upgrade pip

# Install dependencies using --prefer-binary so pip prefers pre-compiled wheels
# over building from source for packages like numkong/lightgbm/albucore
RUN grep -vE "^torch==|^torchvision==" requirements.txt > /tmp/req_no_torch.txt && \
    pip install \
        --target /build/deps \
        --prefer-binary \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.3.1+cpu \
        torchvision==0.18.1+cpu \
        -r /tmp/req_no_torch.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Final Lambda image
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/var/task

WORKDIR /var/task

COPY --from=builder /build/deps ./
COPY app/ ./app/

CMD ["app.main.handler"]
