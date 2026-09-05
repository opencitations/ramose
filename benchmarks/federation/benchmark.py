# SPDX-FileCopyrightText: 2026 Arcangelo Massari <arcangelo.massari@unibo.it>
#
# SPDX-License-Identifier: ISC

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote

import requests
from scipy.stats import bootstrap

BENCHMARK_DIR = Path(__file__).resolve().parent
SNAPSHOT_MANIFEST = BENCHMARK_DIR / "snapshots.json"
HOST_DATA_DIR = BENCHMARK_DIR / "data"
CONTAINER_DATA_DIR = Path("/data")
SAMPLE_RELATIVE_PATH = Path("benchmark/sample.csv")
SAMPLE_PATH = CONTAINER_DATA_DIR / SAMPLE_RELATIVE_PATH
RAW_RESULTS_PATH = Path("/results/raw.csv")
ENVIRONMENT_PATH = Path("/results/environment.json")
SUMMARY_PATH = Path("/results/summary.csv")
BASE_URL = "http://ramose:8080/benchmark"
V1_BASE_URL = "http://ramose-v1:8081/benchmark"
INDEX_ENDPOINT = "http://index:7001"
META_ENDPOINT = "http://meta:8890/sparql"
MINIMUM_FREE_BYTES = 380_000_000_000
REQUEST_TIMEOUT_SECONDS = 320
STRATEGIES = ("service", "orchestration")
CONCURRENCY_LEVELS = (1, 4, 16)
REPETITIONS = 10
BOOTSTRAP_RESAMPLES = 10_000
HTTP_OK = 200
SAMPLES_PER_BAND = 20
REFERENCE_BAND_BOUNDS = (10, 50, 100)
SAMPLE_QUERY_PAGE_SIZE = 200
BANDS = ("0", "1-9", "10-49", "50-99", "100+")


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
    ready_file: str
    parts: tuple[ArchivePart, ...]


@dataclass(frozen=True)
class Sample:
    doi: str
    omid: str
    expected_reference_count: int


@dataclass(frozen=True)
class NormalizedResponse:
    doi: str
    title: str
    omid: str
    references: tuple[str, ...]
    reference_count: int


@dataclass(frozen=True)
class Measurement:
    doi: str
    strategy: str
    repetition: int
    concurrency: int
    latency_ms: float
    response_bytes: int
    started_ns: int
    finished_ns: int


@dataclass(frozen=True)
class Batch:
    strategy: str
    repetition: int
    concurrency: int
    base_url: str
    expected: dict[tuple[str, str], NormalizedResponse]


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
                ready_file=cast("str", dataset["ready_file"]),
                parts=parts,
            )
        )
    return tuple(datasets)


def reference_band(count: int) -> str:
    if count == 0:
        return "0"
    if count < REFERENCE_BAND_BOUNDS[0]:
        return "1-9"
    if count < REFERENCE_BAND_BOUNDS[1]:
        return "10-49"
    if count < REFERENCE_BAND_BOUNDS[2]:
        return "50-99"
    return "100+"


def read_samples(path: Path) -> tuple[Sample, ...]:
    with path.open(newline="", encoding="utf-8") as file:
        return tuple(
            Sample(
                doi=row["doi"],
                omid=row["omid"],
                expected_reference_count=int(row["expected_reference_count"]),
            )
            for row in csv.DictReader(file)
        )


def sparql_rows(endpoint: str, query: str) -> list[dict[str, str]]:
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "text/csv"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def meta_candidates(limit: int, offset: int) -> list[tuple[str, str]]:
    query = f"""PREFIX datacite: <http://purl.org/spar/datacite/>
PREFIX literal: <http://www.essepuntato.it/2010/06/literalreification/>

SELECT DISTINCT ?doi ?omid
FROM <https://w3id.org/oc/meta/>
WHERE {{
  ?identifier datacite:usesIdentifierScheme datacite:doi ;
              literal:hasLiteralValue ?doi .
  ?omid datacite:hasIdentifier ?identifier .
}}
ORDER BY STR(?doi) STR(?omid)
LIMIT {limit}
OFFSET {offset}
"""  # noqa: S608
    return [(row["doi"], row["omid"]) for row in sparql_rows(META_ENDPOINT, query)]


