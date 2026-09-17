FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir "rdfproxy @ https://github.com/acdh-oeaw/rdfproxy/archive/refs/tags/v0.11.0.tar.gz" "fastapi[standard]==0.136.3"

COPY app.py ./app.py

EXPOSE 8086
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8086"]
