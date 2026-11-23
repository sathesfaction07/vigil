import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("content_guard")


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format=(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"service":"content_guard","module":"%(module)s","msg":"%(message)s"}'
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


class Metrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.timings: dict[str, list[float]] = {}
        self.start_time = time.time()

    def increment(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def record_timing(self, name: str, duration_ms: float) -> None:
        self.timings.setdefault(name, []).append(duration_ms)
        if len(self.timings[name]) > 1000:
            self.timings[name] = self.timings[name][-500:]

    def summary(self) -> dict[str, Any]:
        timing_summary = {}
        for key, values in self.timings.items():
            sorted_v = sorted(values)
            n = len(sorted_v)
            timing_summary[key] = {
                "count": n,
                "avg_ms": round(sum(sorted_v) / n, 1) if n else 0,
                "p50_ms": round(sorted_v[n // 2], 1) if n else 0,
                "p95_ms": round(sorted_v[int(n * 0.95)], 1) if n else 0,
                "p99_ms": round(sorted_v[int(n * 0.99)], 1) if n else 0,
            }
        return {
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "counters": dict(self.counters),
            "timings": timing_summary,
        }


metrics = Metrics()


def timed(metric_name: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                metrics.increment(f"{metric_name}.success")
                return result
            except Exception:
                metrics.increment(f"{metric_name}.error")
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.record_timing(metric_name, elapsed_ms)

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                metrics.increment(f"{metric_name}.success")
                return result
            except Exception:
                metrics.increment(f"{metric_name}.error")
                raise
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.record_timing(metric_name, elapsed_ms)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
