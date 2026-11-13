FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CONFIG_DIR=/app/config \
    TELEGRAM_SESSION_PATH=/data/telegram.session \
    INTERACTIVE_AUTH=false \
    LOG_FORMAT=json

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /data

COPY config ./config
COPY src ./src

CMD ["python", "-m", "vinnytsia_monitor"]
