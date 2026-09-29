"""Compute aggregate metrics from raw per-request records."""

import json
import math
from pathlib import Path
from typing import Any


def percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile (0-100) of a sorted list using nearest-rank."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1


def compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "error_rate": 0.0,
            "throughput": 0.0,
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
        }

    successful_records = [r for r in records if r["success"]]
    failed_records = [r for r in records if not r["success"]]

    latencies = sorted(r["latency_ms"] for r in records)
    success_latencies = sorted(r["latency_ms"] for r in successful_records)

    duration_seconds = max(1.0, records[-1]["timestamp"] - records[0]["timestamp"])
    throughput = total / duration_seconds

    return {
        "p50_all": percentile(latencies, 50.0),
        "p95_all": percentile(latencies, 95.0),
        "p99_all": percentile(latencies, 99.0),
        "p50_success": percentile(success_latencies, 50.0),
        "p95_success": percentile(success_latencies, 95.0),
        "p99_success": percentile(success_latencies, 99.0),
        "error_rate": len(failed_records) / total,
        "throughput": throughput,
        "total_requests": total,
        "successful": len(successful_records),
        "failed": len(failed_records),
        "mean_latency_ms": sum(latencies) / total,
    }


def save_records(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f, indent=2)


def load_records(path: Path) -> list[dict[str, Any]]:
    with open(path) as f:
        return json.load(f)
