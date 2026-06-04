"""Tests for the RAG retrieval engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agent.rag import retrieve
from db.database import init_db
from db.seed import seed


@pytest.fixture(scope="module", autouse=True)
def setup_db_and_index():
    """Ensure DB is seeded before RAG tests."""
    init_db()
    seed()


class TestRAGRetrieval:
    def test_retrieves_results(self):
        results = retrieve("running shoes")
        assert len(results) > 0

    def test_returns_at_most_top_n(self):
        results = retrieve("electronics gadgets", top_n=3)
        assert len(results) <= 3

    def test_grocery_query_returns_groceries(self):
        results = retrieve("fresh vegetables and groceries")
        categories = [r.get("category_name", "").lower() for r in results]
        assert any("grocer" in c for c in categories)

    def test_electronics_query(self):
        results = retrieve("wireless earbuds")
        assert len(results) > 0

    def test_ice_cream_query(self):
        results = retrieve("delicious ice cream")
        names = [r["name"].lower() for r in results]
        assert any("ice cream" in n for n in names)

    def test_results_have_required_fields(self):
        results = retrieve("laptop bag backpack")
        for r in results:
            assert "id" in r
            assert "name" in r
            assert "price" in r
            assert "rating" in r

    def test_scores_are_sorted_descending(self):
        results = retrieve("formal leather shoes", top_n=5)
        scores = [r.get("_semantic_score", 0) for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_like_query_still_returns(self):
        # Should not raise; may return generic results
        results = retrieve("something")
        assert isinstance(results, list)
