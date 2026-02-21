from typing import List, Dict, Any, Optional
import asyncio
from .base import BaseRecommender
from ..fetchers.google_books import GoogleBooksFetcher
from ..cache import cache_manager as cache

class RealtimeBookRecommender(BaseRecommender):
    """
    Recommender that fetches FRESH data from Internet APIs (Google Books, etc.)
    Specifically used for 'Trending' or 'New Releases' or 'Topics' not in our DB.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.fetcher = GoogleBooksFetcher()
        self.cache_ttl = 3600 # 1 hour cache
        
    async def generate_candidates(self, user_id: int, limit: int = 10, context: Dict = None) -> List[Dict[str, Any]]:
        """
        Generate candidates by querying external APIs based on user interests.
        """
        context = context or {}
        interests = context.get('interests', [])
        
        if not interests:
            # Fallback: General trending query
            queries = ["bestsellers 2024", "trending books"]
        else:
            # Use top 2 interests
            queries = interests[:2]
            
        candidates = []
        
        # Async fetch for each query
        tasks = []
        for q in queries:
            tasks.append(self._fetch_and_cache(q, limit))
            
        results = await asyncio.gather(*tasks)
        
        # Flatten
        seen = set()
        for res_list in results:
            for book in res_list:
                bid = book['book_id']
                if bid not in seen:
                    candidates.append({
                        "book_id": bid,
                        "score": 0.9, # High score for fresh content
                        "title": book['title'], # Store metadata directly as it might not be in DB
                        "image": book['thumbnail'],
                        "explanation": f"Trending in {book.get('categories', ['General'])[0]}"
                    })
                    seen.add(bid)
                    
        return candidates[:limit]

    async def _fetch_and_cache(self, query: str, limit: int) -> List[Dict]:
        """
        Helper to fetch with Redis Caching.
        """
        cache_key = f"ext_search:{query}:{limit}"
        
        # Check Cache
        cached = await cache.get(cache_key)
        if cached:
            return cached
            
        # Fetch Live
        books = await self.fetcher.search_books(query, limit)
        
        # Save Cache
        if books:
            await cache.set(cache_key, books, self.cache_ttl)
            
        return books
