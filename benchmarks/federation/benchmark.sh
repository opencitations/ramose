#!/bin/sh
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

stack_started=false
stop_stack() {
    if [ "$stack_started" = true ]; then
        docker compose down || true
    fi
}
trap stop_stack EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

rm -f \
    results/raw.csv \
    results/environment.json \
    results/summary.csv

uv run --extra benchmark python benchmark.py prepare
stack_started=true
docker compose up --build --wait

RAMOSE_BENCHMARK_COMMIT=$(git -C ../.. rev-parse HEAD)
RAMOSE_BENCHMARK_HOST=$(uname -a)
RAMOSE_BENCHMARK_IMAGES=$(docker compose images --format json | python -c 'import json, sys; print(json.dumps([json.loads(line) for line in sys.stdin if line.strip()]))')
export RAMOSE_BENCHMARK_COMMIT RAMOSE_BENCHMARK_HOST RAMOSE_BENCHMARK_IMAGES

docker compose run --rm --no-deps runner sample
docker compose run --rm --no-deps runner run
docker compose run --rm --no-deps runner summarize
