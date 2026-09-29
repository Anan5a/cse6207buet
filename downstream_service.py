"""Flask downstream service with configurable injected latency and error rate.

Supports two error modes:
  - uniform_random (default): each request fails independently at error_rate
  - burst_correlated: errors cluster in long bursts (~8-12s) followed by short
    gaps (~1-2s). During a burst window, ~15% of requests fail; during a gap,
    only ~1%. This creates correlated failures where retry timing matters —
    retries with backoff+jitter can land in recovery windows.
"""

import random
import threading
import time
from dataclasses import dataclass

from flask import Flask, jsonify, request

app = Flask(__name__)


@dataclass
class FaultConfig:
    latency_ms: int = 0
    error_rate: float = 0.0
    burst_mode: bool = False


_config = FaultConfig()
_config_lock = threading.Lock()

# Burst-mode state: stored in a dict so reads/writes don't require `global`.
_burst_state_lock = threading.Lock()
_burst = {
    "end": 0.0,           # monotonic timestamp when current phase ends
    "in_burst": True,      # True = in error-producing burst; False = in gap
}


def _now_mono() -> float:
    return time.monotonic()


def _tick_burst_timer(now: float) -> None:
    """Schedule next burst↔gap transition."""
    if _burst["in_burst"]:
        gap_dur = random.uniform(1.0, 2.0)
        end = now + gap_dur
    else:
        burst_dur = random.uniform(8.0, 12.0)
        end = now + burst_dur

    with _burst_state_lock:
        _burst["end"] = end
        _burst["in_burst"] = not _burst["in_burst"]

    threading.Timer(end - now, _tick_burst_timer).start()


def get_config() -> FaultConfig:
    with _config_lock:
        return FaultConfig(_config.latency_ms, _config.error_rate, _config.burst_mode)


def set_burst_config(latency_ms: int, error_rate: float, burst_mode: bool) -> None:
    """Update fault config and optionally start burst scheduling."""
    with _config_lock:
        _config.latency_ms = max(0, int(latency_ms))
        _config.error_rate = max(0.0, min(1.0, float(error_rate)))
        _config.burst_mode = burst_mode
    if burst_mode:
        with _burst_state_lock:
            _burst["end"] = _now_mono() + random.uniform(4.0, 7.0)
            _burst["in_burst"] = True
        threading.Timer(random.uniform(4.0, 7.0), _tick_burst_timer).start()


def _should_error_burst() -> bool:
    """Determine if this request should fail based on current burst schedule.

    Thread-safe using mutex + monotonic time for window comparison.

    During burst windows: requests fail at the configured burst error rate
    (e.g. 15% or 30%), moderate enough that some retry attempts will succeed.
    During gap windows: ~1% noise (near-clean recovery period).
    """
    cfg = get_config()
    now = _now_mono()
    with _burst_state_lock:
        in_burst = _burst["in_burst"]
        win_end = _burst["end"]

    if in_burst and now < win_end:
        return random.random() < cfg.error_rate   # burst: configured fail rate
    else:
        return random.random() < 0.01             # gap: near-clean ~1 % noise


@app.route("/api/data", methods=["GET"])
def api_data():
    cfg = get_config()
    if cfg.latency_ms > 0:
        time.sleep(cfg.latency_ms / 1000.0)

    if cfg.burst_mode:
        if _should_error_burst():
            return jsonify({"error": "injected failure"}), 500
    elif cfg.error_rate > 0:
        if random.random() < cfg.error_rate:
            return jsonify({"error": "injected failure"}), 500

    return jsonify({"status": "ok", "latency_ms": cfg.latency_ms}), 200


@app.route("/admin/fault", methods=["POST"])
def admin_fault():
    data = request.get_json(force=True, silent=True) or {}
    latency_ms = data.get("latency_ms", 0)
    error_rate = data.get("error_rate", 0.0)
    burst_mode = data.get("burst_mode", False)
    set_burst_config(latency_ms, error_rate, burst_mode)
    cfg = get_config()
    return jsonify({
        "latency_ms": cfg.latency_ms,
        "error_rate": cfg.error_rate,
        "burst_mode": cfg.burst_mode,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


def main():
    print("Starting downstream service on http://127.0.0.1:5001")
    try:
        import waitress
        print("Using waitress WSGI server")
        waitress.serve(app, host="127.0.0.1", port=5001, threads=512)
    except ImportError:
        print("waitress not installed; falling back to Flask development server")
        app.run(host="127.0.0.1", port=5001, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
