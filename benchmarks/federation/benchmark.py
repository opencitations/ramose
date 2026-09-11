# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote, unquote

import requests

csv.field_size_limit(sys.maxsize)
BENCHMARK_DIR = Path(__file__).resolve().parent
SNAPSHOT_MANIFEST = BENCHMARK_DIR / "snapshots.json"
SPECIFICATION = BENCHMARK_DIR / "operations.hf"
HOST_DATA_DIR = BENCHMARK_DIR / "data"
CONTAINER_DATA_DIR = Path("/data")
ORDER_SEED = 20260905
BASE_URL = "http://ramose:8080/benchmark"
INDEX_ENDPOINT = "http://index:7001"
INDEX_CONTROL = "http://index:7002"
META_ENDPOINT = "http://meta:7001/sparql"
META_CONTROL = "http://meta:7002"
BACKEND_CONTROLS = (INDEX_CONTROL, META_CONTROL)
MINIMUM_FREE_BYTES = 380_000_000_000
REQUEST_TIMEOUT_SECONDS = 180
VALIDATION_TIMEOUT_SECONDS = 900
SAMPLING_TIMEOUT_SECONDS = 900
STRATEGIES = ("service", "orchestration")
CONCURRENCY_LEVELS = (1, 16)
REPETITIONS = 3
HTTP_OK = 200
CLIENT_TIMEOUT_STATUS = 0
BACKEND_IDLE_SECONDS = 15
SAMPLES_PER_BAND = 5
SAMPLE_QUERY_PAGE_SIZE = 100
BAND_BOUNDS = (10, 100, 1000)
BANDS = ("1-9", "10-99", "100-999", "1000-9999")
MAX_VENUE_OMIDS = 10000
MAX_VENUE_WORKS = 100_000
PREFIXES = """PREFIX cito: <http://purl.org/spar/cito/>
PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>
PREFIX frbr: <http://purl.org/vocab/frbr/core#>
PREFIX fabio: <http://purl.org/spar/fabio/>
"""


@dataclass(frozen=True)
class ArchivePart:
    name: str
    url: str
    size: int
    md5: str


@dataclass(frozen=True)
class Dataset:
    name: str
    directory: str
    ready_files: dict[str, int]
    parts: tuple[ArchivePart, ...]


@dataclass(frozen=True)
class Sample:
    issn: str
    omids: str
    expected_work_count: int

    @property
    def omid_count(self) -> int:
        return len(self.omids.split("|"))

    @property
    def band(self) -> str:
        for bound, band in zip(BAND_BOUNDS, BANDS[:-1], strict=True):
            if self.omid_count < bound:
                return band
        return BANDS[-1]


@dataclass(frozen=True)
class Validation:
    issn: str
    strategy: str
    status: int
    latency_ms: float
    response_bytes: int
    equivalent: bool
    backend_requests: int
    backend_request_bytes: int
    backend_response_bytes: int
    backend_latency_ms: float
    backend_errors: int


@dataclass(frozen=True)
class Measurement:
    concurrency: int
    issn: str
    strategy: str
    repetition: int
    status: int
    latency_ms: float
    response_bytes: int
    started_ns: int
    finished_ns: int
    equivalent: bool


@dataclass(frozen=True)
class Response:
    omids: tuple[str, ...]
    relations: tuple[tuple[str, str, str], ...]
    works: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]


Expected = dict[str, Response]


