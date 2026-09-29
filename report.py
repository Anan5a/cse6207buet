"""Generate comparison markdown tables and matplotlib charts from experiment metrics.

Handles scenario-prefixed metric files (e.g. run1_burst_15_no_retry_metrics.json)
and writes one table + chart per scenario, plus a consolidated summary.
"""

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


CONFIG_LABELS = {
    "no_retry": "No retry",
    "naive_retry": "Naive retry",
    "retry_jitter": "Retry + jitter",
    "retry_jitter_cb": "Retry + jitter + CB",
}

SCENARIOS = [
    {
        "name": "run1_burst_15",
        "title": "Run 1 — Burst Mode, 15% Errors",
        "fault": "burst-correlated, 15% burst error rate, latency ramp 200→800 ms",
    },
    {
        "name": "run2_uniform",
        "title": "Run 2 — Uniform Random, 5% Errors",
        "fault": "independent random, 5% error rate, latency ramp 300→1500 ms",
    },
    {
        "name": "run3_burst_30",
        "title": "Run 3 — Burst Mode, 30% Errors",
        "fault": "burst-correlated, 30% burst error rate, latency ramp 200→800 ms",
    },
]


def load_scenario_metrics(results_dir: Path, scenario: str) -> dict[str, dict[str, Any]]:
    metrics = {}
    for config in CONFIG_LABELS:
        path = results_dir / f"{scenario}_{config}_metrics.json"
        if path.exists():
            with open(path) as f:
                metrics[config] = json.load(f)
        else:
            print(f"[Report] Warning: missing metrics file {path}")
    return metrics


def generate_markdown_table(scenario: dict[str, str], metrics: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# {scenario['title']}",
        "",
        f"- Fault: {scenario['fault']}",
        "",
        "| Configuration | P50 (ms) | P95 (ms) | P99 (ms) | Error rate | Throughput (req/s) |",
        "|---|---|---|---|---|---|",
    ]
    for config, label in CONFIG_LABELS.items():
        m = metrics.get(config, {})
        lines.append(
            f"| {label} | "
            f"{m.get('p50_success', 0.0):.1f} | "
            f"{m.get('p95_success', 0.0):.1f} | "
            f"{m.get('p99_success', 0.0):.1f} | "
            f"{m.get('error_rate', 0.0):.2%} | "
            f"{m.get('throughput', 0.0):.1f} |"
        )
    return "\n".join(lines)


def generate_scenario_chart(
    scenario: dict[str, str], metrics: dict[str, dict[str, Any]], output_path: Path
) -> None:
    configs = list(CONFIG_LABELS.keys())
    labels = [CONFIG_LABELS[c] for c in configs]
    p99_values = [metrics.get(c, {}).get("p99_success", 0.0) for c in configs]
    error_values = [metrics.get(c, {}).get("error_rate", 0.0) * 100 for c in configs]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax1 = plt.subplots(figsize=(10, 6))
    color_p99 = "tab:blue"
    ax1.set_xlabel("Configuration")
    ax1.set_ylabel("P99 latency (ms)", color=color_p99)
    ax1.bar(x - width / 2, p99_values, width, label="P99 latency (ms)", color=color_p99)
    ax1.tick_params(axis="y", labelcolor=color_p99)

    ax2 = ax1.twinx()
    color_err = "tab:red"
    ax2.set_ylabel("Error rate (%)", color=color_err)
    ax2.bar(x + width / 2, error_values, width, label="Error rate (%)", color=color_err)
    ax2.tick_params(axis="y", labelcolor=color_err)

    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=15, ha="right")
    ax1.set_title(f"Chaos Engineering Experiment — {scenario['title']}")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def generate_error_rate_summary(
    metrics_by_scenario: dict[str, dict[str, dict[str, Any]]]
) -> str:
    lines = [
        "## Error-rate summary across runs (%)",
        "",
        "| Configuration | Run 1 (burst 15%) | Run 2 (uniform 5%) | Run 3 (burst 30%) |",
        "|---|---|---|---|",
    ]
    for config, label in CONFIG_LABELS.items():
        row = [label]
        for sc in SCENARIOS:
            m = metrics_by_scenario.get(sc["name"], {}).get(config, {})
            row.append(f"{m.get('error_rate', 0.0) * 100:.2f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def generate_report(results_dir: str = "results") -> None:
    results_path = Path(results_dir)
    metrics_by_scenario = {}
    parts = []

    title = "# Chaos Engineering Experiment Results\n"
    parts.append(title + "\n- Load: 20 req/s for 30 s per configuration\n"
                 "- Four client patterns: no retry, naive retry, retry + jitter, retry + jitter + CB\n"
                 "- Service: Flask via waitress (512 threads), in-process on localhost:5001\n")

    for scenario in SCENARIOS:
        metrics = load_scenario_metrics(results_path, scenario["name"])
        metrics_by_scenario[scenario["name"]] = metrics

        table = generate_markdown_table(scenario, metrics)
        table_path = results_path / f"{scenario['name']}_comparison.md"
        table_path.write_text(table)
        print(f"[Report] Wrote {table_path}")

        chart_path = results_path / f"{scenario['name']}_chart.png"
        generate_scenario_chart(scenario, metrics, chart_path)
        print(f"[Report] Wrote {chart_path}")

        parts.append(table)
        parts.append("")

    parts.append(generate_error_rate_summary(metrics_by_scenario))
    parts.append("")

    summary_path = results_path / "comparison_table.md"
    summary_path.write_text("\n".join(parts).strip() + "\n")
    print(f"[Report] Wrote {summary_path}")


if __name__ == "__main__":
    generate_report()