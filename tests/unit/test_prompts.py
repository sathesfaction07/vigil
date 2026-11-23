from content_guard.core.keywords import KeywordMatch
from content_guard.core.prompts import build_system_prompt, build_user_prompt


class TestPrompts:
    def test_system_prompt_contains_security_rules(self):
        prompt = build_system_prompt()
        assert "INSTRUCTION INTEGRITY" in prompt
        assert "DATA HANDLING" in prompt
        assert "OUTPUT ACCURACY" in prompt
        assert "ACTION BOUNDARIES" in prompt
        assert "NO FABRICATION" in prompt
        assert "JSON" in prompt

    def test_system_prompt_has_output_schema(self):
        prompt = build_system_prompt()
        assert '"classification"' in prompt
        assert '"confidence_pct"' in prompt
        assert '"evidence"' in prompt

    def test_user_prompt_includes_product_data(self):
        product = {
            "product_id": "SKU-123",
            "title": "Test Product",
            "brand": "TestBrand",
            "description": "A description",
            "marketplace": "US",
        }
        prompt = build_user_prompt(product, [])
        assert "SKU-123" in prompt
        assert "Test Product" in prompt
        assert "TestBrand" in prompt
        assert "A description" in prompt

    def test_user_prompt_includes_keyword_matches(self):
        matches = [
            KeywordMatch(
                keyword="adult only", language="en", category="red", field="title", context="..."
            ),
            KeywordMatch(
                keyword="family friendly",
                language="en",
                category="green",
                field="description",
                context="...",
            ),
        ]
        prompt = build_user_prompt({"product_id": "X", "title": "T", "marketplace": "US"}, matches)
        assert "VIOLATION signals" in prompt
        assert "adult only" in prompt
        assert "PRODUCT signals" in prompt
        assert "family friendly" in prompt

    def test_user_prompt_truncates_long_description(self):
        product = {
            "product_id": "X",
            "title": "T",
            "description": "x" * 1000,
            "marketplace": "US",
        }
        prompt = build_user_prompt(product, [])
        assert "..." in prompt
        assert len(prompt) < 2000

    def test_user_prompt_handles_bullet_points(self):
        product = {
            "product_id": "X",
            "title": "T",
            "bullet_points": ["bullet 1", "bullet 2", "bullet 3"],
            "marketplace": "US",
        }
        prompt = build_user_prompt(product, [])
        assert "Bullet 1:" in prompt
        assert "Bullet 3:" in prompt
