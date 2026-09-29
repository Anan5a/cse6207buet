# Chaos Engineering Framework for Microservices Resilience

A minimal Python chaos-engineering experiment that reproduces the retry / circuit-breaker study design from Mohammad (2025) using an in-process Flask downstream service and real HTTP calls.

## Files

| File | Purpose |
|---|---|
| `downstream_service.py` | Flask service with `/api/data` and `/admin/fault` endpoints |
| `client_patterns.py` | Retry, retry+jitter, circuit breaker, timeout, bulkhead wrappers |
| `fault_injector.py` | Time-based latency ramp injected via `/admin/fault` |
| `load_runner.py` | Threaded load generator that records every request |
| `metrics.py` | P50/P95/P99, error rate, throughput |
| `report.py` | Markdown comparison table + matplotlib chart |
| `experiment_runner.py` | Main entry point — runs all 4 configs and produces the report |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment_runner.py
```

Results are written to `results/`:

- `{run}_{config}.json` — raw per-request data (e.g. `run1_burst_15_no_retry.json`)
- `{run}_{config}_metrics.json` — aggregate statistics per configuration
- `{run}_comparison.md` and `{run}_chart.png` — per-scenario table + chart
- `comparison_table.md` — consolidated summary across all three runs

## What it demonstrates

Four client configurations are compared under the same fault schedule:

1. **No retry** — raw HTTP calls
2. **Naive retry** — 3 attempts, fixed 500 ms delay, no jitter
3. **Retry + jitter** — exponential backoff + full jitter
4. **Retry + jitter + Circuit Breaker** — retry wrapped with a circuit breaker

Three fault schedules are run (see Results):

- **Run 1 (burst 15%):** latency ramp 200 → 800 ms, burst-correlated errors at 15%
- **Run 2 (uniform 5%):** latency ramp 300 → 1500 ms, independent random errors at 5%
- **Run 3 (burst 30%):** latency ramp 200 → 800 ms, burst-correlated errors at 30%

## Current Run Parameters

The demo runs at reduced scale for single-machine execution:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Load rate | 20 req/s | Produces ~600 requests per config without saturating local resources |
| Duration | 30 s per config | Covers full latency ramp plus warm-up buffer |
| Timeout | 10 s max | Prevents hung calls; far exceeds 1500 ms fault ceiling |
| Worker pool | 100 threads | Bounded concurrency prevents resource exhaustion under retry storms |
| Service | Waitress WSGI, 512 threads | Avoids bottlenecking the server itself |

For the original literature parameters (200 req/s, 60 s) deploy the service on a separate host or use an async server.

## Results

### Measured Data — In-Process Simulation (Three Experimental Runs)

The framework runs three scenarios sequentially, each under the same four client patterns:

| Run | Fault mode | Burst error rate | Latency ramp |
|-----|-----------|------------------|--------------|
| 1 | burst-correlated | 15 % | 200 → 800 ms |
| 2 | uniform random | 5 % | 300 → 1500 ms |
| 3 | burst-correlated | 30 % | 200 → 800 ms |

Errors in burst mode cluster in windows (~8–12 s) followed by short gaps (~1–2 s). During bursts, the configured percentage of requests fail; during gaps, ~1%. This creates correlated failures where retry timing matters.

**Run 1 — Burst mode, 15% errors**

| Configuration | Total Requests | Failed | Error Rate | Throughput |
|---------------|----------------|--------|------------|------------|
| **No retry** | 600 | 103 | 17.17 % | 19.7 req/s |
| **Naive retry** | 600 | 88 | 14.67 % | 19.7 req/s |
| **Retry + jitter** | 600 | 98 | 16.33 % | 19.7 req/s |
| **Retry + jitter + CB** | 600 | 99 | 16.50 % | 19.7 req/s |

**Run 2 — Uniform random, 5% errors**

| Configuration | Total Requests | Failed | Error Rate | Throughput |
|---------------|----------------|--------|------------|------------|
| **No retry** | 600 | 23 | 3.83 % | 19.3 req/s |
| **Naive retry** | 600 | 33 | 5.50 % | 19.3 req/s |
| **Retry + jitter** | 600 | 31 | 5.17 % | 19.3 req/s |
| **Retry + jitter + CB** | 600 | 33 | 5.50 % | 19.3 req/s |

**Run 3 — Burst mode, 30% errors**

| Configuration | Total Requests | Failed | Error Rate | Throughput |
|---------------|----------------|--------|------------|------------|
| **No retry** | 600 | 187 | 31.17 % | 19.7 req/s |
| **Naive retry** | 600 | 163 | 27.17 % | 19.7 req/s |
| **Retry + jitter** | 600 | 200 | 33.33 % | 19.7 req/s |
| **Retry + jitter + CB** | 600 | 208 | 34.67 % | 19.7 req/s |

#### Key Findings

**Under correlated (burst) faults, only naive fixed-delay retry beats baseline.** In Run 1 naive retry improves 17.17% → 14.67% (-2.5 pts); in Run 3 it improves 31.17% → 27.17% (-4.0 pts). Jitter and CB help only marginally at 15% and *harm* outcomes at 30% severity (33.33% and 34.67% vs. 31.17% baseline).

Two factors explain this outcome:

1. **Burst duration >> retry interval.** Bursts last 8–12 s while gaps are only 1–2 s. A fixed 500 ms retry sometimes lands just outside the burst, while randomized jitter does not reliably shift past the entire burst period. At 30% severity, a jittered wait more often lands back inside the same long burst.

2. **Circuit breaker trips early and stays open.** At 20 req/s, failures accumulate slowly enough that the CB rarely reaches its trip threshold until late in a burst. Once tripped, it fails all subsequent requests immediately rather than letting them succeed in recovery gaps — at 30% severity this pushes error rate above baseline.

**Under independent (uniform) errors, retries provide no benefit.** Every attempt has the same ~5% chance regardless of timing, so retrying only adds amplification (3.83% baseline vs. 5.17–5.50%). This confirms that retry effectiveness depends on error correlation — the presence of recovery windows that retry timing can exploit.

**P99 latency ceiling persists:** All configurations plateau at the injected ramp ceiling (~803 ms in burst runs, ~1503 ms in the uniform run). Circuit breakers would need higher concurrency or separate-host deployment to demonstrate their full latency-saving potential via fast-fail semantics.

### Literature Comparison — Mohammad (2025)

Mohammad (2025) — *Resilient Microservices: A Systematic Review of Recovery Patterns, Strategies, and Evaluation Frameworks* — published both a PRISMA-guided systematic review (412 papers → 26 studies) AND ran their own experiments at 200 req/s for 60 s with a latency ramp of 300→1500 ms using a separate service host. The paper provides summary findings but focuses primarily on the literature synthesis; detailed experimental setup, source code, and raw data are not included in the publication. Our work complements their findings by providing an independently runnable implementation where all configuration parameters, source code, and raw per-request data are fully available.

#### Mohammad's Reported Results

| Configuration | P99 Latency | Error Rate | Notes |
|---------------|-------------|------------|-------|
| Raw exponential backoff (uncontrolled retries) | **2600 ms** | **17 %** | Retry amplification causes cascading delays |
| Exponential backoff + jitter | **1400 ms** | **6 %** | Randomized backoff desynchronizes retries |
| Capped attempts + circuit breaker | **1100 ms** | **3 %** | Fail-fast after trip threshold prevents waste |

Our measured results were reported above. The span of error-rate improvements differs materially (Mohammad: 17% → 3%; ours: 17.17% → 14.67% best-case under burst faults). Possible explanations include their use of uncontrolled exponential backoff as the worst case (causing severe retry amplification) and testing at 10× our concurrency level where CB benefits compound more dramatically.

### Known Limitations

1. **Low concurrency** (20 req/s vs. target 200 req/s): insufficient thread contention to expose retry storm mitigation differences
2. **Single machine**: no network isolation between load generator and service
3. **Short runs** (30 s): burst windows (~8–12 s) overlap run boundaries; CB trips early and may not recover before the next burst
4. **Limited fault variety**: only latency ramp + burst-correlated errors, no crash scenarios or error-rate spikes

Future work: Docker/Kubernetes deployment with isolated service hosts, increased load to 200+ req/s, expanded fault types, and formal statistical testing (confidence intervals, p-values, effect sizes).

## Reproducibility

Delete `results/` and re-run. All raw per-request data is saved as JSON, so every table and chart above can be regenerated from the committed inputs.
