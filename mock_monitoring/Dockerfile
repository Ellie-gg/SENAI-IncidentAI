FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /svc

COPY mock_monitoring/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/__init__.py ./app/__init__.py
COPY app/models ./app/models
COPY mock_monitoring ./mock_monitoring

EXPOSE 8081

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health', timeout=3)"

CMD ["uvicorn", "mock_monitoring.main:app", "--host", "0.0.0.0", "--port", "8081"]
