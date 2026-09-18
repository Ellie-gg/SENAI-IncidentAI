from __future__ import annotations

import pytest

from app.models.llm_io import AnalysisOut, RecommendationOut
from app.services.llm import MockLLMClient, default_actions_for_category, structured_with_fallback


async def test_mock_llm_classifies_database_connectivity():
    client = MockLLMClient()
    result = await client.structured(
        AnalysisOut, "ERROR connection pool exhausted, database timeout"
    )
    assert result.category == "database_connectivity"
    assert result.confidence > 0.5


async def test_mock_llm_returns_unknown_for_unmatched_text():
    client = MockLLMClient()
    result = await client.structured(AnalysisOut, "Something strange happened, unclear cause")
    assert result.category == "unknown"
    assert result.confidence < 0.5


async def test_mock_llm_recommendation_returns_category_actions():
    client = MockLLMClient()
    result = await client.structured(RecommendationOut, "category: memory_pressure heap oom")
    assert len(result.recommended_actions) >= 1


async def test_structured_with_fallback_success_not_degraded():
    client = MockLLMClient()
    result, degraded = await structured_with_fallback(client, AnalysisOut, "database timeout")
    assert degraded is False
    assert isinstance(result, AnalysisOut)


async def test_structured_with_fallback_mock_fail_degrades_cleanly():
    client = MockLLMClient(always_fail=True)
    result, degraded = await structured_with_fallback(client, AnalysisOut, "database timeout")
    assert degraded is True
    assert result is None


def test_default_actions_for_category_has_fallback_for_unknown():
    actions = default_actions_for_category("this-category-does-not-exist")
    assert len(actions) >= 1


@pytest.mark.parametrize("category", ["database_connectivity", "memory_pressure", "unknown"])
def test_default_actions_for_category_known_categories(category):
    actions = default_actions_for_category(category)
    assert len(actions) >= 3
