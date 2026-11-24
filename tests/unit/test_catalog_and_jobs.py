"""The catalog client and the Redis job queue, without a network or a Redis server.

CatalogService runs real httpx against httpx.MockTransport, so status codes, timeouts and
JSON decoding are exercised for real. JobQueue runs against an in-memory stand-in that
implements exactly the Redis commands it uses.
"""

import json

import httpx
import pytest

from content_guard.queue import jobs
from content_guard.queue.jobs import AnalysisJob, JobQueue, JobStatus
from content_guard.services import catalog
from content_guard.services.catalog import CatalogService


def use_transport(monkeypatch, handler):
    real_client = httpx.Client

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(catalog.httpx, "Client", client)


class TestCatalogService:
    def test_merges_every_marketplace_that_has_the_product(self, monkeypatch):
        def handler(request):
            mp = request.url.params["marketplace"]
            if mp == "UK":
                return httpx.Response(404)
            return httpx.Response(200, json={"title": f"Widget {mp}", "marketplace": mp})

        use_transport(monkeypatch, handler)
        data = CatalogService("http://catalog").fetch_product("SKU-1", ["US", "UK", "DE"])
        assert data["title"] == "Widget US"  # the first hit is primary
        assert set(data["marketplace_results"]) == {"US", "DE"}
        assert data["marketplaces_scanned"] == 3
        assert data["marketplaces_found"] == 2

    def test_requests_the_product_path_with_the_marketplace(self, monkeypatch):
        seen = []

        def handler(request):
            seen.append((request.url.path, request.url.params["marketplace"]))
            return httpx.Response(200, json={"title": "x"})

        use_transport(monkeypatch, handler)
        CatalogService("http://catalog").fetch_product("SKU-9", ["JP"])
        assert seen == [("/products/SKU-9", "JP")]

    def test_timeouts_and_server_errors_skip_a_marketplace_not_the_product(self, monkeypatch):
        def handler(request):
            mp = request.url.params["marketplace"]
            if mp == "US":
                raise httpx.ReadTimeout("slow", request=request)
            if mp == "DE":
                return httpx.Response(503)
            return httpx.Response(200, json={"title": "Widget FR"})

        use_transport(monkeypatch, handler)
        data = CatalogService("http://catalog").fetch_product("SKU-1", ["US", "DE", "FR"])
        assert data["marketplaces_found"] == 1
        assert list(data["marketplace_results"]) == ["FR"]

    def test_no_marketplace_answering_is_an_empty_result(self, monkeypatch):
        use_transport(monkeypatch, lambda request: httpx.Response(404))
        assert CatalogService("http://catalog").fetch_product("SKU-1", ["US", "DE"]) == {}

    def test_defaults_to_the_priority_list_capped_by_settings(self, monkeypatch):
        asked = []

        def handler(request):
            asked.append(request.url.params["marketplace"])
            return httpx.Response(404)

        use_transport(monkeypatch, handler)
        monkeypatch.setattr(catalog.settings, "max_marketplaces", 3)
        CatalogService("http://catalog").fetch_product("SKU-1")
        assert asked == catalog.MARKETPLACE_PRIORITY[:3]


class FakeRedis:
    """Just the commands JobQueue uses, with Redis's semantics for them."""

    def __init__(self):
        self.lists, self.kv, self.published = {}, {}, []
        self.up = True

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def blpop(self, key, timeout=0):
        items = self.lists.get(key) or []
        return (key, items.pop(0)) if items else None

    def set(self, key, value, ex=None):
        self.kv[key] = value.value if isinstance(value, JobStatus) else value

    def get(self, key):
        return self.kv.get(key)

    def publish(self, channel, message):
        self.published.append((channel, json.loads(message)))

    def ping(self):
        if not self.up:
            raise ConnectionError("redis down")
        return True


@pytest.fixture
def queue(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(jobs.redis.Redis, "from_url", lambda *a, **k: fake)
    q = JobQueue("redis://test")
    q.fake = fake
    return q


class TestJobQueue:
    def test_a_job_round_trips_through_the_queue_in_order(self, queue):
        first = queue.enqueue("SKU-1", ["US"])
        second = queue.enqueue("SKU-2")
        assert queue.get_status(first) == "pending"
        job = queue.dequeue()
        assert (job.job_id, job.product_id, job.marketplaces) == (first, "SKU-1", ["US"])
        assert queue.dequeue().job_id == second
        assert queue.dequeue() is None

    def test_a_stored_result_completes_the_job_and_notifies_listeners(self, queue):
        job_id = queue.enqueue("SKU-1")
        queue.publish_progress(job_id, "scanning")
        queue.store_result(job_id, {"verdict": "RED"})
        assert queue.get_result(job_id) == {"verdict": "RED"}
        assert queue.get_status(job_id) == "completed"
        kinds = [msg["type"] for channel, msg in queue.fake.published if job_id in channel]
        assert kinds == ["progress", "complete"]

    def test_a_failed_job_records_its_error(self, queue):
        job_id = queue.enqueue("SKU-1")
        queue.mark_failed(job_id, "catalog down")
        assert queue.get_status(job_id) == "failed"
        assert queue.fake.kv[f"{jobs.RESULT_PREFIX}{job_id}:error"] == "catalog down"
        assert queue.get_result(job_id) is None

    def test_an_unknown_job_is_reported_as_unknown(self, queue):
        assert queue.get_status("nope") == "unknown"

    def test_health_check_reflects_redis(self, queue):
        assert queue.health_check() is True
        queue.fake.up = False
        assert queue.health_check() is False


def test_jobs_serialise_losslessly():
    job = AnalysisJob(job_id="j1", product_id="SKU-1", marketplaces=["US", "DE"])
    assert AnalysisJob.from_json(job.to_json()) == job
