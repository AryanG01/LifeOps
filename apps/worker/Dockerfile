FROM python:3.11-slim
WORKDIR /app

COPY packages/core packages/core
COPY packages/connectors packages/connectors
COPY apps/worker apps/worker

RUN pip install --no-cache-dir \
    -e packages/core \
    -e packages/connectors \
    -e apps/worker

CMD ["python", "-m", "worker.main"]
