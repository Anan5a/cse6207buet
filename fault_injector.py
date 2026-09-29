"""Time-based fault injection controller for the downstream service."""

import threading
import time

import requests


class FaultInjector:
    def __init__(self, base_url: str = "http://127.0.0.1:5001"):
        self.base_url = base_url.rstrip("/")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def inject_fault(self, latency_ms: int, error_rate: float, burst_mode: bool = False) -> None:
        url = f"{self.base_url}/admin/fault"
        payload = {"latency_ms": latency_ms, "error_rate": error_rate, "burst_mode": burst_mode}
        try:
            requests.post(url, json=payload, timeout=2)
        except requests.RequestException as exc:
            print(f"[FaultInjector] Failed to inject fault: {exc}")

    def ramp_latency(
        self,
        duration: float = 30.0,
        start_ms: int = 300,
        end_ms: int = 1500,
        error_rate: float = 0.40,
        step_seconds: float = 1.0,
        burst_mode: bool = True,
    ) -> None:
        """Ramp latency linearly from start_ms to end_ms over duration seconds.

        When burst_mode=True, errors are correlated in bursty windows rather than
        uniformly random. This enables retry strategies to differentiate: backoff+jitter
        can land on non-burst windows, while rapid retries stay stuck in bursts.
        Circuit breaker trips during sustained burst periods.
        """
        self._stop_event.clear()
        start_time = time.time()
        elapsed = 0.0
        while elapsed < duration and not self._stop_event.is_set():
            progress = elapsed / duration
            latency_ms = int(start_ms + (end_ms - start_ms) * progress)
            self.inject_fault(latency_ms, error_rate, burst_mode)
            mode_str = " (burst)" if burst_mode else ""
            print(f"[FaultInjector] t={elapsed:.1f}s -> latency={latency_ms}ms, error_rate={error_rate:.2%}{mode_str}")
            time.sleep(step_seconds)
            elapsed = time.time() - start_time
        # Final value at the end of the ramp to keep config stable.
        self.inject_fault(end_ms, error_rate, burst_mode)

    def start_ramp(self, **kwargs) -> threading.Thread:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.ramp_latency, kwargs=kwargs, daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


if __name__ == "__main__":
    injector = FaultInjector()
    injector.ramp_latency(duration=60, start_ms=300, end_ms=1500, error_rate=0.05)
