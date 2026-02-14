import sys
import os
import torch
import numpy as np

# Ensure we can import from the package
sys.path.append(os.getcwd())

from flask_book_recommendation.advanced_recommender.inference import DLInferenceEngine

def verify():
    print("Initializing Engine...")
    engine = DLInferenceEngine()
    
    if not engine.is_ready:
        print("FAIL: Engine not ready. Model file might be missing or invalid.")
        return
        
    print("Engine Ready. Running dummy prediction...")
    
    # Dummy Data
    user_id = 1
    history = np.zeros((10, 384), dtype=np.float32)
    interests = np.zeros((384,), dtype=np.float32)
    candidates = {101: np.random.randn(384).astype(np.float32)}
    
    try:
        scores = engine.predict(user_id, history, interests, candidates)
        print(f"Prediction Success: {scores}")
    except Exception as e:
        print(f"FAIL: Prediction error: {e}")

if __name__ == "__main__":
    verify()