def read_manifest(path: Path) -> tuple[Dataset, ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    datasets = []
    for raw_dataset in value["datasets"]:
        dataset = cast("dict[str, object]", raw_dataset)
        raw_parts = cast("list[dict[str, object]]", dataset["parts"])
        parts = tuple(
            ArchivePart(
                name=cast("str", part["name"]),
                url=cast("str", part["url"]),
                size=cast("int", part["size"]),
                md5=cast("str", part["md5"]),
            )
            for part in raw_parts
        )
        datasets.append(
            Dataset(
                name=cast("str", dataset["name"]),
                directory=cast("str", dataset["directory"]),
                ready_files=cast("dict[str, int]", dataset["ready_files"]),
                parts=parts,
            )
        )
    return tuple(datasets)


def read_samples(path: Path) -> tuple[Sample, ...]:
    with path.open(newline="", encoding="utf-8") as file:
        return tuple(
            Sample(issn=row["issn"], omids=row["omids"], expected_work_count=int(row["expected_work_count"]))
            for row in csv.DictReader(file)
        )


def sparql_rows(endpoint: str, query: str) -> list[dict[str, str]]:
    response = requests.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "text/csv"},
        timeout=SAMPLING_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    if response.status_code != HTTP_OK or (
        "X-SQL-State" in response.headers and response.headers["X-SQL-State"] != "00000"
    ):
        message = f"Incomplete SPARQL response from {endpoint}: {response.status_code}"
        raise RuntimeError(message)
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def issn_page(limit: int, after: str | None) -> list[str]:
    cursor_filter = f"FILTER(STR(?issn) > {json.dumps(after)})" if after else ""
    query = f"""{PREFIXES}
SELECT ?issn
FROM <https://w3id.org/oc/meta/id/>
WHERE {{
  ?identifier datacite:usesIdentifierScheme datacite:issn ; literal:hasLiteralValue ?issn .
  {cursor_filter}
}}
ORDER BY STR(?issn)
LIMIT {limit}
"""  # noqa: S608
    return sorted({row["issn"] for row in sparql_rows(META_ENDPOINT, query)})


def resolved_omids(issns: list[str]) -> dict[str, set[str]]:
    values = " ".join(
        f"{json.dumps(issn)} {json.dumps(issn)}^^<http://www.w3.org/2001/XMLSchema#string>" for issn in issns
    )
    query = f"""{PREFIXES}
SELECT DISTINCT (STR(?issn) AS ?value) ?omid
FROM <https://w3id.org/oc/meta/br/>
FROM <https://w3id.org/oc/meta/id/>
WHERE {{
  VALUES ?issn {{ {values} }}
  ?venue_identifier datacite:usesIdentifierScheme datacite:issn ; literal:hasLiteralValue ?issn .
  ?venue datacite:hasIdentifier ?venue_identifier .
  {{ ?omid frbr:partOf ?venue . }}
  UNION {{ ?omid frbr:partOf/frbr:partOf ?venue . }}
  UNION {{ ?omid frbr:partOf/frbr:partOf/frbr:partOf ?venue . }}
  UNION {{ ?omid frbr:partOf/frbr:partOf/frbr:partOf/frbr:partOf ?venue . }}
  ?omid a fabio:JournalArticle .
}}
"""  # noqa: S608
    omids: dict[str, set[str]] = {issn: set() for issn in issns}
    for row in sparql_rows(META_ENDPOINT, query):
        omids[row["value"]].add(row["omid"])
    return omids


def incoming_counts(candidates: dict[str, set[str]]) -> dict[str, int]:
    values = " ".join(f"({json.dumps(issn)} <{omid}>)" for issn, omids in candidates.items() for omid in omids)
    query = f"""{PREFIXES}
SELECT ?issn (COUNT(DISTINCT ?citing) AS ?count)
WHERE {{
  VALUES (?issn ?omid) {{ {values} }}
  ?citation a cito:Citation ; cito:hasCitedEntity ?omid ; cito:hasCitingEntity ?citing .
}}
GROUP BY ?issn
"""
    counts = dict.fromkeys(candidates, 0)
    counts.update({row["issn"]: int(row["count"]) for row in sparql_rows(INDEX_ENDPOINT, query)})
    return counts


def select_samples(progress_path: Path) -> tuple[Sample, ...]:
    selected: dict[str, list[Sample]] = {band: [] for band in BANDS}
    offset = 0
    after = None
    while any(len(samples) < SAMPLES_PER_BAND for samples in selected.values()):
        print(f"Sampling venues at offset {offset}...", flush=True)  # noqa: T201
        issns = issn_page(SAMPLE_QUERY_PAGE_SIZE, after)
        if not issns:
            missing = {
                band: SAMPLES_PER_BAND - len(samples)
                for band, samples in selected.items()
                if len(samples) < SAMPLES_PER_BAND
            }
            message = f"The fixed snapshots do not contain enough venue samples: {missing}"
            raise RuntimeError(message)
        candidates = {
            issn: omids for issn, omids in resolved_omids(issns).items() if omids and len(omids) < MAX_VENUE_OMIDS
        }
        counts = incoming_counts(candidates) if candidates else {}
        for issn, omids in candidates.items():
            sample = Sample(issn, "|".join(sorted(omids)), counts[issn])
            if len(selected[sample.band]) < SAMPLES_PER_BAND and sample.expected_work_count < MAX_VENUE_WORKS:
                selected[sample.band].append(sample)
        offset += len(issns)
        after = issns[-1]
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(
            json.dumps(
                {
                    "offset": offset,
                    "after": after,
                    "samples": [asdict(row) for rows in selected.values() for row in rows],
                }
            ),
            encoding="utf-8",
        )
        print(  # noqa: T201
            f"Selected venue samples per band: { {band: len(rows) for band, rows in selected.items()} }",
            flush=True,
        )
    return tuple(sample for band in BANDS for sample in selected[band])


