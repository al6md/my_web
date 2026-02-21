from typing import List, Dict, Any, Optional
import math

class MMRDiversifier:
    """
    Maximal Marginal Relevance (MMR) implementation for diversity optimization.
    Balances Relevance (Score) vs Diversity (Novelty/Difference).
    """
    
    def __init__(self, lambda_param: float = 0.7):
        self.lambda_param = lambda_param

    def diversify(self, candidates: List[Dict[str, Any]], limit: int, similarity_matrix: Dict = None) -> List[Dict[str, Any]]:
        """
        Re-ranks a list of candidates to maximize diversity.
        
        Args:
            candidates: List of books with 'score' and 'book_id'.
            limit: Number of items to return.
            similarity_matrix: Optional precomputed similarity between items. 
                               If None, uses simple heuristic (e.g. author/genre check).
        """
        if not candidates:
            return []
            
        # If very few candidates, just return them sorted
        if len(candidates) <= limit:
            return sorted(candidates, key=lambda x: x['score'], reverse=True)

        # Selected items
        selected = []
        remaining = sorted(candidates, key=lambda x: x['score'], reverse=True)
        
        # 1. Pick the best item first
        selected.append(remaining.pop(0))
        
        while len(selected) < limit and remaining:
            best_mmr = -float('inf')
            best_item_idx = -1
            
            for idx, item in enumerate(remaining):
                # Relevance part
                relevance = item['score']
                
                # Diversity part (Max similarity to any already selected item)
                max_sim = 0.0
                for selected_item in selected:
                    sim = self._calculate_similarity(item, selected_item, similarity_matrix)
                    if sim > max_sim:
                        max_sim = sim
                
                # MMR Formula: Lambda * Rel - (1-Lambda) * MaxSim
                mmr_score = (self.lambda_param * relevance) - ((1 - self.lambda_param) * max_sim)
                
                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_item_idx = idx
            
            # Select best candidate
            if best_item_idx != -1:
                selected.append(remaining.pop(best_item_idx))
            else:
                break
                
        return selected

    def _calculate_similarity(self, item1: Dict, item2: Dict, matrix: Dict = None) -> float:
        """
        Heuristic similarity if no matrix provided.
        Returns 0.0 to 1.0
        """
        # If we have a matrix, use it
        if matrix:
            # key = f"{item1['book_id']}:{item2['book_id']}"
            # return matrix.get(key, 0.0)
            pass
            
        # Heuristic: Same Author?
        # Note: We need normalized data. Let's assume 'authors' is a list or string.
        a1 = item1.get('authors', [])
        a2 = item2.get('authors', [])
        
        # If exact match of primary author
        if a1 and a2 and a1 == a2:
             return 0.8
             
        # Same Category/Genre?
        c1 = item1.get('categories', [])
        c2 = item2.get('categories', [])
        if c1 and c2:
            # Intersection
            overlap = set(c1) & set(c2)
            if overlap:
                return 0.3
                
        return 0.0
