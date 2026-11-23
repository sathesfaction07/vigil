from unittest.mock import MagicMock, patch

from content_guard.enrichment.google_nlp import GoogleNLPEnricher
from content_guard.enrichment.local import LocalEnricher


class TestLocalEnricher:
    def setup_method(self):
        self.enricher = LocalEnricher()

    def test_detects_age_number(self):
        product = {"title": "Toy for ages 3 to 8", "description": "", "bullet_points": []}
        entities = self.enricher.detect_entities(product)
        assert any(e.entity_type == "AGE" for e in entities)

    def test_detects_age_indicator(self):
        product = {"title": "Children's educational game", "description": "", "bullet_points": []}
        entities = self.enricher.detect_entities(product)
        assert any(e.entity_type == "AGE_INDICATOR" for e in entities)

    def test_detects_adult_indicator(self):
        product = {"title": "Adult supplement 18+", "description": "", "bullet_points": []}
        entities = self.enricher.detect_entities(product)
        age_entities = [e for e in entities if "AGE" in e.entity_type]
        assert len(age_entities) >= 1

    def test_detects_pii_email(self):
        product = {
            "title": "Product",
            "description": "Contact merchant@example.com for info",
            "bullet_points": [],
        }
        entities = self.enricher.detect_entities(product)
        assert any(e.entity_type == "PII_EMAIL" for e in entities)

    def test_no_entities_in_clean_product(self):
        product = {
            "title": "Wireless Bluetooth Headphones",
            "description": "High quality audio",
            "bullet_points": [],
        }
        entities = self.enricher.detect_entities(product)
        assert len(entities) == 0

    def test_scans_bullet_points(self):
        product = {"title": "Product", "description": "", "bullet_points": ["For kids ages 5-12"]}
        entities = self.enricher.detect_entities(product)
        assert any(e.field == "bullet_points" for e in entities)

    def test_language_detection_defaults_to_english(self):
        lang = self.enricher.detect_language("This is English text")
        assert lang == "en"


class TestGoogleNLPEnricher:
    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_detects_entities_successfully(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_entity = MagicMock()
        mock_entity.name = "TechCorp"
        mock_entity.type_.name = "ORGANIZATION"
        mock_entity.salience = 0.85

        mock_response = MagicMock()
        mock_response.entities = [mock_entity]
        mock_client.analyze_entities.return_value = mock_response

        enricher = GoogleNLPEnricher()
        product = {"title": "TechCorp laptop", "description": "", "bullet_points": []}
        entities = enricher.detect_entities(product)

        assert len(entities) == 1
        assert entities[0].text == "TechCorp"
        assert entities[0].entity_type == "ORGANIZATION"
        assert entities[0].confidence == 0.85

    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_filters_low_salience_entities(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_high = MagicMock()
        mock_high.name = "ImportantEntity"
        mock_high.type_.name = "PERSON"
        mock_high.salience = 0.9

        mock_low = MagicMock()
        mock_low.name = "MinorEntity"
        mock_low.type_.name = "OTHER"
        mock_low.salience = 0.3

        mock_response = MagicMock()
        mock_response.entities = [mock_high, mock_low]
        mock_client.analyze_entities.return_value = mock_response

        enricher = GoogleNLPEnricher()
        product = {"title": "Test product", "description": "", "bullet_points": []}
        entities = enricher.detect_entities(product)

        assert len(entities) == 1
        assert entities[0].text == "ImportantEntity"

    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_returns_empty_list_for_blank_product(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        enricher = GoogleNLPEnricher()
        product = {"title": "", "description": "", "bullet_points": []}
        entities = enricher.detect_entities(product)

        assert entities == []
        mock_client.analyze_entities.assert_not_called()

    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_handles_api_error_gracefully(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.analyze_entities.side_effect = Exception("API error")

        enricher = GoogleNLPEnricher()
        product = {"title": "Product", "description": "", "bullet_points": []}
        entities = enricher.detect_entities(product)

        assert entities == []

    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_detect_language_returns_language_code(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.language = "es"
        mock_client.analyze_sentiment.return_value = mock_response

        enricher = GoogleNLPEnricher()
        lang = enricher.detect_language("Hola mundo")

        assert lang == "es"

    @patch("content_guard.enrichment.google_nlp.language_v1.LanguageServiceClient")
    def test_detect_language_defaults_to_english_on_error(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.analyze_sentiment.side_effect = Exception("API error")

        enricher = GoogleNLPEnricher()
        lang = enricher.detect_language("Test text")

        assert lang == "en"
