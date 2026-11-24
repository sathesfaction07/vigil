import logging
from typing import Any, cast

import boto3

from .base import DetectedEntity, EntityEnricher

logger = logging.getLogger("content_guard")


class ComprehendEnricher(EntityEnricher):
    def __init__(self, region: str = "us-east-1", **kwargs: Any) -> None:
        self.client = boto3.client("comprehend", region_name=region)

    def detect_entities(self, product_data: dict[str, Any]) -> list[DetectedEntity]:
        text = self._combine_text(product_data)
        if not text:
            return []

        language = self.detect_language(text)

        try:
            response = self.client.detect_entities(Text=text[:4500], LanguageCode=language)
        except Exception as e:
            logger.warning(f"Comprehend entity detection failed: {e}")
            return []

        entities = []
        for entity in response.get("Entities", []):
            if entity["Score"] < 0.7:
                continue
            entities.append(
                DetectedEntity(
                    text=entity["Text"],
                    entity_type=entity["Type"],
                    confidence=entity["Score"],
                    field="combined",
                )
            )

        logger.info(f"Comprehend found {len(entities)} entities (language: {language})")
        return entities

    def detect_language(self, text: str) -> str:
        try:
            response = self.client.detect_dominant_language(Text=text[:300])
            languages = response.get("Languages", [])
            if languages:
                return cast(str, languages[0]["LanguageCode"])
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
