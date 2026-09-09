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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from urllib.parse import quote

import queries
import requests
from scipy.stats import bootstrap

BENCHMARK_DIR = Path(__file__).resolve().parent
SNAPSHOT_MANIFEST = BENCHMARK_DIR / "snapshots.json"
HOST_DATA_DIR = BENCHMARK_DIR / "data"
CONTAINER_DATA_DIR = Path("/data")
ORDER_SEED = 20260905
BASE_URL = "http://ramose:8080/benchmark"
INDEX_ENDPOINT = "http://index:7001"
META_ENDPOINT = "http://meta:8890/sparql"
MINIMUM_FREE_BYTES = 380_000_000_000
REQUEST_TIMEOUT_SECONDS = 320
SAMPLING_TIMEOUT_SECONDS = 900
STRATEGIES = ("service", "orchestration")
CONCURRENCY_LEVELS = (1, 4, 16)
REPETITIONS = 10
BOOTSTRAP_RESAMPLES = 10_000
HTTP_OK = 200
SAMPLES_PER_BAND = 20
WORK_BAND_BOUNDS = (10, 50, 100)
SAMPLE_QUERY_PAGE_SIZE = 1000
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
    ready_files: dict[str, int]
    parts: tuple[ArchivePart, ...]


@dataclass(frozen=True)
class Sample:
    doi: str
    omid: str
    expected_work_count: int


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
    enriched_work_count: int
    equivalent: bool


@dataclass(frozen=True)
class Batch:
    strategy: str
    repetition: int
    concurrency: int
    base_url: str
    expected: dict[tuple[str, str], queries.Response]


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


def work_band(count: int) -> str:
    if count == 0:
        return "0"
    if count < WORK_BAND_BOUNDS[0]:
        return "1-9"
    if count < WORK_BAND_BOUNDS[1]:
        return "10-49"
    if count < WORK_BAND_BOUNDS[2]:
        return "50-99"
    return "100+"