def write_samples(sample_path: Path, samples: tuple[Sample, ...]) -> None:
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(Sample.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(selected_sample) for selected_sample in samples)


def sample(sample_path: Path) -> None:
    progress_path = sample_path.with_suffix(".progress.json")
    samples = select_samples(progress_path)
    write_samples(sample_path, samples)
    progress_path.unlink()


def file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_part(part: ArchivePart, destination: Path) -> None:
    downloaded = destination.stat().st_size if destination.exists() else 0
    if downloaded > part.size:
        message = f"{destination} is larger than the fixed size"
        raise ValueError(message)
    if downloaded < part.size:
        headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}
        mode = "ab" if downloaded else "wb"
        with requests.get(part.url, headers=headers, stream=True, timeout=(30, 60)) as response:
            if downloaded and response.status_code != requests.codes.partial_content:
                message = f"The server did not resume {part.url}"
                raise RuntimeError(message)
            response.raise_for_status()
            with destination.open(mode) as file:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    file.write(block)
    if destination.stat().st_size != part.size:
        message = f"Size mismatch for {destination}"
        raise ValueError(message)
    actual_md5 = file_md5(destination)
    if actual_md5 != part.md5:
        message = f"MD5 mismatch for {destination}: {actual_md5}"
        raise ValueError(message)


def prepare_dataset(dataset: Dataset, data_dir: Path) -> None:
    dataset_dir = data_dir / dataset.directory
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for part in dataset.parts:
        download_part(part, dataset_dir / part.name)
    first_part = dataset_dir / dataset.parts[0].name
    subprocess.run(["7z", "t", str(first_part)], check=True)  # noqa: S603, S607
    subprocess.run(["7z", "x", "-y", str(first_part), f"-o{dataset_dir}"], check=True)  # noqa: S603, S607
    for part in dataset.parts:
        (dataset_dir / part.name).unlink()


def dataset_is_ready(dataset: Dataset, data_dir: Path) -> bool:
    for name, minimum_size in dataset.ready_files.items():
        path = data_dir / dataset.directory / name
        if not path.is_file() or path.stat().st_size < minimum_size:
            return False
    return True


def prepare() -> None:
    spec_path = HOST_DATA_DIR / "benchmark/operations.hf"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SPECIFICATION, spec_path)
    datasets = read_manifest(SNAPSHOT_MANIFEST)
    pending = [dataset for dataset in datasets if not dataset_is_ready(dataset, HOST_DATA_DIR)]
    if pending:
        free_bytes = shutil.disk_usage(HOST_DATA_DIR.parent).free
        if free_bytes < MINIMUM_FREE_BYTES:
            message = f"prepare requires {MINIMUM_FREE_BYTES} free bytes; found {free_bytes}"
            raise RuntimeError(message)
    for dataset in pending:
        prepare_dataset(dataset, HOST_DATA_DIR)


def set_backend_label(label: str) -> None:
    for control in BACKEND_CONTROLS:
        requests.post(f"{control}/label", json={"label": label}, timeout=10).raise_for_status()


def drain_backend_records() -> list[dict[str, object]]:
    records = []
    for control in BACKEND_CONTROLS:
        response = requests.get(f"{control}/records", timeout=60)
        response.raise_for_status()
        records.extend(response.json())
    return records


def wait_backend_idle() -> None:
    while True:
        time.sleep(BACKEND_IDLE_SECONDS)
        active = []
        for control in BACKEND_CONTROLS:
            response = requests.get(f"{control}/status", timeout=10)
            response.raise_for_status()
            active.append(response.json()["active"])
        if active == [0, 0]:
            return


def backend_totals(records: list[dict[str, object]]) -> tuple[int, int, int, float, int]:
    return (
        len(records),
        sum(cast("int", record["request_bytes"]) for record in records),
        sum(cast("int", record["response_bytes"]) for record in records),
        sum(cast("float", record["latency_ms"]) for record in records),
        sum(cast("int", record["status"]) >= requests.codes.bad_request for record in records),
    )


