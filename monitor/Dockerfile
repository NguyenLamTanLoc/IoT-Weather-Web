FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY monitor/requirements.txt monitor/requirements.txt
RUN pip install --no-cache-dir -r monitor/requirements.txt

COPY manage.py .
COPY config/ config/
COPY monitor/ monitor/

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 150"]

