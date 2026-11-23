from unittest.mock import patch


class TestHealthEndpoint:
    def test_health_returns_200_when_redis_up(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.health_check.return_value = True
            response = client.get("/health")
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "healthy"
            assert data["checks"]["redis"] is True

    def test_health_returns_503_when_redis_down(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.health_check.return_value = False
            response = client.get("/health")
            assert response.status_code == 503
            data = response.get_json()
            assert data["status"] == "degraded"


class TestAnalyzeEndpoint:
    def test_analyze_accepts_valid_request(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.enqueue.return_value = "test-job-id"
            response = client.post(
                "/api/analyze",
                json={"product_id": "SKU-001", "marketplaces": ["US", "DE"]},
            )
            assert response.status_code == 202
            data = response.get_json()
            assert data["job_id"] == "test-job-id"
            assert data["status"] == "pending"

    def test_analyze_rejects_missing_product_id(self, client):
        response = client.post("/api/analyze", json={"marketplaces": ["US"]})
        assert response.status_code == 400

    def test_analyze_rejects_empty_body(self, client):
        response = client.post("/api/analyze", data="", content_type="application/json")
        assert response.status_code == 400


class TestBatchEndpoint:
    def test_batch_accepts_valid_list(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.enqueue.side_effect = lambda pid, mp: f"job-{pid}"
            response = client.post(
                "/api/batch",
                json={"product_ids": ["SKU-001", "SKU-002", "SKU-003"]},
            )
            assert response.status_code == 202
            data = response.get_json()
            assert data["count"] == 3
            assert len(data["job_ids"]) == 3

    def test_batch_rejects_too_many(self, client):
        ids = [f"SKU-{i}" for i in range(101)]
        response = client.post("/api/batch", json={"product_ids": ids})
        assert response.status_code == 400

    def test_batch_rejects_non_list(self, client):
        response = client.post("/api/batch", json={"product_ids": "single-id"})
        assert response.status_code == 400


class TestResultEndpoint:
    def test_result_returns_completed(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.get_status.return_value = "completed"
            mock_queue.get_result.return_value = {"classification": "COMPLIANT"}
            response = client.get("/api/result/test-job-id")
            assert response.status_code == 200
            data = response.get_json()
            assert data["result"]["classification"] == "COMPLIANT"

    def test_result_returns_202_for_pending(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.get_status.return_value = "pending"
            response = client.get("/api/result/test-job-id")
            assert response.status_code == 202

    def test_result_returns_404_for_unknown(self, client):
        with patch("content_guard.api.app.queue") as mock_queue:
            mock_queue.get_status.return_value = "unknown"
            response = client.get("/api/result/nonexistent")
            assert response.status_code == 404
