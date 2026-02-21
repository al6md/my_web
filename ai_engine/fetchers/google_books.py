import aiohttp
from typing import List, Dict, Any
from .base import BaseFetcher
import os

class GoogleBooksFetcher(BaseFetcher):
    """
    Real-time data fetcher for Google Books API (V1).
    """
    BASE_URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self):
        super().__init__("google_books")
        self.api_key = os.getenv("GOOGLE_BOOKS_API_KEY", "")

    async def search_books(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Async search implementation.
        """
        params = {
            "q": query,
            "maxResults": limit,
            "printType": "books",
            "key": self.api_key
        }
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                # 1. Fetch
                async with session.get(self.BASE_URL, params=params, timeout=5) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                
                # 2. Normalize
                if "items" not in data:
                    return []
                
                return [self._normalize_book(item) for item in data['items']]
            except Exception as e:
                print(f"Error fetching from Google Books: {e}")
                return []

    def _normalize_book(self, raw_data: Dict) -> Dict[str, Any]:
        """
        Convert Google specific JSON to our unified format.
        """
        vol = raw_data.get('volumeInfo', {})
        
        image = vol.get('imageLinks', {}).get('thumbnail', '')
        if image:
            image = image.replace("http://", "https://")
            
        return {
            "book_id": raw_data.get('id', 'unknown'),
            "title": vol.get('title', 'Unknown Title'),
            "authors": vol.get('authors', ['Unknown Author']),
            "description": vol.get('description', ''),
            "thumbnail": image,
            "categories": vol.get('categories', []),
            "published_date": vol.get('publishedDate', ''),
            "source": self.source_name,
            "average_rating": vol.get('averageRating', 0),
            "ratings_count": vol.get('ratingsCount', 0),
            "preview_link": vol.get('previewLink', '')
        }
