"""Composable client-side resilience patterns for HTTP calls."""

import random
import threading
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable


class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    pass


def naive_retry(
    fn: Callable[..., Any],
    max_attempts: int = 3,
    delay: float = 0.5,
) -> Callable[..., Any]:
    """Fixed-delay retry without jitter."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    time.sleep(delay)
        raise last_exc

    return wrapper


def retry_with_jitter(
    fn: Callable[..., Any],
    max_attempts: int = 3,
    base_delay: float = 0.2,
    max_delay: float = 2.0,
    exponential_base: float = 2.0,
) -> Callable[..., Any]:
    """Exponential backoff with full jitter."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    backoff = base_delay * (exponential_base ** attempt)
                    backoff = min(backoff, max_delay)
                    sleep_time = random.uniform(0, backoff)
                    time.sleep(sleep_time)
        raise last_exc

    return wrapper


def timeout_wrapper(fn: Callable[..., Any], seconds: float) -> Callable[..., Any]:
    """Inject a timeout keyword argument into a requests-style call."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return fn(*args, **kwargs)

    return wrapper


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        half_open_timeout: float = 10.0,
        success_threshold: int = 2,
        wrapped_call: Callable[..., Any] | None = None,
    ):
        self.failure_threshold = failure_threshold
        self.half_open_timeout = half_open_timeout
        self.success_threshold = success_threshold
        self.wrapped_call = wrapped_call

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state

    def _trip(self) -> None:
        self._state = CircuitBreakerState.OPEN
        self._last_failure_time = time.time()
        self._consecutive_failures = 0

    def _attempt_reset(self) -> bool:
        if time.time() - self._last_failure_time >= self.half_open_timeout:
            self._state = CircuitBreakerState.HALF_OPEN
            self._consecutive_successes = 0
            return True
        return False

    def call(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if not self._attempt_reset():
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if self._state == CircuitBreakerState.HALF_OPEN:
                    self._consecutive_successes += 1
                    if self._consecutive_successes >= self.success_threshold:
                        self._state = CircuitBreakerState.CLOSED
                        self._consecutive_successes = 0
                else:
                    self._consecutive_failures = 0
            return result
        except Exception as exc:
            with self._lock:
                self._consecutive_failures += 1
                if self._state == CircuitBreakerState.HALF_OPEN:
                    self._trip()
                elif self._consecutive_failures >= self.failure_threshold:
                    self._trip()
            raise exc

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            return self.call(fn, *args, **kwargs)

        return wrapper


class Bulkhead:
    """Semaphore-based concurrency limiter."""

    def __init__(self, max_concurrent: int):
        self._semaphore = threading.Semaphore(max_concurrent)

    def wrap(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            with self._semaphore:
                return fn(*args, **kwargs)

        return wrapper


# Convenience factory to build the exact configurations for the experiment.

def make_no_retry_call(base_call: Callable[..., Any]) -> Callable[..., Any]:
    return base_call


def make_naive_retry_call(base_call: Callable[..., Any]) -> Callable[..., Any]:
    return naive_retry(base_call, max_attempts=3, delay=0.5)


def make_retry_jitter_call(base_call: Callable[..., Any]) -> Callable[..., Any]:
    return retry_with_jitter(
        base_call,
        max_attempts=3,
        base_delay=0.2,
        max_delay=2.0,
        exponential_base=2.0,
    )


def make_retry_jitter_cb_call(base_call: Callable[..., Any], failure_threshold: int = 3) -> Callable[..., Any]:
    retry_call = make_retry_jitter_call(base_call)
    cb = CircuitBreaker(
        failure_threshold=failure_threshold,
        half_open_timeout=10.0,
        success_threshold=2,
    )
    return cb.wrap(retry_call)
