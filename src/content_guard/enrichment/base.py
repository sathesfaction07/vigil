from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DetectedEntity:
    text: str
    entity_type: str  # "AGE", "PERSON", "ORGANIZATION", "PII", "PRODUCT_TYPE"
    confidence: float
    field: str


class EntityEnricher(ABC):
    @abstractmethod
    def detect_entities(self, product_data: dict[str, Any]) -> list[DetectedEntity]: ...

    @abstractmethod
    def detect_language(self, text: str) -> str: ...
