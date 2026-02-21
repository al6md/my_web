from typing import List, Dict, Any, Optional
import numpy as np
import asyncio
from .base import BaseRecommender
from ..retrieval import RetrievalEngine
from ..embeddings import embedding_service

class SemanticRecommender(BaseRecommender):
    """
    Recommender based on Semantic Similarity (Embeddings + FAISS).
    Uses the existing RetrievalEngine from ai_engine/retrieval.py.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.retriever = RetrievalEngine() # Initializes FAISS index
        self.limit = config.get('limit', 10)

    async def generate_candidates(self, user_id: int, limit: int = 10, context: Dict = None) -> List[Dict[str, Any]]:
        """
        Generates candidates using semantic similarity of user interests/history.
        """
        context = context or {}
        history = context.get('history', [])
        interests = context.get('interests', [])
        
        # 1. Generate Query Vector (this is CPU bound, run in executor if heavy)
        loop = asyncio.get_running_loop()
        query_vec = await loop.run_in_executor(None, self._generate_query_vector, history, interests)
        
        # 2. Search Index (FAISS is CPU bound)
        # Using executor to prevent blocking the event loop
        results = await loop.run_in_executor(None, self.retriever.search, query_vec, limit)
        
        # 3. Format Results
        candidates = []
        for book_id, score in results:
            candidates.append({
                'book_id': book_id,
                'score': float(score),
                'explanation': f"Matched your interests (Score: {score:.2f})"
            })
            
        return candidates

    def _generate_query_vector(self, history: List[str], interests: List[str]) -> np.ndarray:
        """
        Helper to construct the query vector from user data.
        """
        # Encode Interests
        if not interests:
            int_vec = np.zeros(384) # Default/Zero
        else:
            int_emb = embedding_service.encode(interests)
            int_vec = np.mean(int_emb, axis=0)
            
        # Encode History (if available)
        hist_vec = None
        if history:
            hist_emb = embedding_service.encode(history[-5:]) # Last 5 books
            hist_vec = np.mean(hist_emb, axis=0)
            
        # Combine (Simple Average or Weighted)
        if hist_vec is not None:
             final_vec = (int_vec + hist_vec) / 2.0
        else:
             final_vec = int_vec
             
        return final_vec
