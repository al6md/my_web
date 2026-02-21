from datetime import datetime
import numpy as np
import logging
from typing import Dict, Any

# Adjust imports to match your project structure
# In your main app, 'flask_book_recommendation.models' is likely where models reside.
# But 'ai_engine' is outside 'flask_book_recommendation'.
# We need to import models carefully or assume the app context handles it.
# For now, we assume this code runs inside the unified server context where these models are available.

try:
    from flask_book_recommendation.models import User, UserRatingCF, UserBookView, UserGenre, Genre
    from flask_book_recommendation.extensions import db
    MODELS_AVAILABLE = True
except ImportError:
    # Fallback/Mock for standalone AI Engine testing without full Flask app
    MODELS_AVAILABLE = False
    print("Warning: Database models not found. Feature Store will use mock data.")

from ..cache.manager import cache_manager

logger = logging.getLogger(__name__)

class FeatureStore:
    """
    Central Feature Store for high-performance retrieval of user and item features.
    Serves as the single source of truth for the 'UnifiedRecommender' to access pre-computed data.
    """
    
    def __init__(self):
        self.cache = cache_manager
        self.feature_ttl = 3600 # 1 hour
        
    async def get_user_features(self, user_id: int) -> Dict[str, Any]:
        """
        Get user profile features from Redis or compute if missing.
        """
        key = f"features:user:{user_id}"
        
        # 1. Try Cache
        cached = await self.cache.get(key)
        if cached:
            return cached
            
        # 2. Compute
        features = await self._compute_user_features(user_id)
        
        # 3. Store in Cache (1 hour)
        await self.cache.set(key, features, ttl=self.feature_ttl)
        
        return features

    async def get_item_features(self, book_id: str) -> Dict[str, Any]:
        """
        Get book features (metadata, embeddings, stats).
        """
        key = f"features:book:{book_id}"
        cached = await self.cache.get(key)
        if cached:
            return cached
            
        # Compute/Fetch
        features = await self._compute_item_features(book_id)
        await self.cache.set(key, features, ttl=86400) # 24 hours
        return features

    async def _compute_user_features(self, user_id: int) -> Dict[str, Any]:
        if not MODELS_AVAILABLE:
            return self._mock_user_features(user_id)

        # We need to run synchronous DB queries in a thread-safe way if we are inside async loop
        # But SQL Alchemy objects are bound to thread.
        # Ideally, we should use a sync wrapper or run_in_executor.
        # For this prototype, assuming read-only access is safe enough or we are in a context that allows it.
        # However, calling DB from async function directly blocks the loop.
        # We will wrap it in asyncio.to_thread (New in 3.9) or loop.run_in_executor
        
        import asyncio
        loop = asyncio.get_running_loop()
        
        return await loop.run_in_executor(None, self._sync_compute_user_features, user_id)

    def _sync_compute_user_features(self, user_id: int) -> Dict[str, Any]:
        try:
            user = User.query.get(user_id)
            if not user:
                return {}
                
            ratings = UserRatingCF.query.filter_by(user_id=user_id).all()
            views = UserBookView.query.filter_by(user_id=user_id).order_by(UserBookView.last_viewed_at.desc()).limit(50).all()
            
            # Genres join
            # genres = db.session.query(UserGenre, Genre).join(Genre).filter(UserGenre.user_id == user_id).all()
            # Simplified for now if relations exist:
            # favorite_genres = [g.name for g in user.genres] # if relationship exists
            
            # Manual query for genres
            user_genres = UserGenre.query.filter_by(user_id=user_id).all()
            favorite_genres = []
            if user_genres:
                genre_ids = [ug.genre_id for ug in user_genres]
                genres = Genre.query.filter(Genre.id.in_(genre_ids)).all()
                favorite_genres = [g.name for g in genres]
            
            # Statistics
            rating_values = [r.rating for r in ratings]
            avg_rating = sum(rating_values) / len(rating_values) if rating_values else 0.0
            rating_std = np.std(rating_values) if len(rating_values) > 1 else 0.0
            
            # Recency
            last_active = datetime.min
            if ratings:
                last_active = max(last_active, max(r.created_at for r in ratings))
            if views:
                last_active = max(last_active, max(v.last_viewed_at for v in views))
                
            days_since_active = (datetime.utcnow() - last_active).days if last_active != datetime.min else 999
            
            features = {
                "user_id": user_id,
                "created_at_ts": user.created_at.timestamp() if user.created_at else 0,
                "num_ratings": len(ratings),
                "avg_rating": float(avg_rating),
                "rating_std": float(rating_std),
                "num_views": len(views),
                "recent_view_count": len([v for v in views if (datetime.utcnow() - v.last_viewed_at).days <= 7]),
                "favorite_genres": favorite_genres,
                "days_since_active": days_since_active,
                "activity_level": self._calculate_activity_level(len(ratings), len(views))
            }
            return features
        except Exception as e:
            logger.error(f"Error computing features for user {user_id}: {e}")
            return {}

    def _calculate_activity_level(self, n_ratings, n_views) -> str:
        total = n_ratings + n_views
        if total < 5: return 'low'
        if total < 20: return 'medium'
        return 'high'

    async def _compute_item_features(self, book_id: str) -> Dict[str, Any]:
        # Placeholder for item feature computation
        return {
            "book_id": book_id,
            "popularity": 0.5, # Default
            "freshness": 0.5
        }

    def _mock_user_features(self, user_id: int) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "avg_rating": 4.5,
            "favorite_genres": ["Science Fiction", "Technology"],
            "activity_level": "high",
            "account_age_days": 120,
            "last_active": "2024-05-20"
        }

feature_store = FeatureStore()
