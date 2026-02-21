from abc import ABC, abstractmethod
from typing import List, Dict, Any
import aiohttp
import urllib.parse

class BaseFetcher(ABC):
    """
    Abstract Base Class for all Internet Data Fetchers.
    Ensures consistent interface for fetching book data.
    """
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.headers = {"User-Agent": "UnifiedBookRecommender/1.0"}

    @abstractmethod
    async def search_books(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for books based on a query string.
        Returns normalized book objects.
        """
        pass

    def _normalize_book(self, raw_data: Dict) -> Dict[str, Any]:
        """
        Convert raw API response into our standard book format.
        """
        return raw_data
