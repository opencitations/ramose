FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git default-jdk-headless \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "ramose[sparql-anything] @ git+https://github.com/opencitations/ramose.git@737240b80d5d286e7053241d2aa28ba9323557aa" \
 && python -c "import pysparql_anything"

WORKDIR /app
COPY oc.hf /app/oc.hf
COPY articles.csv /app/articles.csv
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8081
ENTRYPOINT ["/app/entrypoint.sh"]