def read_samples(path: Path) -> tuple[Sample, ...]:
    with path.open(newline="", encoding="utf-8") as file:
        return tuple(
            Sample(
                doi=row["doi"],
                omid=row["omid"],
                expected_work_count=int(row["expected_work_count"]),
            )
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


def meta_candidates(limit: int, after: str | None) -> list[tuple[str, str]]:
    cursor_filter = f"FILTER(STR(?doi) > {json.dumps(after)})" if after else ""
    query = f"""{queries.PREFIXES}
SELECT ?doi
FROM <https://w3id.org/oc/meta/id/>
WHERE {{
  ?identifier datacite:usesIdentifierScheme datacite:doi ; literal:hasLiteralValue ?doi .
  {cursor_filter}
}}
ORDER BY STR(?doi)
LIMIT {limit}
"""  # noqa: S608
    dois = sorted({row["doi"] for row in sparql_rows(META_ENDPOINT, query)})
    if not dois:
        return []
    values = " ".join(f"{json.dumps(doi)} {json.dumps(doi)}^^<http://www.w3.org/2001/XMLSchema#string>" for doi in dois)
    query = f"""{queries.PREFIXES}
SELECT DISTINCT ?doi ?omid
FROM <https://w3id.org/oc/meta/id/>
FROM <https://w3id.org/oc/meta/br/>
WHERE {{
  VALUES ?doi_value {{ {values} }}
  ?identifier datacite:usesIdentifierScheme datacite:doi ; literal:hasLiteralValue ?doi_value .
  ?omid datacite:hasIdentifier ?identifier .
  BIND(STR(?doi_value) AS ?doi)
}}
"""  # noqa: S608
    works: dict[str, set[str]] = {doi: set() for doi in dois}
    for row in sparql_rows(META_ENDPOINT, query):
        works[row["doi"]].add(row["omid"])
    return [(doi, "|".join(sorted(works[doi]))) for doi in dois]


def incoming_counts(candidates: list[tuple[str, str]]) -> dict[str, int]:
    values = " ".join(f"({json.dumps(doi)} <{omid}>)" for doi, omids in candidates for omid in omids.split("|") if omid)
    query = f"""{queries.PREFIXES}
SELECT ?doi (COUNT(DISTINCT ?citing) AS ?count)
WHERE {{ VALUES (?doi ?omid) {{ {values} }} {queries.RELATIONS} }}
GROUP BY ?doi
"""
    counts = dict.fromkeys((doi for doi, _ in candidates), 0)
    counts.update({row["doi"]: int(row["count"]) for row in sparql_rows(INDEX_ENDPOINT, query)})
    return counts


def select_samples(progress_path: Path) -> tuple[Sample, ...]:
    selected: dict[str, list[Sample]] = {band: [] for band in BANDS}
    offset = 0
    after = None
    seen_dois: set[str] = set()
    while any(len(samples) < SAMPLES_PER_BAND for samples in selected.values()):
        print(f"Sampling DOI candidates at offset {offset}...", flush=True)  # noqa: T201
        candidates = meta_candidates(SAMPLE_QUERY_PAGE_SIZE, after)
        if not candidates:
            missing = {
                band: SAMPLES_PER_BAND - len(samples)
                for band, samples in selected.items()
                if len(samples) < SAMPLES_PER_BAND
            }
            message = f"The fixed snapshots do not contain enough samples: {missing}"
            raise RuntimeError(message)
        counts = incoming_counts(candidates)
        for doi, omid in candidates:
            count = counts[doi]
            band = work_band(count)
            if not omid or doi in seen_dois or len(selected[band]) >= SAMPLES_PER_BAND:
                continue
            selected[band].append(Sample(doi, omid, count))
            seen_dois.add(doi)
        offset += len(candidates)
        after = candidates[-1][0]
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
        print(f"Selected samples per band: { {band: len(rows) for band, rows in selected.items()} }", flush=True)  # noqa: T201
    return tuple(sample for band in BANDS for sample in selected[band])


def sample(sample_path: Path) -> None:
    progress_path = sample_path.with_suffix(".progress.json")
    samples = select_samples(progress_path)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    with sample_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(Sample.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(selected_sample) for selected_sample in samples)
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
    spec_path.write_text(queries.specification(), encoding="utf-8")
    datasets = read_manifest(SNAPSHOT_MANIFEST)
    pending = [dataset for dataset in datasets if not dataset_is_ready(dataset, HOST_DATA_DIR)]
    if pending:
        free_bytes = shutil.disk_usage(HOST_DATA_DIR.parent).free
        if free_bytes < MINIMUM_FREE_BYTES:
            message = f"prepare requires {MINIMUM_FREE_BYTES} free bytes; found {free_bytes}"
            raise RuntimeError(message)
    for dataset in pending:
        prepare_dataset(dataset, HOST_DATA_DIR)


def request_strategy(base_url: str, strategy: str, doi: str) -> tuple[int, bytes, float, int, int]:
    url = f"{base_url.rstrip('/')}/{strategy}/{quote(quote(doi, safe=''), safe='')}"
    started_ns = time.perf_counter_ns()
    response = requests.get(url, headers={"Accept": "application/json"}, timeout=REQUEST_TIMEOUT_SECONDS)
    finished_ns = time.perf_counter_ns()
    return response.status_code, response.content, (finished_ns - started_ns) / 1_000_000, started_ns, finished_ns


def validated_responses(samples: tuple[Sample, ...], base_url: str) -> dict[tuple[str, str], queries.Response]:
    responses: dict[tuple[str, str], queries.Response] = {}
    for position, sample in enumerate(samples, 1):
        print(  # noqa: T201
            f"Validating {position}/{len(samples)}: {sample.doi}, citing works={sample.expected_work_count}", flush=True
        )
        for strategy in STRATEGIES:
            status, content, _, _, _ = request_strategy(base_url, strategy, sample.doi)
            if status != HTTP_OK:
                message = f"{strategy} returned HTTP {status} for {sample.doi}"
                raise RuntimeError(message)
            normalized = queries.normalize(content)
            if normalized.omids != tuple(sorted(sample.omid.split("|"))):
                message = f"DOI resolution diverges for {sample.doi}"
                raise RuntimeError(message)
            if len(normalized.works) != sample.expected_work_count:
                message = f"Distinct citing work count diverges for {sample.doi}"
                raise RuntimeError(message)
            responses[(sample.doi, strategy)] = normalized
        if responses[(sample.doi, "service")] != responses[(sample.doi, "orchestration")]:
            message = f"Strategies diverge for {sample.doi}"
            raise RuntimeError(message)
    return responses


def measure(sample: Sample, batch: Batch) -> Measurement:
    status, content, latency_ms, started_ns, finished_ns = request_strategy(batch.base_url, batch.strategy, sample.doi)
    if status != HTTP_OK:
        message = f"{batch.strategy} returned HTTP {status} for {sample.doi}"
        raise RuntimeError(message)
    normalized = queries.normalize(content)
    if normalized != batch.expected[(sample.doi, batch.strategy)]:
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
        enriched_work_count=normalized.enriched_work_count,
        equivalent=True,
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
        "snapshots": json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8")),
    }


