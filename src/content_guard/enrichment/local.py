import logging
import re

from .base import DetectedEntity, EntityEnricher

logger = logging.getLogger("content_guard")

AGE_PATTERNS = [
    (r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?|ans)\b", "AGE"),
    (r"\bage[sd]?\s*(\d{1,2})\s*(?:to|-)?\s*(\d{1,2})?\b", "AGE"),
    (r"\b(?:children|kids|toddler|infant|baby|child)\b", "AGE_INDICATOR"),
    (r"\b(?:adult|mature|18\+|21\+)\b", "AGE_INDICATOR"),
]

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "PII_EMAIL"),
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "PII_PHONE"),
]


class LocalEnricher(EntityEnricher):
    def detect_entities(self, product_data: dict) -> list[DetectedEntity]:
        entities = []

        for field in ["title", "description", "bullet_points"]:
            value = product_data.get(field, "")
            if isinstance(value, list):
                value = " ".join(value)
            if not value:
                continue

            for pattern, entity_type in AGE_PATTERNS + PII_PATTERNS:
                for match in re.finditer(pattern, value, re.IGNORECASE):
                    entities.append(
                        DetectedEntity(
                            text=match.group(),
                            entity_type=entity_type,
                            confidence=0.85,
                            field=field,
                        )
                    )

        return entities

    def detect_language(self, text: str) -> str:
        try:
            from langdetect import detect

            return detect(text[:500])
        except Exception:
            return "en"
