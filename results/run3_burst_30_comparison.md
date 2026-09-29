# Run 3 — Burst Mode, 30% Errors

- Fault: burst-correlated, 30% burst error rate, latency ramp 200→800 ms

| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |
|---|---|---|---|---|---|
| No retry | 523.6 | 802.0 | 802.6 | 31.17% | 19.7 |
| Naive retry | 522.9 | 801.8 | 802.4 | 27.17% | 19.7 |
| Retry + jitter | 522.4 | 801.8 | 802.5 | 33.33% | 19.7 |
| Retry + jitter + CB | 524.1 | 785.7 | 802.2 | 34.67% | 19.7 |