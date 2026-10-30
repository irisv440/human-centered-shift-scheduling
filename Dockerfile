FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/

CMD ["uvicorn", "main:app", "--app-dir", "/app/api", "--host", "0.0.0.0", "--port", "8000"]