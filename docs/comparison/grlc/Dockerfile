FROM python:3.12-slim

RUN pip install --no-cache-dir grlc==1.3.11

WORKDIR /app
COPY config.ini /app/config.ini
COPY queries /app/queries
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8082
ENTRYPOINT ["/app/entrypoint.sh"]
