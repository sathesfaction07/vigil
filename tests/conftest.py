import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from content_guard.api.app import app as flask_app
from content_guard.core.keywords import KeywordEngine


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def sample_products():
    path = Path(__file__).parent.parent / "data" / "sample_products.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def keyword_engine():
    return KeywordEngine()


@pytest.fixture
def mock_bedrock_response():
    return {
        "classification": "VIOLATION",
        "confidence_pct": 96.5,
        "reasoning": "Product title contains 'adult only' keyword. Age attribute confirms 18+ target.",
        "evidence": ["Title: 'Adult Formula'", "Attribute: target_age=18+"],
        "image_review_recommended": False,
    }


@pytest.fixture
def mock_bedrock_client(mock_bedrock_response):
    client = MagicMock()
    response_body = MagicMock()
    response_body.read.return_value = json.dumps(
        {
            "content": [{"text": json.dumps(mock_bedrock_response)}],
            "usage": {"input_tokens": 500, "output_tokens": 150},
        }
    ).encode()
    client.invoke_model.return_value = {"body": response_body}
    return client


@pytest.fixture
def mock_redis():
    try:
        import fakeredis

        return fakeredis.FakeRedis(decode_responses=True)
    except ImportError:
        pytest.skip("fakeredis not installed")
