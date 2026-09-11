#!/bin/sh
# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

stack_started=false
stop_stack() {
    status=$?
    if [ "$stack_started" = true ]; then
        if [ "$status" -ne 0 ]; then
            docker compose logs --no-color >&2 || true
        fi
        docker compose down --remove-orphans || true
    fi
}
trap stop_stack EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir -p results
uv run --extra benchmark python -c 'import benchmark; benchmark.prepare()'
stack_started=true
docker compose up --build --wait --remove-orphans || {
    status=$?
    docker compose logs --no-color >&2 || true
    exit "$status"
}

for grant in \
    'GRANT SELECT ON DB.DBA.SPARQL_SINV_2 TO "SPARQL"' \
    'GRANT EXECUTE ON DB.DBA.SPARQL_SINV_IMP TO "SPARQL"'
do
    docker compose exec -T virtuoso /bin/sh -c '"$VIRTUOSO_HOME/bin/isql" 1111 dba dba VERBOSE=OFF' <<SQL
$grant;
EXIT \$IF \$EQU \$STATE OK 0 1;
SQL
done

RAMOSE_BENCHMARK_COMMIT=$(git -C ../.. rev-parse HEAD)
RAMOSE_BENCHMARK_HOST=$(uname -a)
RAMOSE_BENCHMARK_IMAGES=$(docker compose images --format json | python -c 'import json, sys; print(json.dumps([json.loads(line) for line in sys.stdin if line.strip()]))')
export RAMOSE_BENCHMARK_COMMIT RAMOSE_BENCHMARK_HOST RAMOSE_BENCHMARK_IMAGES

docker compose run --rm --no-deps --user "$(id -u):$(id -g)" runner
