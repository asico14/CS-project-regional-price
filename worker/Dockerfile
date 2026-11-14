# Built from the repository root (see docker-compose.yml), because the
# worker runs the Django code of the web service.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_DIR=/app/web

WORKDIR /app

COPY web/requirements.txt web-requirements.txt
COPY worker/requirements.txt worker-requirements.txt
RUN pip install --no-cache-dir -r web-requirements.txt -r worker-requirements.txt

COPY web/ web/
COPY worker/ worker/

CMD ["python", "worker/bot.py"]
