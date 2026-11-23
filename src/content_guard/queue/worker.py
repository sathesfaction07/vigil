import signal
from dataclasses import asdict

import boto3

from ..config import settings
from ..core.classifier import Classifier
from ..core.keywords import KeywordEngine
from ..enrichment import get_enricher
from ..observability import logger, metrics, setup_logging
from ..services.catalog import CatalogService
from .jobs import JobQueue


class Worker:
    def __init__(self) -> None:
        self.queue = JobQueue()
        self.catalog = CatalogService()
        self.keywords = KeywordEngine()
        self.classifier = Classifier(
            boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        )
        self.enricher = get_enricher(settings.enricher, region=settings.bedrock_region)
        self.running = True

    def start(self) -> None:
        setup_logging(settings.log_level)
        logger.info(
            f"Worker starting (enricher={settings.enricher}, multimodal={settings.multimodal})"
        )

        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        while self.running:
            job = self.queue.dequeue(timeout=5)
            if job is None:
                continue

            logger.info(f"Processing job {job.job_id} for product {job.product_id}")
            self.queue.publish_progress(job.job_id, "Processing started")

            try:
                self._process(job)
            except Exception as e:
                logger.error(f"Job {job.job_id} failed: {e}")
                self.queue.mark_failed(job.job_id, str(e))
                metrics.increment("worker.job_failed")

    def _process(self, job) -> None:
        self.queue.publish_progress(job.job_id, "Fetching catalog data...")
        product_data = self.catalog.fetch_product(job.product_id, job.marketplaces or None)

        if not product_data:
            self.queue.mark_failed(job.job_id, "No catalog data found")
            return

        self.queue.publish_progress(job.job_id, "Running keyword detection...")
        keyword_matches = self.keywords.detect(product_data)

        entities = []
        detected_language = "en"
        if self.enricher:
            self.queue.publish_progress(job.job_id, "Running entity detection...")
            entities = self.enricher.detect_entities(product_data)
            detected_language = self.enricher.detect_language(
                product_data.get("title", "") + " " + product_data.get("description", "")
            )

        image_urls = product_data.get("image_urls", []) if settings.multimodal else []

        self.queue.publish_progress(
            job.job_id,
            f"Classifying... ({len(keyword_matches)} keywords, {len(entities)} entities)",
        )
        result = self.classifier.classify(
            product_data, keyword_matches, entities=entities, image_urls=image_urls
        )

        result_dict = {
            "classification": result.classification,
            "confidence_pct": result.confidence_pct,
            "confidence_level": result.confidence_level,
            "reasoning": result.reasoning,
            "evidence": result.evidence,
            "image_review_recommended": result.image_review_recommended,
            "keyword_matches": [asdict(m) for m in result.keyword_matches],
            "entities_detected": [asdict(e) for e in entities],
            "detected_language": detected_language,
            "token_usage": result.token_usage,
            "product_id": job.product_id,
            "marketplaces_scanned": product_data.get("marketplaces_scanned", 0),
            "multimodal": len(image_urls) > 0,
        }

        self.queue.store_result(job.job_id, result_dict)
        metrics.increment("worker.job_completed")
        logger.info(
            f"Job {job.job_id} complete: {result.classification} "
            f"({result.confidence_pct}% {result.confidence_level})"
        )

    def _shutdown(self, signum, frame) -> None:
        logger.info("Shutdown signal received, finishing current job...")
        self.running = False


def main() -> None:
    worker = Worker()
    worker.start()


if __name__ == "__main__":
    main()
