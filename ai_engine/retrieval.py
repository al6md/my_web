import faiss
import numpy as np
import pickle
import os
from .config import settings

class RetrievalEngine:
    def __init__(self, index_path=settings.INDEX_PATH, dim=settings.OUTPUT_DIM):
        self.index_path = index_path
        self.dim = dim
        self.index = None
        self.book_ids = [] # Mapping Index -> DB ID function
        self._load_index()

    def _load_index(self):
        if os.path.exists(self.index_path):
            print(f"Loading FAISS index from {self.index_path}")
            self.index = faiss.read_index(self.index_path)
            # Load metadata (book_ids)
            meta_path = self.index_path.replace(".bin", "_meta.pkl")
            if os.path.exists(meta_path):
                with open(meta_path, 'rb') as f:
                    self.book_ids = pickle.load(f)
        else:
            print("No existing index found. Initializing new IndexFlatIP (Inner Product).")
            self.index = faiss.IndexFlatIP(self.dim) # Inner Product = Cosine if normalized

    def build_index(self, embeddings: np.ndarray, ids: list):
        """
        embeddings: (N, dim) float32 numpy array, normalized
        ids: list of book_ids corresponding to rows
        """
        if embeddings.shape[1] != self.dim:
            raise ValueError(f"Embedding dim {embeddings.shape[1]} != Index dim {self.dim}")
            
        self.index.reset()
        self.index.add(embeddings)
        self.book_ids = ids
        
        # Save
        faiss.write_index(self.index, self.index_path)
        with open(self.index_path.replace(".bin", "_meta.pkl"), 'wb') as f:
            pickle.dump(self.book_ids, f)
            
        return len(ids)

    def search(self, query_vector: np.ndarray, k: int = 10):
        """
        query_vector: (1, dim) or (Batch, dim)
        Returns: list of (book_id, score)
        """
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
            
        distances, indices = self.index.search(query_vector, k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.book_ids):
                results.append((self.book_ids[idx], float(distances[0][i])))
                
        return results
