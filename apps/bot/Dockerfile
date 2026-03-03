FROM python:3.11-slim
WORKDIR /app

COPY packages/core packages/core
COPY packages/connectors packages/connectors
COPY packages/cli packages/cli
COPY apps/bot apps/bot

RUN pip install --no-cache-dir \
    -e packages/core \
    -e packages/connectors \
    -e packages/cli \
    -e apps/bot

CMD ["python", "-m", "bot.main"]
