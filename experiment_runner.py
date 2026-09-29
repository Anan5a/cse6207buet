"""Orchestrate the full chaos engineering experiment across all configurations.

By default runs three experimental scenarios sequentially, each under the same
four client patterns, and writes a consolidated report:

  Run 1  burst mode, 15% burst error rate        (latency ramp 200 -> 800 ms)
  Run 2  uniform random, 5% error rate           (latency ramp 300 -> 1500 ms)
  Run 3  burst mode, 30% burst error rate        (latency ramp 200 -> 800 ms)

Use `--single` to run only the first scenario (fast smoke test).
Output files are prefixed with the scenario name under `results/`.
"""

import json
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests

from client_patterns import (
    make_naive_retry_call,
    make_no_retry_call,
    make_retry_jitter_call,
    make_retry_jitter_cb_call,
)
from fault_injector import FaultInjector
from load_runner import build_base_call, run_load
from metrics import compute_metrics, save_records
from report import generate_report

BASE_URL = "http://127.0.0.1:5001"
SERVICE_STARTUP_TIMEOUT = 10.0
DURATION = 30.0
TARGET_RPS = 20

PatternCall = Callable[..., Any]
PatternFactory = Callable[[PatternCall], PatternCall]

# Configurations compared under every scenario, in report order.
CONFIGS: list[tuple[str, PatternFactory]] = [
    ("no_retry", make_no_retry_call),
    ("naive_retry", make_naive_retry_call),
    ("retry_jitter", make_retry_jitter_call),
    ("retry_jitter_cb", make_retry_jitter_cb_call),
]


@dataclass
class Scenario:
    name: str
    description: str
    use_burst: bool
    burst_error_pct: float
    start_latency: int
    end_latency: int


SCENARIOS = [
    Scenario(
        name="run1_burst_15",
        description="Burst Mode - 15% Errors",
        use_burst=True,
        burst_error_pct=0.15,
        start_latency=200,
        end_latency=800,
    ),
    Scenario(
        name="run2_uniform",
        description="Uniform Random - 5% Errors",
        use_burst=False,
        burst_error_pct=0.05,
        start_latency=300,
        end_latency=1500,
    ),
    Scenario(
        name="run3_burst_30",
        description="Burst Mode - 30% Errors",
        use_burst=True,
        burst_error_pct=0.30,
        start_latency=200,
        end_latency=800,
    ),
]


def wait_for_service(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/health", timeout=1)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.2)
    return False


def start_service() -> subprocess.Popen | None:
    # If something is already on the port, try to reuse it.
    if wait_for_service(BASE_URL, timeout=1.0):
        print("[Runner] Reusing existing downstream service")
        return None

    print("[Runner] Starting downstream service...")
    proc = subprocess.Popen(
        [sys.executable, "downstream_service.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if not wait_for_service(BASE_URL, SERVICE_STARTUP_TIMEOUT):
        proc.terminate()
        raise RuntimeError("Downstream service failed to start")
    print("[Runner] Downstream service ready")
    return proc


def stop_service(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def reset_faults() -> None:
    try:
        requests.post(
            f"{BASE_URL}/admin/fault",
            json={"latency_ms": 0, "error_rate": 0.0},
            timeout=2,
        )
    except requests.RequestException as exc:
        print(f"[Runner] Warning: could not reset faults: {exc}")


def run_single_experiment(
    scenario: Scenario,
    config_name: str,
    pattern_factory: PatternFactory,
    results_dir: Path,
) -> dict[str, Any]:
    print(f"\n[Runner] === {scenario.name} / config: {config_name} ===")
    reset_faults()

    base_call = build_base_call(url=f"{BASE_URL}/api/data", timeout=5.0)
    pattern_call = pattern_factory(base_call)

    injector = FaultInjector(BASE_URL)
    # In burst mode, the burst error rate is the probability a request fails
    # while inside a burst window. In uniform mode, it is the flat per-request
    # error rate.
    injector.start_ramp(
        duration=DURATION,
        start_ms=scenario.start_latency,
        end_ms=scenario.end_latency,
        error_rate=scenario.burst_error_pct,
        burst_mode=scenario.use_burst,
    )

    # Brief warm-up so the ramp is active before load starts.
    time.sleep(2.0)

    records = run_load(
        pattern_fn=pattern_call,
        duration=DURATION,
        target_rps=TARGET_RPS,
    )

    injector.stop()

    metrics = compute_metrics(records)
    prefix = f"{scenario.name}_"
    save_records(records, results_dir / f"{prefix}{config_name}.json")
    metrics_path = results_dir / f"{prefix}{config_name}_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))

    print(
        f"[Runner] {config_name}: total={metrics['total_requests']}, "
        f"errors={metrics['error_rate']:.2%}, p99={metrics['p99_success']:.1f}ms, "
        f"throughput={metrics['throughput']:.1f}req/s"
    )
    return metrics


def run_scenario(scenario: Scenario, results_dir: Path) -> None:
    print(f"\n{'=' * 60}")
    print(f"RUNNING SCENARIO: {scenario.description}")
    print(f"  name: {scenario.name}, burst={scenario.use_burst}, "
          f"error_rate={scenario.burst_error_pct:.0%}")
    print(f"{'=' * 60}\n")

    service_proc = start_service()
    try:
        for config_name, pattern_factory in CONFIGS:
            run_single_experiment(scenario, config_name, pattern_factory, results_dir)
            time.sleep(2.0)
    finally:
        stop_service(service_proc)


def run_all_scenarios(results_dir: Path) -> None:
    for scenario in SCENARIOS:
        run_scenario(scenario, results_dir)
    generate_report(str(results_dir))
    print("\n[Runner] All experiments complete. Report generated in results/")


def main() -> int:
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        # Fast smoke test: run only the first scenario.
        run_scenario(SCENARIOS[0], results_dir)
        generate_report(str(results_dir))
        print("\n[Runner] Single scenario complete.")
    else:
        run_all_scenarios(results_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())