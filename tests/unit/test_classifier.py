import json

from content_guard.core.classifier import ClassificationResult, Classifier
from content_guard.core.keywords import KeywordMatch


class TestClassifier:
    def test_classify_returns_result(self, mock_bedrock_client, mock_bedrock_response):
        classifier = Classifier(mock_bedrock_client)
        product_data = {"product_id": "SKU-001", "title": "Adult Product", "marketplace": "US"}
        keyword_matches = [
            KeywordMatch(
                keyword="adult",
                language="en",
                category="red",
                field="title",
                context="Adult Product",
            )
        ]
        result = classifier.classify(product_data, keyword_matches)

        assert isinstance(result, ClassificationResult)
        assert result.classification == "VIOLATION"
        assert result.confidence_pct == 96.5
        assert result.confidence_level == "HIGH"
        assert len(result.evidence) == 2

    def test_low_confidence_becomes_uncertain(self, mock_bedrock_client):
        low_conf_response = json.dumps(
            {
                "classification": "VIOLATION",
                "confidence_pct": 65.0,
                "reasoning": "Weak signal",
                "evidence": ["signal 1"],
                "image_review_recommended": False,
            }
        ).encode()
        body_mock = mock_bedrock_client.invoke_model.return_value["body"]
        body_mock.read.return_value = json.dumps(
            {
                "content": [{"text": low_conf_response.decode()}],
                "usage": {},
            }
        ).encode()

        classifier = Classifier(mock_bedrock_client)
        result = classifier.classify({"product_id": "X", "title": "Y", "marketplace": "US"}, [])
        assert result.classification == "UNCERTAIN"
        assert result.confidence_level == "LOW"

    def test_confidence_levels(self):
        assert Classifier._confidence_level(95) == "HIGH"
        assert Classifier._confidence_level(94) == "HIGH"
        assert Classifier._confidence_level(93.5) == "MEDIUM"
        assert Classifier._confidence_level(90) == "MEDIUM"
        assert Classifier._confidence_level(89.9) == "LOW"
        assert Classifier._confidence_level(50) == "LOW"

    def test_parse_response_valid_json(self, mock_bedrock_client):
        classifier = Classifier(mock_bedrock_client)
        valid = '{"classification": "COMPLIANT", "confidence_pct": 97, "reasoning": "OK", "evidence": ["e1"], "image_review_recommended": false}'
        result = classifier._parse_response(valid)
        assert result["classification"] == "COMPLIANT"

    def test_parse_response_json_in_text(self, mock_bedrock_client):
        classifier = Classifier(mock_bedrock_client)
        messy = 'Here is my analysis:\n{"classification": "VIOLATION", "confidence_pct": 88}\nEnd.'
        result = classifier._parse_response(messy)
        assert result["classification"] == "VIOLATION"

    def test_parse_response_fallback_regex(self, mock_bedrock_client):
        classifier = Classifier(mock_bedrock_client)
        broken = '"classification": "COMPLIANT", "confidence_pct": 92.5, "reasoning": "looks fine"'
        result = classifier._parse_response(broken)
        assert result["classification"] == "COMPLIANT"
        assert result["confidence_pct"] == 92.5
