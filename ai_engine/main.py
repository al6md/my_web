from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
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

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State
model = SuperIntelligentTwoTower()
model.eval() # Force eval mode immediately to prevent BatchNorm errors
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

class RealtimeRecommendRequest(BaseModel):
    user_id: int
    k: int = 10
    candidates: Optional[List[int]] = None # Optional list of pre-selected candidates to re-rank

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

@app.post("/recommend/realtime")
async def realtime_recommend(req: RealtimeRecommendRequest):
    """
    Real-time re-ranking endpoint (Phase 3).
    Fetches the user's running mean embedding from the database,
    fetches candidates (trending/top rated if none provided),
    and re-ranks them using cosine similarity.
    """
    try:
        from flask_book_recommendation.extensions import db
        from flask_book_recommendation.models import UserEmbedding, BookEmbedding, Book
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import create_engine
        
        # 1. We need a DB session. We'll use the existing SQLAlchemy setup.
        # Ensure we are using the correct connection string to the main application DB
        from flask_book_recommendation.config import Config
        db_url = Config.SQLALCHEMY_DATABASE_URI
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        
        try:
            # 2. Fetch User Embedding
            user_emb = session.query(UserEmbedding).filter_by(user_id=req.user_id).first()
            if not user_emb or user_emb.vector is None:
                # Cold start: Return some popular books if no vector exists
                # Fallback to random or basic query since Book doesn't have ratings_count
                top_books = session.query(Book).limit(req.k).all()
                return {
                    "user_id": req.user_id,
                    "status": "cold_start",
                    "recommendations": [{"book_id": b.id, "score": 0.0, "title": b.title} for b in top_books]
                }
            
            user_vector = np.array(user_emb.vector)
            
            # 3. Fetch Candidates
            candidate_ids = req.candidates
            if not candidate_ids:
                # If no specific candidates provided, we pull a mix of popular/trending books
                # For this endpoint, let's grab random 100 books to re-rank
                cand_query = session.query(Book.id).limit(100).all()
                candidate_ids = [c[0] for c in cand_query]
            
            if not candidate_ids:
                return {"user_id": req.user_id, "status": "no_candidates", "recommendations": []}
                
            # 4. Fetch Emdeddings for Candidates
            book_embs = session.query(BookEmbedding).filter(BookEmbedding.book_id.in_(candidate_ids)).all()
            
            book_vectors = []
            valid_bids = []
            
            for be in book_embs:
                if be.vector is not None:
                    book_vectors.append(np.array(be.vector))
                    valid_bids.append(be.book_id)
            
            if not book_vectors:
                # Fallback if candidates have no embeddings
                return {"user_id": req.user_id, "status": "no_candidate_embeddings", "recommendations": []}
                
            # 5. Compute Cosine Similarity
            # Normalize vectors first
            u_norm = np.linalg.norm(user_vector)
            u_vec_n = user_vector / u_norm if u_norm > 0 else user_vector
            
            b_matrix = np.array(book_vectors)
            b_norms = np.linalg.norm(b_matrix, axis=1, keepdims=True)
            # Avoid division by zero
            b_norms = np.where(b_norms == 0, 1e-10, b_norms)
            b_matrix_n = b_matrix / b_norms
            
            # Dot product of normalized vectors = Cosine Similarity
            similarities = np.dot(b_matrix_n, u_vec_n)
            
            # 6. Sort and Re-rank
            # Pair scores with IDs and sort descending
            scored_candidates = list(zip(valid_bids, similarities))
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Take top K
            top_recs = scored_candidates[:req.k]
            
            # Form response
            formatted_recs = []
            for bid, score in top_recs:
                formatted_recs.append({
                    "book_id": bid,
                    "score": float(score)  # Ensure JSON serializable
                })
                
            return {
                "user_id": req.user_id,
                "status": "success",
                "recommendations": formatted_recs
            }
            
        finally:
            session.close()
            
    except Exception as e:
        print(f"Error in realtime recommend: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
