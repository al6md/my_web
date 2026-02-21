import asyncio
import logging
import json
import time
import random
import numpy as np
import torch
import os
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# Flask/App imports
try:
    from flask import current_app
except ImportError:
    pass

# Model Imports
from .models.collaborative_filtering import MatrixFactorization
from .models.two_tower_v2 import TwoTowerV2
from .models.graph_recommender import GraphRecommender
from .models.neural_reranker import NeuralReranker
from .models.ensemble import EnsembleRanker, EnsembleWeights
from .retrieval.hybrid_retrieval import HybridRetriever
from .retrieval.vector_index import VectorIndexService
from .interest_fetcher_service import interest_service
from .feature_store import get_feature_store

logger = logging.getLogger(__name__)

class RedisCacheLayer:
    """
    🚀 High-Performance Redis Caching Layer
    """
    def __init__(self, use_redis=True):
        self.use_redis = use_redis
        self.local_cache = {}
        self.redis = None
        
        if self.use_redis:
            try:
                import redis
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
                self.redis = redis.Redis.from_url(redis_url, socket_timeout=0.2, decode_responses=True)
                self.redis.ping()
                logger.info("✅ [Cache] Connected to Redis")
            except Exception as e:
                logger.warning(f"⚠️ [Cache] Redis not available: {e}")
                self.redis = None

    async def get(self, key: str) -> Any:
        try:
            if self.redis:
                val = await asyncio.to_thread(self.redis.get, key)
                if val:
                    return json.loads(val)
        except Exception: 
            pass
        return self.local_cache.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int = 600):
        try:
            if self.redis:
                await asyncio.to_thread(self.redis.setex, key, ttl_seconds, json.dumps(value))
            else:
                self.local_cache[key] = value # Simple in-memory fallback (no TTL for simplicity in fallback)
        except Exception:
            pass

