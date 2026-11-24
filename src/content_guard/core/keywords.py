import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ..observability import logger, metrics, timed


@dataclass
class KeywordMatch:
    keyword: str
    language: str
    category: str  # "red" (violation) or "green" (product signal)
    field: str  # which product field matched
    context: str  # surrounding text snippet


class KeywordEngine:
    def __init__(self, keywords_path: Path | None = None) -> None:
        if keywords_path is None:
            keywords_path = Path(__file__).parent.parent.parent.parent / "data" / "keywords.json"
        self.keywords: dict[str, dict[str, list[str]]] = self._load(keywords_path)

    def _load(self, path: Path) -> dict[str, dict[str, list[str]]]:
        if not path.exists():
            logger.warning(f"Keywords file not found at {path}, using empty set")
            return {}
        with open(path, encoding="utf-8") as f:
            return cast(dict[str, dict[str, list[str]]], json.load(f))

    @timed("keyword_detection")
    def detect(self, product_data: dict[str, Any]) -> list[KeywordMatch]:
        matches: list[KeywordMatch] = []
        fields_to_scan = ["title", "description", "bullet_points", "brand"]

        for field in fields_to_scan:
            raw_value = product_data.get(field, "")
            if isinstance(raw_value, list):
                raw_value = " ".join(raw_value)
            if not raw_value:
                continue

            normalized = self._normalize(raw_value)

            for language, categories in self.keywords.items():
                for category, keyword_list in categories.items():
                    for keyword in keyword_list:
                        norm_keyword = self._normalize(keyword)
                        if norm_keyword in normalized:
                            idx = normalized.find(norm_keyword)
                            context_start = max(0, idx - 30)
                            context_end = min(len(raw_value), idx + len(keyword) + 30)
                            matches.append(
                                KeywordMatch(
                                    keyword=keyword,
                                    language=language,
                                    category=category,
                                    field=field,
                                    context=raw_value[context_start:context_end],
                                )
                            )

        metrics.increment("keywords.total_matches", len(matches))
        logger.info(f"Keyword detection found {len(matches)} matches")
        return matches

    def _normalize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        return normalized.lower()