def request_strategy(
    strategy: str, sample: Sample, timeout: int = REQUEST_TIMEOUT_SECONDS
) -> tuple[int, bytes, float, int, int]:
    url = f"{BASE_URL}/{strategy}/{quote(quote(sample.issn, safe=''), safe='')}"
    started_ns = time.perf_counter_ns()
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    except requests.Timeout:
        finished_ns = time.perf_counter_ns()
        return CLIENT_TIMEOUT_STATUS, b"", (finished_ns - started_ns) / 1_000_000, started_ns, finished_ns
    finished_ns = time.perf_counter_ns()
    return response.status_code, response.content, (finished_ns - started_ns) / 1_000_000, started_ns, finished_ns


def normalize(content: bytes) -> Response:
    rows = json.loads(content)
    if not isinstance(rows, list) or not rows:
        message = "Expected resolved article rows, including when no citations exist"
        raise ValueError(message)
    omids = set()
    relations = set()
    works: dict[str, set[tuple[str, ...]]] = {}
    for row in rows:
        if not row["omid"] or bool(row["citation"]) != bool(row["citing"]):
            message = "Each citation must have both a cited and a citing resource"
            raise ValueError(message)
        if not row["citation"] and row["metadata"]:
            message = "A row without a citation cannot contain citing work metadata"
            raise ValueError(message)
        omids.add(row["omid"])
        if row["citation"]:
            relations.add((row["citation"], row["omid"], row["citing"]))
            facts = works.setdefault(row["citing"], set())
            facts.update(
                tuple(unquote(part) for part in fact.split(";")) for fact in row["metadata"].split("|") if fact
            )
    return Response(
        tuple(sorted(omids)),
        tuple(sorted(relations)),
        tuple((work, tuple(sorted(facts))) for work, facts in sorted(works.items())),
    )


def normalized_response(status: int, content: bytes) -> Response | None:
    if status != HTTP_OK:
        return None
    try:
        return normalize(content)
    except ValueError:
        return None


def matches_sample(normalized: Response, sample: Sample) -> bool:
    return normalized.omids == tuple(sample.omids.split("|")) and len(normalized.works) == sample.expected_work_count


def validate(samples: tuple[Sample, ...]) -> tuple[Expected, list[Validation], list[dict[str, object]]]:
    expected: Expected = {}
    validations: list[Validation] = []
    backend_records: list[dict[str, object]] = []
    for position, sample in enumerate(samples, 1):
        print(  # noqa: T201
            f"Validating {position}/{len(samples)}: {sample.issn}, "
            f"articles={sample.omid_count}, citing works={sample.expected_work_count}",
            flush=True,
        )
        reference: Response | None = None
        for strategy in STRATEGIES:
            set_backend_label(f"validation:{strategy}:{sample.issn}")
            status, content, latency_ms, _, _ = request_strategy(strategy, sample, timeout=VALIDATION_TIMEOUT_SECONDS)
            wait_backend_idle()
            set_backend_label("")
            request_records = drain_backend_records()
            backend_records.extend(request_records)
            backend = backend_totals(request_records)
            normalized = normalized_response(status, content)
            equivalent = normalized is not None and matches_sample(normalized, sample)
            if equivalent and reference is None:
                reference = normalized
            elif equivalent and normalized != reference:
                message = f"Strategies diverge for {sample.issn}"
                raise RuntimeError(message)
            validations.append(
                Validation(
                    sample.issn,
                    strategy,
                    status,
                    latency_ms,
                    len(content),
                    equivalent,
                    *backend,
                )
            )
        if reference is None:
            message = f"No valid reference response for {sample.issn}"
            raise RuntimeError(message)
        expected[sample.issn] = reference
    return expected, validations, backend_records


def measure(sample: Sample, strategy: str, concurrency: int, repetition: int, expected: Expected) -> Measurement:
    status, content, latency_ms, started_ns, finished_ns = request_strategy(strategy, sample)
    return Measurement(
        concurrency=concurrency,
        issn=sample.issn,
        strategy=strategy,
        repetition=repetition,
        status=status,
        latency_ms=latency_ms,
        response_bytes=len(content),
        started_ns=started_ns,
        finished_ns=finished_ns,
        equivalent=normalized_response(status, content) == expected[sample.issn],
    )


