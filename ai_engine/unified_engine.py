import asyncio
from typing import List, Dict, Any, Optional
import time
from .recommenders.base import BaseRecommender
from .diversity.mmr import MMRDiversifier
from .ranking.ranker import LearningToRankRanker
from .config.unified_config import get_config
import os
# from .recommenders.semantic import SemanticRecommender

class UnifiedEngine:
    """
    Central orchestration engine for the unified recommendation system.
    Manages multiple recommendation algorithms (BaseRecommender instances),
    handles parallel execution, results merging, and final ranking.
    """
    
    def __init__(self, recommenders: List[BaseRecommender], config: Dict[str, Any] = None):
        if not config:
            env_config = get_config(os.getenv('FLASK_ENV', 'development'))
            self.config = env_config.PERFORMANCE
            self.algo_weights = env_config.ALGORITHM_WEIGHTS
        else:
             self.config = config
             self.algo_weights = {}

        self.recommenders = recommenders
        
        # Hydrate weights from config if available, else default to 1.0
        self.weights = {}
        for rec in recommenders:
            # Map class names to config keys (heuristic)
            # e.g. CollaborativeRecommender -> collaborative_filtering
            # For now, we manually map or use defaults
            self.weights[rec.name] = 1.0 

        self.diversifier = MMRDiversifier(lambda_param=0.7)
        self.ranker = LearningToRankRanker() 

    async def get_recommendations(self, user_id: int, limit: int = 10, context: Dict = None) -> Dict[str, Any]:
        """
        Get unified recommendations from all active algorithms.
        """
        start_time = time.time()
        
        # 1. Parallel Generation
        tasks = [
            rec.generate_with_metrics(user_id, limit, context)
            for rec in self.recommenders
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 2. Merge Results
        candidates_raw = self._merge_results(results, limit=limit*5) # Fetch much more for LTR & Diversity
        
        # 2.5 Re-Rank (LTR)
        # We need user features if we want LTR to work, passed in context or fetched
        user_features = context.get('user_features', {})
        candidates_ranked = self.ranker.rank(candidates_raw, user_features)
        
        # 3. Final Step (Diversity via MMR)
        candidates = self.diversifier.diversify(candidates_ranked, limit)
        
        duration = (time.time() - start_time) * 1000
        
        return {
            "user_id": user_id,
            "recommendations": candidates,
            "meta": {
                "total_duration_ms": round(duration, 2),
                "sources": [r['source'] for r in results if r['status'] == 'success']
            }
        }

    def _merge_results(self, results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """
        Merge implementation: Simple weighted stacking + deduplication.
        """
        merged_candidates = {} # book_id -> {score, count, explanations}
        
        for result in results:
            if result['status'] != 'success':
                continue
                
            source_weight = self.weights.get(result['source'], 1.0)
            
            for item in result['candidates']:
                book_id = item['book_id']
                score = item['score'] * source_weight
                
                if book_id in merged_candidates:
                    merged_candidates[book_id]['score'] += score
                    merged_candidates[book_id]['count'] += 1
                    merged_candidates[book_id]['sources'].append(result['source'])
                else:
                    merged_candidates[book_id] = {
                        'book_id': book_id,
                        'score': score,
                        'count': 1,
                        'sources': [result['source']],
                        'explanation': item.get('explanation', '')
                    }
        
        # Convert to list and sort by score
        final_list = list(merged_candidates.values())
        final_list.sort(key=lambda x: x['score'], reverse=True)
        
        return final_list[:limit]

    def add_recommender(self, recommender: BaseRecommender, weight: float = 1.0):
        self.recommenders.append(recommender)
        self.weights[recommender.name] = weight