def run(sample_path: Path, result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=False)
    samples = read_samples(sample_path)
    print(f"Validating {len(samples)} samples...", flush=True)  # noqa: T201
    expected = validated_responses(samples, BASE_URL)
    (result_dir / "expected.json").write_text(
        json.dumps({sample.doi: asdict(expected[(sample.doi, "service")]) for sample in samples}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(sample_path, result_dir / "sample.csv")
    spec = queries.specification()
    (result_dir / "operations.hf").write_text(spec, encoding="utf-8")
    shutil.copyfile(BENCHMARK_DIR / "compose.yaml", result_dir / "compose.yaml")
    print("Warming up both strategies...", flush=True)  # noqa: T201
    for strategy in STRATEGIES:
        execute_batch(samples, Batch(strategy, 0, max(CONCURRENCY_LEVELS), BASE_URL, expected))
    measurements: list[Measurement] = []
    write_measurements(result_dir / "raw.csv", measurements)
    (result_dir / "environment.json").write_text(
        json.dumps(
            {
                **environment_description(),
                "order_seed": ORDER_SEED,
                "repetitions": REPETITIONS,
                "concurrency_levels": CONCURRENCY_LEVELS,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for concurrency in CONCURRENCY_LEVELS:
        for repetition in range(1, REPETITIONS + 1):
            ordered = list(samples)
            random.Random(ORDER_SEED + repetition).shuffle(ordered)  # noqa: S311
            for strategy in STRATEGIES if repetition % 2 else reversed(STRATEGIES):
                batch = Batch(strategy, repetition, concurrency, BASE_URL, expected)
                measurements.extend(execute_batch(tuple(ordered), batch))
                write_measurements(result_dir / "raw.csv", measurements)
                print(  # noqa: T201
                    f"Measured {strategy}: concurrency={concurrency}, repetition={repetition}; "
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
        "work_band": band,
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
    for strategy in STRATEGIES:
        result[f"{strategy}_mean_response_bytes"] = statistics.mean(row.response_bytes for row in by_strategy[strategy])
        result[f"{strategy}_mean_enriched_works"] = statistics.mean(
            row.enriched_work_count for row in by_strategy[strategy]
        )
    if band == "all":
        for strategy in STRATEGIES:
            batches: dict[int, list[Measurement]] = {}
            for row in by_strategy[strategy]:
                batches.setdefault(row.repetition, []).append(row)
            result[f"{strategy}_throughput_rps"] = statistics.mean(
                batch_throughput(batch) for batch in batches.values()
            )
    return result


def summarize(sample_path: Path, result_dir: Path) -> None:
    samples = read_samples(sample_path)
    sample_by_doi = {sample.doi: sample for sample in samples}
    with (result_dir / "raw.csv").open(newline="", encoding="utf-8") as file:
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
                enriched_work_count=int(row["enriched_work_count"]),
                equivalent=row["equivalent"] == "True",
            )
            for row in csv.DictReader(file)
        ]
    summary = []
    for concurrency in sorted({row.concurrency for row in rows}):
        concurrency_rows = [row for row in rows if row.concurrency == concurrency]
        summary.append(summarize_group(concurrency, "all", concurrency_rows))
        for band in BANDS:
            band_rows = [
                row for row in concurrency_rows if work_band(sample_by_doi[row.doi].expected_work_count) == band
            ]
            summary.append(summarize_group(concurrency, band, band_rows))
    (result_dir / "summary.csv").parent.mkdir(parents=True, exist_ok=True)
    with (result_dir / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


def main() -> None:  # pragma: no cover
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    sample_path = CONTAINER_DATA_DIR / "benchmark" / run_id / "sample.csv"
    result_dir = Path("/results") / run_id
    sample(sample_path)
    run(sample_path, result_dir)
    summarize(sample_path, result_dir)


if __name__ == "__main__":  # pragma: no cover
    main()
