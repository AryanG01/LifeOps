FROM python:3.11-slim
WORKDIR /app

COPY packages/core packages/core
COPY packages/connectors packages/connectors
COPY apps/api apps/api

RUN pip install --no-cache-dir \
    -e packages/core \
    -e packages/connectors \
    -e apps/api

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
