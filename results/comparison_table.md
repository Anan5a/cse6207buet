# Chaos Engineering Experiment Results

- Load: 20 req/s for 30 s per configuration
- Four client patterns: no retry, naive retry, retry + jitter, retry + jitter + CB
- Service: Flask via waitress (512 threads), in-process on localhost:5001

# Run 1 — Burst Mode, 15% Errors

- Fault: burst-correlated, 15% burst error rate, latency ramp 200→800 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 523.8 | 802.0 | 802.6 | 17.17% | 19.7 |
| Naive retry | 542.9 | 802.0 | 802.6 | 14.67% | 19.7 |
| Retry + jitter | 523.4 | 801.8 | 802.3 | 16.33% | 19.7 |
| Retry + jitter + CB | 523.4 | 801.9 | 802.4 | 16.50% | 19.7 |

# Run 2 — Uniform Random, 5% Errors

- Fault: independent random, 5% error rate, latency ramp 300→1500 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 943.8 | 1502.0 | 1502.6 | 3.83% | 19.3 |
| Naive retry | 984.1 | 1502.0 | 1502.6 | 5.50% | 19.3 |
| Retry + jitter | 943.5 | 1501.9 | 1502.6 | 5.17% | 19.3 |
| Retry + jitter + CB | 944.9 | 1501.9 | 1502.5 | 5.50% | 19.3 |

# Run 3 — Burst Mode, 30% Errors

- Fault: burst-correlated, 30% burst error rate, latency ramp 200→800 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 523.6 | 802.0 | 802.6 | 31.17% | 19.7 |
| Naive retry | 522.9 | 801.8 | 802.4 | 27.17% | 19.7 |
| Retry + jitter | 522.4 | 801.8 | 802.5 | 33.33% | 19.7 |
| Retry + jitter + CB | 524.1 | 785.7 | 802.2 | 34.67% | 19.7 |

## Error-rate summary across runs (%)

| Configuration | Run 1 (burst 15%) | Run 2 (uniform 5%) | Run 3 (burst 30%) |
|---|---|---|---|
| No retry | 17.17 | 3.83 | 31.17 |
| Naive retry | 14.67 | 5.50 | 27.17 |
| Retry + jitter | 16.33 | 5.17 | 33.33 |
| Retry + jitter + CB | 16.50 | 5.50 | 34.67 |
