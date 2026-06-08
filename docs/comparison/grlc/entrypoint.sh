#!/bin/sh
if [ -n "$GITHUB_TOKEN" ]; then
  sed -i "s|^github_access_token = .*|github_access_token = $GITHUB_TOKEN|" /app/config.ini
fi
exec grlc-server --port=8082
