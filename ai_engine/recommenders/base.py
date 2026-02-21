from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time
import asyncio

class BaseRecommender(ABC):
    """
    Abstract Base Class for all recommendation algorithms within the Unified System.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = self.__class__.__name__
        self.type = self.config.get('type', 'candidate_generator') # candidate_generator, ranker, diversifier

    @abstractmethod
    async def generate_candidates(self, user_id: int, limit: int = 10, context: Dict = None) -> List[Dict[str, Any]]:
        """
        Generate a list of candidate items.
        
        Args:
            user_id: The ID of the user to generate recommendations for.
            limit: The maximum number of candidates to return.
            context: Additional context like history, interests, location, etc.
            
        Returns:
            List of dictionaries, each containing at least 'book_id' and 'score'.
            Example: [{'book_id': 123, 'score': 0.85, 'explanation': 'Because you liked X'}]
        """
        pass

    async def generate_with_metrics(self, user_id: int, limit: int = 10, context: Dict = None) -> Dict[str, Any]:
        """
        Wrapper around generate_candidates that captures execution metrics.
        """
        start_time = time.time()
        try:
            # Run the generation
            candidates = await self.generate_candidates(user_id, limit, context)
            
            # Enrich candidates with source info if not present
            for c in candidates:
                if 'source' not in c:
                    c['source'] = self.name
                    
            duration_ms = (time.time() - start_time) * 1000
            
            return {
                "source": self.name,
                "candidates": candidates,
                "duration_ms": round(duration_ms, 2),
                "status": "success",
                "count": len(candidates)
            }
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            # Log error (in a real system, use a logger)
            print(f"Error in {self.name}: {str(e)}")
            return {
                "source": self.name,
                "candidates": [],
                "duration_ms": round(duration_ms, 2),
                "status": "error",
                "error": str(e)
            }

    def get_name(self) -> str:
        return self.name

    def get_type(self) -> str:
        return self.type
