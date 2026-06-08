#!/bin/sh
set -e

mkdir -p /app/state
python -m ramose --auth-db /app/.auth --token-create demo | tail -n1 > /app/state/token

exec python -m ramose -s /app/oc.hf -w 0.0.0.0:8081 --no-cache --auth-db /app/.auth
