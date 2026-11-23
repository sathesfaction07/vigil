import json
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import redis

from ..config import settings
from ..observability import logger

QUEUE_KEY = "contentguard:jobs"
RESULT_PREFIX = "contentguard:result:"
PROGRESS_PREFIX = "contentguard:progress:"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisJob:
    job_id: str
    product_id: str
    marketplaces: list[str]
    status: str = JobStatus.PENDING

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "AnalysisJob":
        return cls(**json.loads(data))


class JobQueue:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis = redis.Redis.from_url(redis_url or settings.redis_url, decode_responses=True)

    def enqueue(self, product_id: str, marketplaces: list[str] | None = None) -> str:
        job_id = str(uuid.uuid4())
        job = AnalysisJob(
            job_id=job_id,
            product_id=product_id,
            marketplaces=marketplaces or [],
        )
        self.redis.rpush(QUEUE_KEY, job.to_json())
        self.redis.set(
            f"{RESULT_PREFIX}{job_id}:status", JobStatus.PENDING, ex=settings.result_ttl_seconds
        )
        logger.info(f"Enqueued job {job_id} for product {product_id}")
        return job_id

    def dequeue(self, timeout: int = 5) -> AnalysisJob | None:
        result = self.redis.blpop(QUEUE_KEY, timeout=timeout)
        if result is None:
            return None
        _, job_data = result
        return AnalysisJob.from_json(job_data)

    def publish_progress(self, job_id: str, message: str) -> None:
        channel = f"{PROGRESS_PREFIX}{job_id}"
        self.redis.publish(channel, json.dumps({"type": "progress", "message": message}))

    def store_result(self, job_id: str, result: dict[str, Any]) -> None:
        key = f"{RESULT_PREFIX}{job_id}"
        self.redis.set(key, json.dumps(result), ex=settings.result_ttl_seconds)
        self.redis.set(f"{key}:status", JobStatus.COMPLETED, ex=settings.result_ttl_seconds)
        self.redis.publish(
            f"{PROGRESS_PREFIX}{job_id}",
            json.dumps({"type": "complete", "result": result}),
        )
        logger.info(f"Stored result for job {job_id}")

    def mark_failed(self, job_id: str, error: str) -> None:
        key = f"{RESULT_PREFIX}{job_id}"
        self.redis.set(f"{key}:status", JobStatus.FAILED, ex=settings.result_ttl_seconds)
        self.redis.set(f"{key}:error", error, ex=settings.result_ttl_seconds)

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        key = f"{RESULT_PREFIX}{job_id}"
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    def get_status(self, job_id: str) -> str:
        return self.redis.get(f"{RESULT_PREFIX}{job_id}:status") or "unknown"

    def health_check(self) -> bool:
        try:
            return self.redis.ping()
        except Exception:
            return False
