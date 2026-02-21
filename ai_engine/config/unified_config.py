class UnifiedRecommenderConfig:
    """Configuration for the unified recommendation system"""
    
    # ==================== PERFORMANCE SETTINGS ====================
    PERFORMANCE = {
        # Cache settings
        'cache_ttl_seconds': 300,  # 5 minutes
        'feature_cache_ttl': 3600,  # 1 hour
        'embedding_cache_ttl': 86400,  # 24 hours
        
        # Parallel processing
        'max_parallel_workers': 8,
        'algorithm_timeout_seconds': 2.0,
        'internet_fetch_timeout': 3.0,
        
        # Candidate generation
        'candidate_multiplier': 3,  # Generate 3x for ranking
        'min_candidates_per_algo': 10,
        'max_candidates_total': 300,
        
        # Database
        'db_pool_size': 20,
        'db_max_overflow': 10,
        'query_timeout': 5.0
    }
    
    # ==================== ALGORITHM WEIGHTS ====================
    ALGORITHM_WEIGHTS = {
        # Primary algorithms (total = 1.0)
        'collaborative_filtering': 0.25,
        'content_based': 0.20,
        'embedding_based': 0.20,
        'deep_learning': 0.15,
        'behavior_sequence': 0.10,
        
        # Secondary algorithms
        'context_aware': 0.05,
        'trend_based': 0.03,
        'social_based': 0.02,
        
        # Special algorithms (applied conditionally)
        'internet_sources': 0.15,  # When fetch_from_internet=True
        'mood_based': 0.10,  # When mood is specified
    }

class DevelopmentConfig(UnifiedRecommenderConfig):
    """Development environment configuration"""
    # Override settings for dev
    UnifiedRecommenderConfig.PERFORMANCE['cache_ttl_seconds'] = 60

class ProductionConfig(UnifiedRecommenderConfig):
    """Production environment configuration"""
    UnifiedRecommenderConfig.PERFORMANCE['max_parallel_workers'] = 16

def get_config(environment='development'):
    configs = {
        'development': DevelopmentConfig,
        'production': ProductionConfig
    }
    return configs.get(environment, DevelopmentConfig)
