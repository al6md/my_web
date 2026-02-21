import pytest
import asyncio
from httpx import AsyncClient
from ..main import app
from ..unified_engine import UnifiedEngine
from ..recommenders.base import BaseRecommender

class MockRecommender(BaseRecommender):
    async def generate_candidates(self, user_id, limit, context=None):
        return [{"book_id": "1", "title": "Test Book", "score": 0.9}]

@pytest.mark.asyncio
async def test_unified_engine_merge():
    rec = MockRecommender()
    engine = UnifiedEngine(recommenders=[rec])
    
    result = await engine.get_recommendations(user_id=1, limit=5)
    assert len(result['recommendations']) > 0
    assert result['recommendations'][0]['book_id'] == "1"
    assert result['meta']['response_time_ms'] > 0

@pytest.mark.asyncio
async def test_api_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "AI Recommendation Engine"}