def reference_counts(omids: list[str]) -> dict[str, int]:
    values = " ".join(f"<{omid}>" for omid in omids)
    query = f"""PREFIX cito: <http://purl.org/spar/cito/>

SELECT ?omid (COUNT(DISTINCT ?reference) AS ?reference_count)
WHERE {{
  VALUES ?omid {{ {values} }}
  OPTIONAL {{
    ?citation a cito:Citation ;
              cito:hasCitingEntity ?omid ;
              cito:hasCitedEntity ?reference .
  }}
}}
GROUP BY ?omid
"""
    return {row["omid"]: int(row["reference_count"]) for row in sparql_rows(INDEX_ENDPOINT, query)}


def select_samples() -> tuple[Sample, ...]:
    selected: dict[str, list[Sample]] = {band: [] for band in BANDS}
    seen_dois: set[str] = set()
    offset = 0
    while any(len(samples) < SAMPLES_PER_BAND for samples in selected.values()):
        candidates = meta_candidates(SAMPLE_QUERY_PAGE_SIZE, offset)
        if not candidates:
            missing = {
                band: SAMPLES_PER_BAND - len(samples)
                for band, samples in selected.items()
                if len(samples) < SAMPLES_PER_BAND
            }
            message = f"The fixed snapshots do not contain enough samples: {missing}"
            raise RuntimeError(message)
        counts = reference_counts([omid for _, omid in candidates])
        for doi, omid in candidates:
            band = reference_band(counts[omid])
            if doi in seen_dois or len(selected[band]) >= SAMPLES_PER_BAND:
                continue
            selected[band].append(Sample(doi, omid, counts[omid]))
            seen_dois.add(doi)
        offset += len(candidates)
    return tuple(sample for band in BANDS for sample in selected[band])


def sample() -> None:
    if SAMPLE_PATH.is_file():
        return
    samples = select_samples()
    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(Sample.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(selected_sample) for selected_sample in samples)


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


def prepare() -> None:
    datasets = read_manifest(SNAPSHOT_MANIFEST)
    pending = [
        dataset for dataset in datasets if not (HOST_DATA_DIR / dataset.directory / dataset.ready_file).is_file()
    ]
    if pending:
        free_bytes = shutil.disk_usage(HOST_DATA_DIR.parent).free
        if free_bytes < MINIMUM_FREE_BYTES:
            message = f"prepare requires {MINIMUM_FREE_BYTES} free bytes; found {free_bytes}"
            raise RuntimeError(message)
    for dataset in pending:
        prepare_dataset(dataset, HOST_DATA_DIR)


def request_strategy(base_url: str, strategy: str, doi: str) -> tuple[int, bytes, float, int, int]:
    url = f"{base_url.rstrip('/')}/{strategy}/{quote(doi, safe='')}"
    started_ns = time.perf_counter_ns()
    response = requests.get(url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT_SECONDS)
    finished_ns = time.perf_counter_ns()
    return response.status_code, response.content, (finished_ns - started_ns) / 1_000_000, started_ns, finished_ns


def normalize_response(content: bytes) -> NormalizedResponse:
    value = json.loads(content)
    if not isinstance(value, list) or not value or any(not isinstance(row, dict) for row in value):
        message = "The response must be a non-empty JSON array of objects"
        raise ValueError(message)
    rows = cast("list[dict[str, object]]", value)
    doi_values = {str(row["doi"]) for row in rows}
    title_values = {str(row["title"]) for row in rows}
    omid_values = {str(row["omid"]) for row in rows}
    count_values = {int(cast("int | str", row["reference_count"])) for row in rows}
    if any(len(values) != 1 for values in (doi_values, title_values, omid_values, count_values)):
        message = "Identity, title, and count must be constant across response rows"
        raise ValueError(message)
    reference_values = {str(row["references"]) for row in rows}
    if len(reference_values) != 1:
        message = "References must be constant across response rows"
        raise ValueError(message)
    serialized_references = reference_values.pop()
    references = tuple(sorted(reference for reference in serialized_references.split("|") if reference))
    return NormalizedResponse(
        doi=doi_values.pop(),
        title=title_values.pop(),
        omid=omid_values.pop(),
        references=references,
        reference_count=count_values.pop(),
    )


