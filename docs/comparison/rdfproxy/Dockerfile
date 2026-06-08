FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir "rdfproxy==0.10.1" "fastapi[standard]==0.136.3"

COPY app.py ./app.py

EXPOSE 8086
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8086"]
