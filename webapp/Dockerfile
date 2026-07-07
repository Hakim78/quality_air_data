FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.6 "uvicorn[standard]==0.32.1" psycopg2-binary==2.9.10

COPY app.py .
COPY static ./static

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
