import csv
import io
import json
from collections.abc import Iterator

from flask import Flask, Response, jsonify, request
from flask.typing import ResponseReturnValue

from ..config import settings
from ..observability import logger, metrics, setup_logging
from ..queue.jobs import JobQueue

app = Flask(__name__)
queue = JobQueue()


@app.before_request
def count_request() -> None:
    metrics.increment("http.requests")


@app.route("/health")
def health() -> ResponseReturnValue:
    redis_ok = queue.health_check()
    checks = {"redis": redis_ok}
    status = "healthy" if all(checks.values()) else "degraded"
    code = 200 if status == "healthy" else 503
    return jsonify(
        {
            "status": status,
            "checks": checks,
            "enricher": settings.enricher,
            "multimodal": settings.multimodal,
            **metrics.summary(),
        }
    ), code


@app.route("/metrics")
def get_metrics() -> ResponseReturnValue:
    return jsonify(metrics.summary())


@app.route("/api/analyze", methods=["POST"])
def analyze() -> ResponseReturnValue:
    data = request.get_json()
    if not data or "product_id" not in data:
        return jsonify({"error": "product_id is required"}), 400

    product_id = data["product_id"]
    marketplaces = data.get("marketplaces", [])

    job_id = queue.enqueue(product_id, marketplaces)
    metrics.increment("jobs.enqueued")

    return jsonify({"job_id": job_id, "status": "pending"}), 202


@app.route("/api/batch", methods=["POST"])
def batch_analyze() -> ResponseReturnValue:
    data = request.get_json()
    if not data or "product_ids" not in data:
        return jsonify({"error": "product_ids is required"}), 400

    product_ids = data["product_ids"]
    if not isinstance(product_ids, list) or len(product_ids) > 100:
        return jsonify({"error": "product_ids must be a list of max 100 items"}), 400

    marketplaces = data.get("marketplaces", [])
    job_ids = []
    for pid in product_ids:
        job_id = queue.enqueue(pid, marketplaces)
        job_ids.append(job_id)

    metrics.increment("jobs.enqueued", len(job_ids))
    return jsonify({"job_ids": job_ids, "count": len(job_ids)}), 202


@app.route("/api/batch/csv", methods=["POST"])
def batch_csv() -> ResponseReturnValue:
    if "file" not in request.files:
        return jsonify({"error": "CSV file required (field name: 'file')"}), 400

    csv_file = request.files["file"]
    content = csv_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    job_ids = []
    for row in reader:
        product_id = row.get("product_id") or row.get("id") or row.get("sku")
        if not product_id:
            continue
        marketplaces = [m.strip() for m in row.get("marketplaces", "").split(",") if m.strip()]
        job_id = queue.enqueue(product_id, marketplaces)
        job_ids.append({"product_id": product_id, "job_id": job_id})

    metrics.increment("jobs.enqueued", len(job_ids))
    return jsonify({"jobs": job_ids, "count": len(job_ids)}), 202


@app.route("/api/results/csv")
def export_csv() -> ResponseReturnValue:
    job_ids = request.args.get("job_ids", "").split(",")
    if not job_ids or job_ids == [""]:
        return jsonify({"error": "job_ids query param required (comma-separated)"}), 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "product_id",
            "classification",
            "confidence_pct",
            "confidence_level",
            "reasoning",
            "evidence",
            "missing_signals",
        ]
    )

    for job_id in job_ids:
        result = queue.get_result(job_id.strip())
        if result:
            writer.writerow(
                [
                    result.get("product_id", ""),
                    result.get("classification", ""),
                    result.get("confidence_pct", ""),
                    result.get("confidence_level", ""),
                    result.get("reasoning", ""),
                    "; ".join(result.get("evidence", [])),
                    "",
                ]
            )

    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )


@app.route("/api/stream/<job_id>")
def stream(job_id: str) -> ResponseReturnValue:
    def event_stream() -> Iterator[str]:
        pubsub = queue.redis.pubsub()
        channel = f"contentguard:progress:{job_id}"
        pubsub.subscribe(channel)

        try:
            # redis-py's PubSub ships without type annotations
            for message in pubsub.listen():  # type: ignore[no-untyped-call]
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    parsed = json.loads(data)
                    if parsed.get("type") in ("complete", "failed"):
                        break
        finally:
            pubsub.unsubscribe(channel)  # type: ignore[no-untyped-call]
            pubsub.close()

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/result/<job_id>")
def get_result(job_id: str) -> ResponseReturnValue:
    status = queue.get_status(job_id)
    if status == "unknown":
        return jsonify({"error": "Job not found"}), 404
    if status == "pending" or status == "processing":
        return jsonify({"status": status}), 202

    result = queue.get_result(job_id)
    if result is None:
        return jsonify({"error": "Result expired"}), 410

    return jsonify({"status": "completed", "result": result})


def create_app() -> Flask:
    setup_logging(settings.log_level)
    logger.info("Vigil API starting")
    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=5050, debug=True)
