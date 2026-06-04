"""
API endpoint tests using FastAPI's TestClient.
Run with: pytest tests/test_api.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client (no real server needed)."""
    from api.main import app

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "models" in data

    def test_health_has_model_names(self, client):
        data = client.get("/health").json()
        assert "stt" in data["models"]
        assert "llm" in data["models"]
        assert "tts" in data["models"]


class TestProductsEndpoint:
    def test_products_returns_list(self, client):
        res = client.get("/v1/products")
        assert res.status_code == 200
        products = res.json()
        assert isinstance(products, list)
        assert len(products) > 0

    def test_products_have_required_fields(self, client):
        products = client.get("/v1/products").json()
        for p in products[:5]:
            assert "id" in p
            assert "name" in p
            assert "price" in p
            assert "rating" in p

    def test_all_prices_positive(self, client):
        products = client.get("/v1/products").json()
        for p in products:
            assert p["price"] > 0


class TestShopEndpoint:
    def test_text_input_returns_response(self, client):
        res = client.post(
            "/v1/shop", data={"text": "Show me red shoes", "skip_tts": "true"}
        )
        assert res.status_code == 200
        data = res.json()
        assert "response_text" in data
        assert "ui_actions" in data
        assert "intent" in data
        assert "transcript" in data

    def test_no_input_returns_422(self, client):
        res = client.post("/v1/shop")
        assert res.status_code == 422

    def test_empty_text_returns_422(self, client):
        res = client.post("/v1/shop", data={"text": "   ", "skip_tts": "true"})
        assert res.status_code in (400, 422)

    def test_response_has_valid_confidence(self, client):
        res = client.post(
            "/v1/shop", data={"text": "Show me yoga mat", "skip_tts": "true"}
        )
        data = res.json()
        assert 0.0 <= data["confidence"] <= 1.0

    def test_ui_actions_are_list(self, client):
        res = client.post(
            "/v1/shop", data={"text": "Show me electronics", "skip_tts": "true"}
        )
        data = res.json()
        assert isinstance(data["ui_actions"], list)

    def test_latency_ms_present(self, client):
        res = client.post(
            "/v1/shop", data={"text": "Best running shoes", "skip_tts": "true"}
        )
        data = res.json()
        assert "latency_ms" in data
        assert data["latency_ms"]["total_ms"] > 0

    def test_off_topic_query(self, client):
        res = client.post(
            "/v1/shop",
            data={"text": "What is the capital of India?", "skip_tts": "true"},
        )
        assert res.status_code == 200
        data = res.json()
        # Should respond gracefully (not crash)
        assert data["response_text"]