def execute_batch(
    samples: tuple[Sample, ...], strategy: str, concurrency: int, repetition: int, expected: Expected
) -> list[Measurement]:
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        return list(executor.map(lambda sample: measure(sample, strategy, concurrency, repetition, expected), samples))


def write_rows(path: Path, rows: list[Validation] | list[Measurement]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(type(rows[0]).__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def environment_description() -> dict[str, object]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": os.environ["RAMOSE_BENCHMARK_HOST"],
        "images": json.loads(os.environ["RAMOSE_BENCHMARK_IMAGES"]),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ramose_commit": os.environ["RAMOSE_BENCHMARK_COMMIT"],
        "snapshots": json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8")),
        "order_seed": ORDER_SEED,
        "repetitions": REPETITIONS,
        "concurrency_levels": CONCURRENCY_LEVELS,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "validation_timeout_seconds": VALIDATION_TIMEOUT_SECONDS,
    }


def shuffled(samples: tuple[Sample, ...], repetition: int) -> tuple[Sample, ...]:
    ordered = list(samples)
    random.Random(ORDER_SEED + repetition).shuffle(ordered)  # noqa: S311
    return tuple(ordered)


def strategies_for(repetition: int) -> tuple[str, ...]:
    return STRATEGIES if repetition % 2 else tuple(reversed(STRATEGIES))


def validated_sample(
    sample_path: Path, result_dir: Path
) -> tuple[tuple[Sample, ...], Expected, list[Validation], list[dict[str, object]]]:
    archive_path = sample_path.with_suffix(".validated.json")
    reused = archive_path.exists()
    if reused:
        print(f"Reusing validation from {archive_path}", flush=True)  # noqa: T201
        archive = json.loads(archive_path.read_text(encoding="utf-8"))
        samples = tuple(Sample(**row) for row in archive["samples"])
        expected = {
            issn: Response(
                tuple(response["omids"]),
                tuple(tuple(relation) for relation in response["relations"]),
                tuple((work, tuple(tuple(fact) for fact in facts)) for work, facts in response["works"]),
            )
            for issn, response in archive["expected"].items()
        }
        validations = [Validation(**row) for row in archive["validations"]]
        backend_records = archive["backend_records"]
    else:
        if not sample_path.exists():
            sample(sample_path)
        samples = read_samples(sample_path)
        print(f"Validating {len(samples)} samples...", flush=True)  # noqa: T201
        expected, validations, backend_records = validate(samples)
        archive = {
            "samples": [asdict(row) for row in samples],
            "expected": {issn: asdict(response) for issn, response in expected.items()},
            "validations": [asdict(row) for row in validations],
            "backend_records": backend_records,
            "source": {
                "result_dir": str(result_dir),
                "environment": environment_description(),
                "specification": SPECIFICATION.read_text(encoding="utf-8"),
            },
        }
        temporary_path = archive_path.with_suffix(".tmp")
        temporary_path.write_text(json.dumps(archive) + "\n", encoding="utf-8")
        temporary_path.replace(archive_path)
    (result_dir / "validation_source.json").write_text(
        json.dumps({"archive": str(archive_path), "reused": reused, **archive["source"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (result_dir / "expected.json").write_text(json.dumps(archive["expected"], indent=2) + "\n", encoding="utf-8")
    write_samples(result_dir / "sample.csv", samples)
    return samples, expected, validations, backend_records


def write_run_metadata(result_dir: Path) -> None:
    shutil.copyfile(SPECIFICATION, result_dir / "operations.hf")
    shutil.copyfile(BENCHMARK_DIR / "compose.yaml", result_dir / "compose.yaml")
    (result_dir / "environment.json").write_text(
        json.dumps(environment_description(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_backend_records(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "backend",
        "label",
        "method",
        "request_bytes",
        "status",
        "response_bytes",
        "latency_ms",
        "started_ns",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def run(sample_path: Path, result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=False)
    samples, expected, validations, backend_records = validated_sample(sample_path, result_dir)
    write_rows(result_dir / "validation.csv", validations)
    write_backend_records(result_dir / "backend.csv", backend_records)
    write_run_metadata(result_dir)
    print("Warming up both strategies...", flush=True)  # noqa: T201
    for strategy in STRATEGIES:
        wait_backend_idle()
        set_backend_label(f"warmup:{strategy}")
        execute_batch(samples, strategy, max(CONCURRENCY_LEVELS), 0, expected)
        wait_backend_idle()
        set_backend_label("")
        backend_records.extend(drain_backend_records())
    measurements: list[Measurement] = []
    for concurrency in CONCURRENCY_LEVELS:
        for repetition in range(1, REPETITIONS + 1):
            ordered = shuffled(samples, repetition)
            for strategy in strategies_for(repetition):
                wait_backend_idle()
                set_backend_label(f"measurement:{concurrency}:{repetition}:{strategy}")
                measurements.extend(execute_batch(ordered, strategy, concurrency, repetition, expected))
                wait_backend_idle()
                set_backend_label("")
                backend_records.extend(drain_backend_records())
                write_rows(result_dir / "raw.csv", measurements)
                write_backend_records(result_dir / "backend.csv", backend_records)
                print(  # noqa: T201
                    f"Measured concurrency {concurrency}, {strategy}, repetition {repetition}; "
                    f"{len(measurements)} measurements saved.",
                    flush=True,
                )


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def read_measurements(path: Path) -> list[Measurement]:
    with path.open(newline="", encoding="utf-8") as file:
        return [
            Measurement(
                concurrency=int(row["concurrency"]),
                issn=row["issn"],
                strategy=row["strategy"],
                repetition=int(row["repetition"]),
                status=int(row["status"]),
                latency_ms=float(row["latency_ms"]),
                response_bytes=int(row["response_bytes"]),
                started_ns=int(row["started_ns"]),
                finished_ns=int(row["finished_ns"]),
                equivalent=row["equivalent"] == "True",
            )
            for row in csv.DictReader(file)
        ]


def read_validations(path: Path) -> list[Validation]:
    with path.open(newline="", encoding="utf-8") as file:
        return [
            Validation(
                issn=row["issn"],
                strategy=row["strategy"],
                status=int(row["status"]),
                latency_ms=float(row["latency_ms"]),
                response_bytes=int(row["response_bytes"]),
                equivalent=row["equivalent"] == "True",
                backend_requests=int(row["backend_requests"]),
                backend_request_bytes=int(row["backend_request_bytes"]),
                backend_response_bytes=int(row["backend_response_bytes"]),
                backend_latency_ms=float(row["backend_latency_ms"]),
                backend_errors=int(row["backend_errors"]),
            )
            for row in csv.DictReader(file)
        ]


def summarize_group(
    concurrency: int, band: str, rows: list[Measurement], validations: list[Validation]
) -> dict[str, object]:
    result: dict[str, object] = {
        "concurrency": concurrency,
        "band": band,
        "requests_per_strategy": len([row for row in rows if row.strategy == STRATEGIES[0]]),
    }
    for strategy in STRATEGIES:
        group = [row for row in rows if row.strategy == strategy]
        latencies = [row.latency_ms for row in group if row.equivalent]
        backend_requests = [row.backend_requests for row in validations if row.strategy == strategy]
        result[f"{strategy}_success_rate"] = len(latencies) / len(group)
        result[f"{strategy}_median_ms"] = statistics.median(latencies) if latencies else ""
        result[f"{strategy}_p95_ms"] = quantile(latencies, 0.95) if latencies else ""
        result[f"{strategy}_mean_backend_requests"] = statistics.mean(backend_requests)
        result[f"{strategy}_max_backend_requests"] = max(backend_requests)
    return result


def summarize(sample_path: Path, result_dir: Path) -> None:
    band_by_issn = {sample.issn: sample.band for sample in read_samples(sample_path)}
    measurements = read_measurements(result_dir / "raw.csv")
    validations = read_validations(result_dir / "validation.csv")
    summary = []
    for concurrency in CONCURRENCY_LEVELS:
        level_rows = [row for row in measurements if row.concurrency == concurrency]
        for band in (*BANDS, "all"):
            band_rows = [row for row in level_rows if band in ("all", band_by_issn[row.issn])]
            band_validations = [row for row in validations if band in ("all", band_by_issn[row.issn])]
            if band_rows:
                summary.append(summarize_group(concurrency, band, band_rows, band_validations))
    with (result_dir / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


def main() -> None:  # pragma: no cover
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sample_path = CONTAINER_DATA_DIR / "venue_sample.csv"
    result_dir = Path("/results") / run_id
    run(sample_path, result_dir)
    summarize(result_dir / "sample.csv", result_dir)


if __name__ == "__main__":  # pragma: no cover
    main()
