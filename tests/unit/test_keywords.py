import unicodedata


class TestKeywordEngine:
    def test_detects_english_red_keyword(self, keyword_engine):
        product = {"title": "This is an adult only product", "description": ""}
        matches = keyword_engine.detect(product)
        assert any(m.keyword == "adult only" and m.category == "red" for m in matches)

    def test_detects_english_green_keyword(self, keyword_engine):
        product = {"title": "Family friendly educational game", "description": ""}
        matches = keyword_engine.detect(product)
        assert any(m.keyword == "family friendly" and m.category == "green" for m in matches)

    def test_detects_german_keywords(self, keyword_engine):
        product = {"title": "Nur für erwachsene - Premium Produkt", "description": ""}
        matches = keyword_engine.detect(product)
        assert any(m.language == "de" and m.category == "red" for m in matches)

    def test_detects_japanese_keywords(self, keyword_engine):
        product = {"title": "この商品は18禁です", "description": ""}
        matches = keyword_engine.detect(product)
        assert any(m.language == "ja" and m.category == "red" for m in matches)

    def test_nfkc_normalization(self, keyword_engine):
        fullwidth_text = "１８＋"
        normalized = unicodedata.normalize("NFKC", fullwidth_text)
        assert normalized == "18+"
        product = {"title": f"Product {fullwidth_text} content", "description": ""}
        matches = keyword_engine.detect(product)
        assert any(m.keyword == "18+" for m in matches)

    def test_no_matches_for_clean_product(self, keyword_engine):
        product = {"title": "Wireless Bluetooth Headphones", "description": "High quality audio"}
        matches = keyword_engine.detect(product)
        assert len(matches) == 0

    def test_scans_all_fields(self, keyword_engine):
        product = {
            "title": "Normal product",
            "description": "This is explicit content",
            "bullet_points": ["certified safe item"],
            "brand": "SafeBrand",
        }
        matches = keyword_engine.detect(product)
        red = [m for m in matches if m.category == "red"]
        green = [m for m in matches if m.category == "green"]
        assert any(m.field == "description" for m in red)
        assert any(m.field == "bullet_points" for m in green)

    def test_context_extraction(self, keyword_engine):
        product = {"title": "Some text before adult only some text after", "description": ""}
        matches = keyword_engine.detect(product)
        assert matches[0].context
        assert "adult only" in matches[0].context

    def test_handles_empty_product(self, keyword_engine):
        matches = keyword_engine.detect({})
        assert matches == []

    def test_handles_list_bullet_points(self, keyword_engine):
        product = {"bullet_points": ["This is explicit", "Normal bullet"]}
        matches = keyword_engine.detect(product)
        assert len(matches) >= 1
