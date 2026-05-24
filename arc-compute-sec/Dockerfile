FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARC_LOG_DIR=/app/logs \
    FRONTEND_DIR=/frontend \
    API_HOST=0.0.0.0 \
    PORT=8080 \
    ENABLE_LIVE_CHAIN=0

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "-m", "services.api"]