def validated_responses(
    samples: tuple[Sample, ...], base_url: str, v1_base_url: str
) -> dict[tuple[str, str], NormalizedResponse]:
    responses = {}
    for sample in samples:
        current = {}
        for strategy in STRATEGIES:
            status, content, _, _, _ = request_strategy(base_url, strategy, sample.doi)
            if status != HTTP_OK:
                message = f"{strategy} returned HTTP {status} for {sample.doi}"
                raise RuntimeError(message)
            current[strategy] = normalize_response(content)
        status, content, _, _, _ = request_strategy(v1_base_url, "service", sample.doi)
        if status != HTTP_OK:
            message = f"RAMOSE v1 returned HTTP {status} for {sample.doi}"
            raise RuntimeError(message)
        v1_response = normalize_response(content)
        if current["service"] != current["orchestration"] or current["service"] != v1_response:
            message = f"Strategies diverge for {sample.doi}"
            raise RuntimeError(message)
        response = current["service"]
        if response.doi != sample.doi or response.omid != sample.omid:
            message = f"DOI or OMID diverges for {sample.doi}"
            raise RuntimeError(message)
        if response.reference_count != sample.expected_reference_count:
            message = f"Reference count diverges for {sample.doi}"
            raise RuntimeError(message)
        for strategy in STRATEGIES:
            responses[(sample.doi, strategy)] = current[strategy]
    return responses


def measure(sample: Sample, batch: Batch) -> Measurement:
    status, content, latency_ms, started_ns, finished_ns = request_strategy(batch.base_url, batch.strategy, sample.doi)
    if status != HTTP_OK:
        message = f"{batch.strategy} returned HTTP {status} for {sample.doi}"
        raise RuntimeError(message)
    if normalize_response(content) != batch.expected[(sample.doi, batch.strategy)]:
        message = f"{batch.strategy} diverged during measurement for {sample.doi}"
        raise RuntimeError(message)
    return Measurement(
        doi=sample.doi,
        strategy=batch.strategy,
        repetition=batch.repetition,
        concurrency=batch.concurrency,
        latency_ms=latency_ms,
        response_bytes=len(content),
        started_ns=started_ns,
        finished_ns=finished_ns,
    )


def execute_batch(
    samples: tuple[Sample, ...],
    batch: Batch,
) -> list[Measurement]:
    with ThreadPoolExecutor(max_workers=batch.concurrency) as executor:
        return list(executor.map(lambda sample: measure(sample, batch), samples))


def write_measurements(path: Path, measurements: list[Measurement]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(Measurement.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(measurement) for measurement in measurements)


def environment_description() -> dict[str, object]:
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": os.environ["RAMOSE_BENCHMARK_HOST"],
        "images": json.loads(os.environ["RAMOSE_BENCHMARK_IMAGES"]),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ramose_commit": os.environ["RAMOSE_BENCHMARK_COMMIT"],
    }


