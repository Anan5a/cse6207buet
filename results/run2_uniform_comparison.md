# Run 2 — Uniform Random, 5% Errors

- Fault: independent random, 5% error rate, latency ramp 300→1500 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 943.8 | 1502.0 | 1502.6 | 3.83% | 19.3 |
| Naive retry | 984.1 | 1502.0 | 1502.6 | 5.50% | 19.3 |
| Retry + jitter | 943.5 | 1501.9 | 1502.6 | 5.17% | 19.3 |
| Retry + jitter + CB | 944.9 | 1501.9 | 1502.5 | 5.50% | 19.3 |