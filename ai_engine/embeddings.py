from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingService:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        print(f"Loading Sentence Transformer: {model_name}...")
        self.model = SentenceTransformer(model_name)
        
    def encode(self, texts: list) -> np.ndarray:
        return self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    
    def encode_single(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

# Singleton instance
embedding_service = EmbeddingService()
