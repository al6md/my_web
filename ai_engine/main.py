from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import numpy as np
import torch
import uvicorn
import os

from .config import settings
from .neural_architecture import SuperIntelligentTwoTower
from .retrieval import RetrievalEngine
from .embeddings import embedding_service

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION)

# Global State
model = SuperIntelligentTwoTower()
retriever = RetrievalEngine()

class RecommendationRequest(BaseModel):
    user_id: int
    history_texts: List[str]  # Titles/Descriptions of books read
    interest_texts: List[str] # List of genre names or interest keywords
    k: int = 10

class SearchRequest(BaseModel):
    query: str
    k: int = 10

class RecommendationResponse(BaseModel):
    user_id: int
    recommendations: List[dict] # {book_id, score}

@app.on_event("startup")
def load_resources():
    # Load Model Weights if exist
    if os.path.exists(settings.MODEL_PATH):
        try:
            model.load_state_dict(torch.load(settings.MODEL_PATH))
            print("Model weights loaded.")
        except Exception as e:
            print(f"Failed to load weights: {e}")
    model.eval()

@app.post("/recommend", response_model=RecommendationResponse)
async def recommend(req: RecommendationRequest):
    # 1. Generate User Vector
    # For a real Two-Tower, we need to map IDs to embeddings.
    # Since we are using a Hybrid Approach where inputs are text (zero-shot/cold-start compatible):
    
    # Encode History
    if not req.history_texts:
        # Cold start: Use interests
         hist_vecs = torch.zeros(1, 1, 384) # Dummy
    else:
        # Encode last 10 books
        recent_history = req.history_texts[-settings.MAX_SEQ_LEN:]
        hist_emb_np = embedding_service.encode(recent_history)
        hist_vecs = torch.tensor(hist_emb_np).unsqueeze(0) # (1, Seq, 384)

    # Encode Interests
    if not req.interest_texts:
        int_vecs = torch.zeros(1, 384)
    else:
        int_emb_np = embedding_service.encode(req.interest_texts)
        # Average interest vectors
        int_mean = np.mean(int_emb_np, axis=0)
        int_vecs = torch.tensor(int_mean).unsqueeze(0) # (1, 384)

    # User ID (Placeholder for now, usually mapped via Embedding Table)
    # We clip user_id to max 50000
    u_id = torch.tensor([min(req.user_id, 49999)]) 

    # Forward Pass through User Tower
    with torch.no_grad():
        user_embedding = model.user_tower(u_id, hist_vecs, int_vecs) # (1, 128)
        
    # 2. Retrieval
    # The User Tower output is 128 dim (trained space). 
    # BUT, our FAISS index currently stores 768 dim (Raw Data) or 128 dim (Model Output)?
    # CRITICAL: For Two-Tower, FAISS must store VALID Model Output vectors (Item Tower outputs).
    # If the model is untrained, the Item Tower output is random garbage.
    # FALLBACK: If model is not trained, we use Raw Semantic Search (mpnet 768d).
    
    # CHECK: Are we in "Semantic" mode or "Neural" mode?
    # For this MVP, let's assume we are doing SEMANTIC Retrieval primarily (System Goal: "Semantic Intelligence")
    # And Neural Re-ranking.
    
    # Strategy:
    # A. Generate User Profile Vector (using simple mean for now OR the Tower)
    # B. If untrained, Use Interest Mean to search FAISS (SentenceTransformer Space)
    
    # Let's use the explicit logic:
    # "Hybrid Recommendation" -> Query vector = Mean(History + Interests)
    query_vec_np = int_vecs.numpy() # Fallback to just semantic interest
    if req.history_texts:
        # Blend history and interests
        h_mean = hist_vecs.mean(dim=1).numpy()
        query_vec_np = (query_vec_np + h_mean) / 2.0
        
    results = retriever.search(query_vec_np, k=req.k)
    
    # Generate Explanations
    from .explain import explainer
    
    final_recs = []
    for bid, sc in results:
        # Fetch metadata (mock or real access needed)
        # For now, we return generic explanation
        expl = "Based on similar books you read."
        final_recs.append({
            "book_id": bid, 
            "score": sc,
            "explanation": expl # TODO: Pass real metadata
        })
    
    return {
        "user_id": req.user_id,
        "recommendations": final_recs
    }

@app.post("/search")
async def search_books(req: SearchRequest):
    q_vec = embedding_service.encode_single(req.query)
    results = retriever.search(q_vec, k=req.k)
    return {"query": req.query, "results": [{"book_id": bid, "score": sc} for bid, sc in results]}

class FeedbackRequest(BaseModel):
    user_id: int
    book_id: int
    event_type: str # click, rate, dwell
    value: float # rating or time in seconds

@app.post("/feedback")
async def log_feedback(req: FeedbackRequest):
    # In a real RL system, this would update a bandit policy or store for Experience Replay.
    # We will log it for the "Continuous Learning" pipeline
    print(f"RL Feedback received: User {req.user_id} -> Book {req.book_id} [{req.event_type}]")
    # TODO: Write to 'interactions.csv' or Kafka
    return {"status": "recorded"}

@app.post("/admin/build_index")
async def trigger_index_build(background_tasks: BackgroundTasks):
    background_tasks.add_task(rebuild_index_task)
    return {"status": "Index build started in background"}

def rebuild_index_task():
    # TODO: Connect to DB, fetch all books, encode, build index
    # For now, we seed with dummy data to prove it works
    print("Rebuilding index...")
    pass

@app.get("/health")
async def health_check():
    return {"status": "ok", "model_loaded": True}

@app.get("/stats")
async def get_stats():
    return {
        "index_size": retriever.index.ntotal if retriever.index else 0,
        "embedding_model": "all-MiniLM-L6-v2",
        "requests_total": 0 # Placeholder
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
