# One image for every Python service (api, worker, simulators). Build context: repo root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY services/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY packages/nimbus_core /opt/nimbus_core
RUN pip install /opt/nimbus_core

COPY services /app/services
COPY eval /app/eval
COPY data /app/data

ENV NIMBUS_DATA_DIR=/app/data
