#!/bin/sh
set -e

mkdir -p /app/state
python -m ramose --auth-db /app/.auth --token-create demo | tail -n1 > /app/state/token

exec python -m ramose -s /app/oc.hf -w 0.0.0.0:8081 --auth-db /app/.auth \
  --backend-auth "http://meta-basic:3030/sparql=Basic $(printf demo:demo | base64)" \
  --backend-auth "http://meta-digest:3030/sparql=Digest demo:demo"
