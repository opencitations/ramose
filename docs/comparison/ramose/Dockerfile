FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY pyproject.toml .
COPY ramose ramose
RUN pip install --no-cache-dir ".[sparql-anything]" \
 && python -c "import pysparql_anything"

WORKDIR /app
COPY docs/comparison/ramose/oc.hf /app/oc.hf
COPY docs/comparison/ramose/articles.csv /app/articles.csv
COPY docs/comparison/ramose/addon.py /app/addon.py
COPY docs/comparison/ramose/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8081
ENTRYPOINT ["/app/entrypoint.sh"]
