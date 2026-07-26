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

# Install gcc/g++ — required to build lightgbm, numkong, nmslib from source
RUN yum install -y gcc gcc-c++ make && yum clean all

COPY requirements.txt .

RUN pip install --upgrade pip

# Install everything in ONE pip transaction:
#   - Exclude torch/torchvision from requirements (we pin them below)
#   - Specify torch==2.3.1+cpu so ALL deps (incl. sentence-transformers)
#     see CPU torch already in the resolution and don't pull GPU torch
#   - --extra-index-url lets pip find the +cpu wheel from PyTorch's index
RUN grep -vE "^torch==|^torchvision==" requirements.txt > /tmp/req_no_torch.txt && \
    pip install \
        --target /build/deps \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.3.1+cpu \
        torchvision==0.18.1+cpu \
        -r /tmp/req_no_torch.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Final Lambda image (lean, no build tools)
# ─────────────────────────────────────────────────────────────────────────────
FROM public.ecr.aws/lambda/python:3.10

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/var/task

WORKDIR /var/task

COPY --from=builder /build/deps ./
COPY app/ ./app/

CMD ["app.main.handler"]
