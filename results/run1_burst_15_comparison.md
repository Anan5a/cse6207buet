# Run 1 — Burst Mode, 15% Errors

- Fault: burst-correlated, 15% burst error rate, latency ramp 200→800 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 523.8 | 802.0 | 802.6 | 17.17% | 19.7 |
| Naive retry | 542.9 | 802.0 | 802.6 | 14.67% | 19.7 |
| Retry + jitter | 523.4 | 801.8 | 802.3 | 16.33% | 19.7 |
| Retry + jitter + CB | 523.4 | 801.9 | 802.4 | 16.50% | 19.7 |