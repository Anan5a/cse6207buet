"""Load generator that drives requests through a client pattern and records per-request data."""

import queue
import threading
import time
from typing import Any, Callable

import requests


class _RequestResult:
    def __init__(
        self,
        request_id: int,
        timestamp: float,
        latency_ms: float,
        success: bool,
        status_code: int | None,
        error: str | None,
    ):
        self.request_id = request_id
        self.timestamp = timestamp
        self.latency_ms = latency_ms
        self.success = success
        self.status_code = status_code
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "status_code": self.status_code,
            "error": self.error,
        }


def _worker(
    pattern_fn: Callable[..., Any],
    request_queue: queue.Queue,
    result_queue: queue.Queue,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set() or not request_queue.empty():
        try:
            request_id = request_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        t0 = time.perf_counter()
        try:
            response = pattern_fn()
            latency_ms = (time.perf_counter() - t0) * 1000.0
            success = 200 <= response.status_code < 300
            result = _RequestResult(
                request_id=request_id,
                timestamp=time.time(),
                latency_ms=latency_ms,
                success=success,
                status_code=response.status_code,
                error=None,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            result = _RequestResult(
                request_id=request_id,
                timestamp=time.time(),
                latency_ms=latency_ms,
                success=False,
                status_code=None,
                error=type(exc).__name__,
            )
        result_queue.put(result)
        request_queue.task_done()


def run_load(
    pattern_fn: Callable[..., Any],
    duration: float = 30.0,
    target_rps: int = 100,
    max_workers: int = 100,
) -> list[dict[str, Any]]:
    """Fire requests at target_rps for duration seconds using a bounded worker pool.

    Uses producer/consumer queues to avoid spawning unbounded threads under high
    concurrency and retry storms.
    """
    start_time = time.time()
    end_time = start_time + duration
    interval = 1.0 / target_rps
    next_request_time = start_time
    request_id = 0

    request_queue: queue.Queue[int] = queue.Queue(maxsize=max_workers)
    result_queue: queue.Queue[_RequestResult] = queue.Queue()
    stop_event = threading.Event()

    threads = [
        threading.Thread(target=_worker, args=(pattern_fn, request_queue, result_queue, stop_event), daemon=True)
        for _ in range(max_workers)
    ]
    for t in threads:
        t.start()

    try:
        while time.time() < end_time:
            now = time.time()
            if now >= next_request_time:
                try:
                    request_queue.put(request_id, timeout=2.0)
                    request_id += 1
                except queue.Full:
                    # Workers are saturated; skip this slot to avoid backlog.
                    pass
                next_request_time += interval
                if next_request_time < now:
                    next_request_time = now + interval
            else:
                sleep_until = min(next_request_time, end_time)
                remaining = sleep_until - time.time()
                if remaining > 0:
                    time.sleep(remaining)
    finally:
        stop_event.set()
        request_queue.join()
        for t in threads:
            t.join(timeout=1.0)

    records = []
    while not result_queue.empty():
        records.append(result_queue.get().to_dict())

    return records


def build_base_call(url: str = "http://127.0.0.1:5001/api/data", timeout: float = 10.0) -> Callable[..., Any]:
    """Return a requests.Session-backed closure with a larger connection pool."""

    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=50,
        pool_maxsize=200,
        max_retries=0,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    def call():
        return session.get(url, timeout=timeout)

    return call
