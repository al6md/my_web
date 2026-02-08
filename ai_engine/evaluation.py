import numpy as np

def precision_at_k(recommended_ids, relevant_ids, k=10):
    recommended_ids = recommended_ids[:k]
    if not recommended_ids:
        return 0.0
    relevant_set = set(relevant_ids)
    hits = sum(1 for bid in recommended_ids if bid in relevant_set)
    return hits / k

def dcg_at_k(r, k, method=0):
    r = np.asfarray(r)[:k]
    if r.size:
        if method == 0:
            return r[0] + np.sum(r[1:] / np.log2(np.arange(2, r.size + 1)))
        elif method == 1:
            return np.sum(r / np.log2(np.arange(2, r.size + 2)))
        raise ValueError('method must be 0 or 1.')
    return 0.

def ndcg_at_k(r, k, method=0):
    dcg_max = dcg_at_k(sorted(r, reverse=True), k, method)
    if not dcg_max:
        return 0.
    return dcg_at_k(r, k, method) / dcg_max

class EvaluationFramework:
    def __init__(self):
        self.metrics = {}
        
    def evaluate_request(self, user_id, recommendations, true_interactions):
        """
        recommendations: list of book_ids
        true_interactions: list of book_ids relevant to user (held out)
        """
        prec = precision_at_k(recommendations, true_interactions)
        
        # Relevance relevance vector (binary) for NDCG
        relevance = [1 if bid in true_interactions else 0 for bid in recommendations]
        ndcg = ndcg_at_k(relevance, k=len(recommendations))
        
        return {"precision": prec, "ndcg": ndcg}

class ABTestSimulator:
    def __init__(self):
        self.groups = {"A": "Semantic", "B": "Neural"}
        
    def assign_bucket(self, user_id):
        return "A" if user_id % 2 == 0 else "B"
