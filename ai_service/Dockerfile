FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

# 1 worker: each worker would load its own copy of TensorFlow (lots of RAM)
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8001"]