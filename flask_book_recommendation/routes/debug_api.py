# flask_book_recommendation/routes/debug_api.py
"""
🔍 Debug API for Recommendation System Verification
====================================================
Provides detailed insights into the recommendation pipeline for debugging
and verification purposes.
"""

import time
from flask import Blueprint, jsonify, request
from flask_login import current_user
from ..extensions import db

debug_bp = Blueprint("debug", __name__, url_prefix="/api/recommend")


@debug_bp.get("/debug")
def recommendation_debug():
    """
    🔬 Debug endpoint showing detailed recommendation pipeline execution.
    
    Returns separate results from each algorithm stage with timing and metadata.
    """
    user_id = request.args.get("user_id", type=int)
    if not user_id and current_user.is_authenticated:
        user_id = current_user.id
    
    if not user_id:
        return jsonify({
            "error": "user_id required",
            "usage": "/api/recommend/debug?user_id=42"
        }), 400
    
    results = {
        "user_id": user_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": {},
        "hybrid_merge": {},
        "final_results": [],
        "execution_summary": {}
    }
    
    total_start = time.perf_counter()
    
    # ========== Stage 1: Transformer Embeddings ==========
    try:
        from ..recommender import get_content_similar
        stage_start = time.perf_counter()
        transformer_results = get_content_similar(user_id, top_n=10)
        stage_time = (time.perf_counter() - stage_start) * 1000
        
        results["stages"]["transformer"] = {
            "invoked": True,
            "time_ms": round(stage_time, 2),
            "result_count": len(transformer_results),
            "results": transformer_results[:5],  # Top 5 for brevity
            "status": "SUCCESS" if transformer_results else "EMPTY"
        }
    except Exception as e:
        results["stages"]["transformer"] = {
            "invoked": False,
            "error": str(e),
            "status": "ERROR"
        }
    
    # ========== Stage 2: Neural Model (Two-Tower) ==========
    try:
        from ..recommender import get_deep_learning_recommendations
        stage_start = time.perf_counter()
        neural_results = get_deep_learning_recommendations(user_id, limit=10)
        stage_time = (time.perf_counter() - stage_start) * 1000
        
        results["stages"]["neural"] = {
            "invoked": True,
            "time_ms": round(stage_time, 2),
            "result_count": len(neural_results),
            "results": neural_results[:5],
            "status": "SUCCESS" if neural_results else "EMPTY"
        }
    except Exception as e:
        results["stages"]["neural"] = {
            "invoked": False,
            "error": str(e),
            "status": "ERROR"
        }
    
    # ========== Stage 3: Behavioral Learning ==========
    try:
        from ..recommender import get_behavior_based_recommendations
        stage_start = time.perf_counter()
        behavioral_results = get_behavior_based_recommendations(user_id, limit=10)
        stage_time = (time.perf_counter() - stage_start) * 1000
        
        results["stages"]["behavioral"] = {
            "invoked": True,
            "time_ms": round(stage_time, 2),
            "result_count": len(behavioral_results),
            "results": behavioral_results[:5],
            "status": "SUCCESS" if behavioral_results else "EMPTY"
        }
    except Exception as e:
        results["stages"]["behavioral"] = {
            "invoked": False,
            "error": str(e),
            "status": "ERROR"
        }
    
    # ========== Stage 4: Collaborative Filtering ==========
    try:
        from ..recommender import get_cf_similar
        stage_start = time.perf_counter()
        cf_results = get_cf_similar(user_id, top_n=10)
        stage_time = (time.perf_counter() - stage_start) * 1000
        
        results["stages"]["collaborative_filtering"] = {
            "invoked": True,
            "time_ms": round(stage_time, 2),
            "result_count": len(cf_results),
            "results": cf_results[:5],
            "status": "SUCCESS" if cf_results else "EMPTY"
        }
    except Exception as e:
        results["stages"]["collaborative_filtering"] = {
            "invoked": False,
            "error": str(e),
            "status": "ERROR"
        }
    
    # ========== Hybrid Merge Simulation ==========
    weights = {
        "transformer": 0.25,
        "neural": 0.35,
        "behavioral": 0.25,
        "collaborative_filtering": 0.15
    }
    
    # Collect all results with weighted scores
    all_books = {}
    for stage_name, weight in weights.items():
        stage_data = results["stages"].get(stage_name, {})
        stage_results = stage_data.get("results", [])
        for idx, book in enumerate(stage_results):
            book_id = book.get("id")
            if not book_id:
                continue
            
            position_score = 1.0 - (idx * 0.1)  # Higher rank = higher score
            weighted_score = position_score * weight
            
            if book_id not in all_books:
                all_books[book_id] = {
                    "book": book,
                    "total_score": 0,
                    "sources": []
                }
            
            all_books[book_id]["total_score"] += weighted_score
            all_books[book_id]["sources"].append({
                "algorithm": stage_name,
                "rank": idx + 1,
                "weighted_contribution": round(weighted_score, 3)
            })
    
    # Sort by total score
    sorted_books = sorted(all_books.values(), key=lambda x: x["total_score"], reverse=True)
    
    results["hybrid_merge"] = {
        "weights_used": weights,
        "merge_strategy": "Weighted Rank Fusion",
        "books_before_merge": len(all_books),
        "merged_rankings": [
            {
                "rank": idx + 1,
                "book_id": item["book"].get("id"),
                "title": item["book"].get("title"),
                "total_score": round(item["total_score"], 3),
                "contributing_algorithms": item["sources"]
            }
            for idx, item in enumerate(sorted_books[:10])
        ]
    }
    
    results["final_results"] = [item["book"] for item in sorted_books[:10]]
    
    # ========== Execution Summary ==========
    total_time = (time.perf_counter() - total_start) * 1000
    
    stage_times = {
        name: data.get("time_ms", 0)
        for name, data in results["stages"].items()
    }
    
    results["execution_summary"] = {
        "total_time_ms": round(total_time, 2),
        "stage_times_ms": stage_times,
        "algorithms_active": sum(1 for s in results["stages"].values() if s.get("invoked")),
        "algorithms_with_results": sum(1 for s in results["stages"].values() if s.get("result_count", 0) > 0),
        "fallback_used": all(s.get("result_count", 0) == 0 for s in results["stages"].values()),
        "verification_status": "PASS" if any(s.get("result_count", 0) > 0 for s in results["stages"].values()) else "FAIL"
    }
    
    return jsonify(results)




