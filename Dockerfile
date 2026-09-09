FROM python:3.13-slim

RUN pip install \
    nvflare \
    torch \
    torchvision \
    numpy \
    pandas

WORKDIR /workspace

COPY jobs/fedavg_nn/app/custom/train.py /workspace/train.py