import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..enrichment.base import DetectedEntity
from ..observability import logger, metrics, timed
from .keywords import KeywordMatch
from .prompts import build_system_prompt, build_user_prompt


@dataclass
class ClassificationResult:
    classification: str  # "VIOLATION", "COMPLIANT", "UNCERTAIN"
    confidence_pct: float
    confidence_level: str  # "HIGH", "MEDIUM", "LOW"
    reasoning: str
    evidence: list[str]
    image_review_recommended: bool
    keyword_matches: list[KeywordMatch] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


class Classifier:
    def __init__(self, bedrock_client: Any) -> None:
        self.client = bedrock_client
        self.model_id = settings.bedrock_model
        self.max_retries = 3

    @timed("classification")
    def classify(
        self,
        product_data: dict[str, Any],
        keyword_matches: list[KeywordMatch],
        entities: list[DetectedEntity] | None = None,
        image_urls: list[str] | None = None,
    ) -> ClassificationResult:
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(product_data, keyword_matches, entities=entities or [])

        response = self._invoke_model(system_prompt, user_prompt, image_urls=image_urls or [])
        parsed = self._parse_response(response["content"])

        confidence = float(parsed.get("confidence_pct", 0))
        confidence_level = self._confidence_level(confidence)

        if confidence_level == "LOW" or parsed.get("image_review_recommended"):
            parsed["classification"] = "UNCERTAIN"

        metrics.increment(f"classification.{parsed['classification'].lower()}")

        return ClassificationResult(
            classification=parsed.get("classification", "UNCERTAIN"),
            confidence_pct=confidence,
            confidence_level=confidence_level,
            reasoning=parsed.get("reasoning", ""),
            evidence=parsed.get("evidence", []),
            image_review_recommended=parsed.get("image_review_recommended", False),
            keyword_matches=keyword_matches,
            token_usage=response.get("usage", {}),
        )

    def _invoke_model(
        self, system_prompt: str, user_prompt: str, image_urls: list[str] | None = None
    ) -> dict[str, Any]:
        content: list[dict] = []
        if image_urls:
            for url in image_urls[:4]:
                content.append({"type": "image", "source": {"type": "url", "url": url}})
        content.append({"type": "text", "text": user_prompt})

        for attempt in range(self.max_retries):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(
                        {
                            "anthropic_version": "bedrock-2023-05-31",
                            "max_tokens": 700,
                            "temperature": 0,
                            "system": [
                                {
                                    "type": "text",
                                    "text": system_prompt,
                                    "cache_control": {"type": "ephemeral"},
                                }
                            ],
                            "messages": [{"role": "user", "content": content}],
                        }
                    ),
                    contentType="application/json",
                )
                body = json.loads(response["body"].read())
                return {
                    "content": body["content"][0]["text"],
                    "usage": body.get("usage", {}),
                }
            except Exception as e:
                if "Throttling" in str(e) and attempt < self.max_retries - 1:
                    wait = (2**attempt) + 1
                    logger.warning(
                        f"Bedrock throttled, retrying in {wait}s (attempt {attempt + 1})"
                    )
                    time.sleep(wait)
                else:
                    raise

        return {"content": "{}", "usage": {}}

    def _parse_response(self, text: str) -> dict[str, Any]:
        # Tier 1: Standard JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Tier 2: Extract JSON block from text
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Tier 3: Regex field extraction
        logger.warning("Falling back to regex parsing for malformed AI response")
        metrics.increment("classification.parse_fallback")
        result: dict[str, Any] = {"classification": "UNCERTAIN", "confidence_pct": 0}
        classification_match = re.search(r'"classification"\s*:\s*"(\w+)"', text)
        if classification_match:
            result["classification"] = classification_match.group(1)
        confidence_match = re.search(r'"confidence_pct"\s*:\s*([\d.]+)', text)
        if confidence_match:
            result["confidence_pct"] = float(confidence_match.group(1))
        reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*)"', text)
        if reasoning_match:
            result["reasoning"] = reasoning_match.group(1)
        result["evidence"] = []
        return result

    @staticmethod
    def _confidence_level(confidence: float) -> str:
        if confidence >= 94:
            return "HIGH"
        elif confidence >= 90:
            return "MEDIUM"
        return "LOW"