def run() -> None:
    samples = read_samples(SAMPLE_PATH)
    expected = validated_responses(samples, BASE_URL, V1_BASE_URL)
    for strategy in STRATEGIES:
        execute_batch(samples, Batch(strategy, 0, 1, BASE_URL, expected))
    measurements: list[Measurement] = []
    write_measurements(RAW_RESULTS_PATH, measurements)
    ENVIRONMENT_PATH.write_text(
        json.dumps(environment_description(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for concurrency in CONCURRENCY_LEVELS:
        for repetition in range(1, REPETITIONS + 1):
            for strategy in STRATEGIES if repetition % 2 else reversed(STRATEGIES):
                batch = Batch(strategy, repetition, concurrency, BASE_URL, expected)
                measurements.extend(execute_batch(samples, batch))
                write_measurements(RAW_RESULTS_PATH, measurements)


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def batch_throughput(rows: list[Measurement]) -> float:
    duration_seconds = (max(row.finished_ns for row in rows) - min(row.started_ns for row in rows)) / 1_000_000_000
    return len(rows) / duration_seconds


def summarize_group(
    concurrency: int,
    band: str,
    rows: list[Measurement],
) -> dict[str, int | float | str]:
    by_strategy = {
        strategy: sorted(
            (row for row in rows if row.strategy == strategy),
            key=lambda row: (row.repetition, row.doi),
        )
        for strategy in STRATEGIES
    }
    service_latencies = [row.latency_ms for row in by_strategy["service"]]
    orchestration_latencies = [row.latency_ms for row in by_strategy["orchestration"]]
    confidence_interval = bootstrap(
        (service_latencies, orchestration_latencies),
        lambda service, orchestration: statistics.median(orchestration) / statistics.median(service),
        paired=True,
        vectorized=False,
        n_resamples=BOOTSTRAP_RESAMPLES,
        confidence_level=0.95,
        method="percentile",
        rng=20260905,
    ).confidence_interval
    result: dict[str, int | float | str] = {
        "concurrency": concurrency,
        "reference_band": band,
        "requests_per_strategy": len(service_latencies),
        "service_median_ms": statistics.median(service_latencies),
        "service_p95_ms": quantile(service_latencies, 0.95),
        "orchestration_median_ms": statistics.median(orchestration_latencies),
        "orchestration_p95_ms": quantile(orchestration_latencies, 0.95),
        "latency_ratio_v2_to_service": statistics.median(orchestration_latencies)
        / statistics.median(service_latencies),
        "latency_ratio_ci95_low": float(confidence_interval.low),
        "latency_ratio_ci95_high": float(confidence_interval.high),
        "service_throughput_rps": "",
        "orchestration_throughput_rps": "",
    }
    if band == "all":
        for strategy in STRATEGIES:
            batches: dict[int, list[Measurement]] = {}
            for row in by_strategy[strategy]:
                batches.setdefault(row.repetition, []).append(row)
            result[f"{strategy}_throughput_rps"] = statistics.mean(
                batch_throughput(batch) for batch in batches.values()
            )
    return result


def summarize() -> None:
    samples = read_samples(SAMPLE_PATH)
    sample_by_doi = {sample.doi: sample for sample in samples}
    with RAW_RESULTS_PATH.open(newline="", encoding="utf-8") as file:
        rows = [
            Measurement(
                doi=row["doi"],
                strategy=row["strategy"],
                repetition=int(row["repetition"]),
                concurrency=int(row["concurrency"]),
                latency_ms=float(row["latency_ms"]),
                response_bytes=int(row["response_bytes"]),
                started_ns=int(row["started_ns"]),
                finished_ns=int(row["finished_ns"]),
            )
            for row in csv.DictReader(file)
        ]
    summary = []
    for concurrency in sorted({row.concurrency for row in rows}):
        concurrency_rows = [row for row in rows if row.concurrency == concurrency]
        summary.append(summarize_group(concurrency, "all", concurrency_rows))
        for band in BANDS:
            band_rows = [
                row
                for row in concurrency_rows
                if reference_band(sample_by_doi[row.doi].expected_reference_count) == band
            ]
            summary.append(summarize_group(concurrency, band, band_rows))
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAMOSE federation benchmark")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, function in (
        ("prepare", prepare),
        ("sample", sample),
        ("run", run),
        ("summarize", summarize),
    ):
        commands.add_parser(command).set_defaults(function=function)
    return parser.parse_args()


if __name__ == "__main__":  # pragma: no cover
    arguments = parse_arguments()
    arguments.function()
