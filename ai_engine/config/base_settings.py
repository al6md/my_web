import os
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "SuperIntelligentBookRec"
    VERSION: str = "1.0.0"
    
    # Model Hyperparameters
    EMBEDDING_DIM: int = 384  # For all-MiniLM-L6-v2
    HIDDEN_DIM: int = 256
    OUTPUT_DIM: int = 384 # Match raw embedding size for compatibility
    MAX_SEQ_LEN: int = 20
    
    # Paths
    MODEL_PATH: str = "models/two_tower_v1.pt"
    INDEX_PATH: str = "models/faiss_index.bin"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    
    # Redis Cache (Required for < 200ms)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL: int = 3600 # 1 hour default

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
