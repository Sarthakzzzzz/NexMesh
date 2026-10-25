FROM python:3.13-slim

ENV PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

RUN python -m pip install --no-cache-dir \
    --timeout 180 \
    --retries 10 \
    nvflare==2.9.0 \
    torch \
    torchvision \
    numpy \
    pandas

WORKDIR /workspace

COPY jobs/fedavg_nn/train.py /workspace/train.py