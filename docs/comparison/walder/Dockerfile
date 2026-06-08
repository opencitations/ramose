FROM node:18-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g walder@4.1.4

WORKDIR /app
COPY config.yaml /app/config.yaml
COPY views /app/views

EXPOSE 8089
CMD ["walder", "-c", "/app/config.yaml", "-p", "8089", "-l", "info"]
