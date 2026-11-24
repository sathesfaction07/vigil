import logging
from typing import Any

from google.cloud import language_v1

from .base import DetectedEntity, EntityEnricher

logger = logging.getLogger("content_guard")


class GoogleNLPEnricher(EntityEnricher):
    def __init__(self, **kwargs: Any) -> None:
        self.client = language_v1.LanguageServiceClient()

    def detect_entities(self, product_data: dict[str, Any]) -> list[DetectedEntity]:
        text = self._combine_text(product_data)
        if not text:
            return []

        try:
            document = language_v1.Document(
                content=text[:4500], type_=language_v1.Document.Type.PLAIN_TEXT
            )
            response = self.client.analyze_entities(document=document)
        except Exception as e:
            logger.warning(f"Google NLP entity detection failed: {e}")
            return []

        entities = []
        for entity in response.entities:
            if entity.salience < 0.7:
                continue
            entities.append(
                DetectedEntity(
                    text=entity.name,
                    entity_type=entity.type_.name,
                    confidence=entity.salience,
                    field="combined",
                )
            )

        logger.info(f"Google NLP found {len(entities)} entities")
        return entities

    def detect_language(self, text: str) -> str:
        try:
            document = language_v1.Document(
                content=text[:300], type_=language_v1.Document.Type.PLAIN_TEXT
            )
            response = self.client.analyze_sentiment(document=document)
            return response.language
        except Exception:
            pass
        return "en"

    def _combine_text(self, product_data: dict[str, Any]) -> str:
        parts = []
        for field in ["title", "description", "bullet_points", "brand"]:
            value = product_data.get(field, "")
            if isinstance(value, list):
                value = " ".join(value)
            if value:
                parts.append(value)
        return " ".join(parts)[:5000]
