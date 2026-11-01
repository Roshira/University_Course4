# Один образ для трьох воркерів: generator.py / consumer.py / db_monitor.py
# (конкретний скрипт задається через command у docker-compose.yml). Контекст збірки: ./services
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY workers/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/ ./common/
COPY workers/*.py ./
EXPOSE 8000
CMD ["python", "generator.py"]
