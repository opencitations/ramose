FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "ramose @ git+https://github.com/opencitations/ramose.git@v2.4.0"

WORKDIR /app
COPY oc.hf /app/oc.hf
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8081
ENTRYPOINT ["/app/entrypoint.sh"]
