from content_guard.core.classifier import Classifier
from content_guard.core.keywords import KeywordEngine


class TestFullPipeline:
    def test_violation_product_classified_correctly(self, sample_products, mock_bedrock_client):
        adult_product = sample_products[1]

        engine = KeywordEngine()
        matches = engine.detect(adult_product)

        assert len(matches) > 0
        assert any(m.category == "red" for m in matches)

        classifier = Classifier(mock_bedrock_client)
        result = classifier.classify(adult_product, matches)

        assert result.classification == "VIOLATION"
        assert result.confidence_level == "HIGH"

    def test_clean_product_no_keywords(self, sample_products):
        headphones = sample_products[3]

        engine = KeywordEngine()
        matches = engine.detect(headphones)

        assert len(matches) == 0

    def test_green_signals_detected_for_safe_product(self, sample_products):
        kids_product = sample_products[0]

        engine = KeywordEngine()
        matches = engine.detect(kids_product)

        green_matches = [m for m in matches if m.category == "green"]
        assert len(green_matches) >= 1
        assert any(
            "family friendly" in m.keyword or "certified safe" in m.keyword for m in green_matches
        )

    def test_german_marketplace_detection(self, sample_products, mock_bedrock_client):
        german_product = sample_products[2]

        engine = KeywordEngine()
        matches = engine.detect(german_product)

        red_matches = [m for m in matches if m.category == "red"]
        assert any(m.language == "de" for m in red_matches)

    def test_pipeline_handles_empty_product_gracefully(self, mock_bedrock_client):
        empty_product = {"product_id": "EMPTY", "title": "", "description": "", "marketplace": "US"}

        engine = KeywordEngine()
        matches = engine.detect(empty_product)
        assert matches == []

        classifier = Classifier(mock_bedrock_client)
        result = classifier.classify(empty_product, matches)
        assert result.classification in ("VIOLATION", "COMPLIANT", "UNCERTAIN")