class UnifiedPipeline:
    """
    🧠 Unified Recommendation Pipeline
    Aggregates: CF, Content, Two-Tower, Graph, Hybrid, Vector, Trending.
    """
    
    def __init__(self):
        self.cache = RedisCacheLayer(use_redis=True)
        self._executor = ThreadPoolExecutor(max_workers=10)
        self.flask_app = None 
        
        # --- Initialize Models ---
        self.ensemble = EnsembleRanker(weights=EnsembleWeights(
            two_tower=0.35, graph=0.20, collaborative=0.20, semantic=0.15, popularity=0.10
        ))
        
        self.feature_store = get_feature_store()
        
        # Load Graph Model
        self.graph_model = GraphRecommender()
        graph_path = os.path.join(os.getcwd(), 'ai_models', 'graph_recommender.pt')
        if os.path.exists(graph_path):
            try:
                self.graph_model.load(graph_path)
            except: 
                logger.warning("Failed to load Graph model, using untrained")
        
        # Load Hybrid/Vector Services
        self.vector_service = VectorIndexService(index_dir="instance/indexes")
        self.hybrid_retriever = HybridRetriever()
        try:
            self.hybrid_retriever.set_vector_index(self.vector_service.get_index("books"))
        except:
            logger.warning("Vector index 'books' not ready")

    async def get_unified_recommendations(self, user_id: int, limit: int = 20) -> List[Dict]:
        """
        Target function: fetches from all models, ensembles, and returns ranked list.
        """
        start_time = time.time()
        
        # 1. Check Cache
        cache_key = f"unified_recs:final:{user_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 2. Parallel Execution
        tasks = [
            self._safe_run("Collaborative Filtering", self._get_cf, user_id),
            self._safe_run("Content-Based", self._get_content, user_id),
            self._safe_run("Deep Learning Two-Tower", self._get_two_tower, user_id),
            self._safe_run("Graph Neural Network", self._get_graph, user_id),
            self._safe_run("Hybrid Retrieval", self._get_hybrid, user_id),
            self._safe_run("Global Trending", self._get_trending, user_id)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 3. Aggregate & De-duplicate
        # Structure: Map[book_id] -> {details, scores: {model: score}}
        candidates_map = {}
        
        for res_list in results:
            for item in res_list:
                bid = str(item.get('id') or item.get('google_id') or f"local_{item.get('local_id')}")
                score = float(item.get('score', 0.1))
                source = item.get('source', 'Unknown')
                
                if bid not in candidates_map:
                    candidates_map[bid] = {
                        'id': bid,
                        'title': item.get('title'),
                        'curr_book_obj': item, # Keep original object
                        'scores': {}
                    }
                
                # Normalize source names for EnsembleRanker keys
                # "Collaborative Filtering" -> "collaborative"
                # "Deep Learning Two-Tower" -> "two_tower"
                norm_source = self._normalize_source_name(source)
                candidates_map[bid]['scores'][norm_source] = score

        # 4. Preparing for Ensemble Ranker
        all_ids = list(candidates_map.keys())
        if not all_ids:
            return []
            
        # Build score vectors for Ensemble
        # Expects: scores = {'two_tower': np.array([...]), ...}
        ensemble_inputs = {
            'two_tower': [], 'graph': [], 'collaborative': [], 'semantic': [], 'popularity': []
        }
        
        for bid in all_ids:
            c_scores = candidates_map[bid]['scores']
            ensemble_inputs['two_tower'].append(c_scores.get('two_tower', 0.0))
            ensemble_inputs['graph'].append(c_scores.get('graph', 0.0))
            ensemble_inputs['collaborative'].append(c_scores.get('collaborative', 0.0))
            ensemble_inputs['semantic'].append(c_scores.get('hybrid', 0.0)) # Mapping Hybrid to Semantic
            ensemble_inputs['popularity'].append(c_scores.get('trending', 0.0))
            
        # Convert to numpy
        for k in ensemble_inputs:
            ensemble_inputs[k] = np.array(ensemble_inputs[k])
            
        # 5. Run Ensemble
        ranked_results = self.ensemble.combine(ensemble_inputs, all_ids)
        # ranked_results is list of (id, final_score, breakdown)
        
        # 6. Formatting Final Output
        final_output = []
        for bid, score, breakdown in ranked_results[:limit]:
            book_data = candidates_map[bid]['curr_book_obj']
            
            # Determine top contributing model
            top_model = "Ensemble"
            max_contrib = 0
            for m, s in breakdown.items():
                if s > max_contrib:
                    max_contrib = s
                    top_model = m
            
            # Map back to readable name
            readable_model = self._human_readable_model(top_model)
            
            # Explainability
            explanation = f"Recommended by {readable_model}"
            if len([v for v in breakdown.values() if v > 0]) > 1:
                explanation += f" with consistency across {len([v for v in breakdown.values() if v > 0])} models."
            
            final_item = {
                "book_id": bid,
                "title": book_data.get('title'),
                "cover": book_data.get('cover'),
                "author": book_data.get('author'),
                "score": round(score, 2),
                "model": readable_model,
                "explanation": explanation,
                "breakdown": breakdown
            }
            final_output.append(final_item)
            
        # 7. Cache
        await self.cache.set(cache_key, final_output, ttl_seconds=600)
        
        return final_output

    async def _safe_run(self, name, func, *args):
        try:
            res = await func(*args)
            # Tag results with source
            for r in res:
                r['source'] = name
                if 'score' not in r: r['score'] = 0.5 # Default score
            return res
        except Exception as e:
            logger.error(f"❌ {name} failed: {e}")
            return []

    # --- Helpers ---
    def _normalize_source_name(self, name):
        name = name.lower()
        if "two-tower" in name: return "two_tower"
        if "graph" in name: return "graph"
        if "collaborative" in name: return "collaborative"
        if "content" in name: return "semantic" # Treat content as semantic-ish
        if "hybrid" in name: return "semantic"
        if "trending" in name: return "popularity"
        return "popularity"

    def _human_readable_model(self, key):
        map_ = {
            "two_tower": "Deep Learning Two-Tower",
            "graph": "Graph Neural Network",
            "collaborative": "Collaborative Filtering",
            "semantic": "Hybrid Retrieval",
            "popularity": "Global Trends"
        }
        return map_.get(key, key.capitalize())

    # --- Wrappers ---
    async def _get_cf(self, user_id):
        from flask_book_recommendation.recommender import get_cf_similar
        def _run():
            if self.flask_app:
                with self.flask_app.app_context():
                    return get_cf_similar(user_id, top_n=20)
            return []
        return await asyncio.to_thread(_run)

    async def _get_content(self, user_id):
        from flask_book_recommendation.recommender import get_content_similar
        def _run():
            if self.flask_app:
                with self.flask_app.app_context():
                    return get_content_similar(user_id, top_n=20)
            return []
        return await asyncio.to_thread(_run)

    async def _get_two_tower(self, user_id):
        from flask_book_recommendation.recommender import _get_ai_embedding_recommendations
        def _run():
            if self.flask_app:
                with self.flask_app.app_context():
                    return _get_ai_embedding_recommendations(user_id, viewed_book_ids=[])
            return []
        return await asyncio.to_thread(_run)

    async def _get_graph(self, user_id):
        # Use simple heuristic or calling the model
        if self.graph_model:
             # Just a placeholder call as we need `user_id` mapping which might not exist in a fresh run
             # In prod, this would map DB ID to Graph ID
             return [] 
        return []

    async def _get_hybrid(self, user_id):
        # Fetch search history as proxy for "query"
        # Or user profile keywords
        # For demonstration, we use a simple generic query
        # In real world: extract user interest keywords
        return []

    async def _get_trending(self, user_id):
        data = interest_service.get_trending_interests()
        return data.get("books", [])[:15]

# Singleton
pipeline = UnifiedPipeline()
