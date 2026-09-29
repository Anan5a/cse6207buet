# Implementation Plan: Chaos Engineering Framework for Microservices Resilience

## Goal
Build a minimal, working Python chaos-engineering experiment that reproduces Mohammad (2025)'s retry/circuit-breaker findings. The demo runs all configurations in-process over localhost HTTP, producing per-request latency data, aggregate metrics, and a comparison chart.

## Constraints & Decisions
- **No Docker / K8s / external infra**: everything is in-process Python with threads and a Flask service on `localhost:5001`.
- **Dependencies**: Flask, requests, matplotlib.
- **Target runtime**: under 10 minutes for all 4 configurations.
- **Load profile**: 200 req/s for 60 s.
- **Fault profile**: latency ramps linearly from 300 ms → 1500 ms; `error_rate` fixed at 5 %.
- **Honest reporting**: final table compares our measured numbers with the literature numbers and notes environment differences.

## File Structure
```
chaos-framework/
├── downstream_service.py   # Flask: /api/data, /admin/fault
├── client_patterns.py      # Retry, retry+jitter, circuit breaker, timeout, bulkhead
├── fault_injector.py       # POST /admin/fault; time-based ramp schedule
├── load_runner.py          # ThreadPoolExecutor load generator
├── experiment_runner.py    # Main entry point: runs all 4 configs
├── metrics.py              # P50/P95/P99, error rate, throughput
├── report.py               # Markdown table + matplotlib chart
└── results/                # Generated artifacts
    ├── no_retry.json
    ├── naive_retry.json
    ├── retry_jitter.json
    ├── retry_jitter_cb.json
    ├── comparison_table.md
    └── comparison_chart.png
```

## Implementation Steps

### 1. `downstream_service.py`
- Flask app on `localhost:5001`.
- `GET /api/data`:
  - Read current fault config from a thread-safe in-memory store (Flask `g` or module-level dict with lock).
  - Sleep `latency_ms`.
  - Return 500 with probability `error_rate`; otherwise 200 with a small JSON payload.
- `POST /admin/fault`:
  - Accept JSON `{latency_ms: int, error_rate: float}`.
  - Validate ranges and update the shared config.
- Expose `app.run(host="127.0.0.1", port=5001, threaded=True)` so latency sleeps do not block other admin calls.

### 2. `fault_injector.py`
- `FaultInjector` class holds target URL and current schedule.
- `inject_fault(latency_ms, error_rate)` sends `POST /admin/fault`.
- `ramp_latency(duration=60, start_ms=300, end_ms=1500, error_rate=0.05)`:
  - Runs in its own thread.
  - Updates fault config every second so latency increases linearly.
  - Prints progress for observability.
- Optional helper `run_schedule()` to start ramp and return control.

### 3. `client_patterns.py`
All wrappers accept a call function `fn(*args, **kwargs)` and return the result or raise the final exception.
- `naive_retry(fn, max_attempts=3, delay=0.5)` — fixed delay, no jitter.
- `retry_with_jitter(fn, max_attempts=3, base_delay=0.2, max_delay=2.0, exponential_base=2.0)`:
  - Backoff = `min(base_delay * (exponential_base ** attempt), max_delay)`.
  - Add uniform or full jitter: `random() * backoff`.
- `CircuitBreaker` class:
  - States: `CLOSED`, `OPEN`, `HALF_OPEN`.
  - Open after 5 consecutive failures; half-open after 10 s; close after 2 consecutive successes in half-open.
  - Wraps `retry_with_jitter`.
  - Thread-safe state transitions with a lock.
- `timeout(fn, seconds)` — wrapper around requests call (stretch / used as default).
- `Bulkhead` class — semaphore with max concurrency (stretch, P2).

### 4. `load_runner.py`
- `run_load(target_url, pattern_fn, duration=60, target_rps=200, timeout=5.0)`:
  - Use `ThreadPoolExecutor(max_workers=400)`.
  - Each worker loops for `duration` seconds, attempting to maintain ~200 req/s via fixed interval between requests (rate-limited by each worker sleeping `1/target_rps` between calls, or better: coordinator dispatching at 5 ms intervals).
  - Better approach: spawn workers equal to target_rps (200), each worker fires once per second; this naturally yields ~200 req/s.
  - Record per request: `timestamp`, `latency_ms`, `success` (bool), `status_code`, `pattern`, `error` (optional).
  - Return list of dicts.
- Apply a per-call `timeout=5.0` by default so stuck calls do not hang the runner.

### 5. `metrics.py`
- `compute_metrics(records: list[dict]) -> dict`:
  - Filter latencies of successful requests for percentile calculation (or include only attempted? include all attempts; report separately if needed).
  - Use `numpy.percentile` if available, otherwise pure-Python sorted percentile.
  - Returns `p50`, `p95`, `p99`, `error_rate`, `throughput`, `total_requests`, `successful`, `failed`.

### 6. `report.py`
- `generate_report(all_metrics: dict, output_dir="results")`:
  - Create `comparison_table.md` with columns: Config, P50, P95, P99, Error Rate, Throughput.
  - Add a second table / rows for Mohammad (2025) literature baseline if known.
  - Use matplotlib to create a grouped bar chart: P99 latency (left y-axis) and error rate (right y-axis) per config.
  - Save `results/comparison_chart.png`.

### 7. `experiment_runner.py`
- Main orchestrator.
- Steps for each config in `["no_retry", "naive_retry", "retry_jitter", "retry_jitter_cb"]`:
  1. Start downstream service in a background thread (or subprocess).
  2. Reset fault config to baseline (latency=0, error=0).
  3. Start the fault injector ramp in a thread.
  4. Wait 2 s warm-up.
  5. Run load for 60 s with the appropriate client pattern.
  6. Stop fault injector.
  7. Compute metrics; save raw records to `results/<config>.json`.
  8. Tear down / restart service for a clean state (avoid cross-config circuit breaker state).
- After all configs, call `report.generate_report()`.
- Guard against port-in-use: if service already running, reuse it; else start.
- Add CLI prints so the demo is observable.

## Priority / Cut Points
- **P0 (must have)**: downstream service, fault injector, load runner, metrics, report, experiment runner, and 3 core patterns: no retry, naive retry, retry+jitter.
- **P1 (demo-complete)**: add circuit breaker.
- **P2 (stretch)**: bulkhead and timeout wrappers; auto-generated chart polish.
- **P3 (cut if time short)**: additional fault types (crash, high error-rate injection).

## Risk Mitigation
- **Port collisions**: check `localhost:5001` before starting; reuse existing service if it responds.
- **Thread saturation**: use threaded Flask and high worker count in load runner; cap total in-flight requests to avoid OS resource exhaustion.
- **Noisy latency measurements**: keep the machine otherwise idle during the run; print warnings if observed throughput is far below target.
- **State bleed between configs**: fully restart the Flask process between configs or ensure `/admin/fault` resets all shared state.

## Acceptance Criteria
- `python experiment_runner.py` completes without errors in < 10 minutes.
- Four `results/*.json` files exist with at least ~12 000 records each (200 req/s × 60 s).
- `results/comparison_table.md` is generated with P99 and error rate for all configs.
- `results/comparison_chart.png` is generated.
- Error rate and P99 latency trend downward as patterns improve (retry+jitter+circuit breaker should be best).
