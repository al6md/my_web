from flask_book_recommendation.app import create_app
from flask_book_recommendation.recommender import get_trending, get_topic_based
import time

app = create_app()

with app.app_context():
    print("Testing get_trending()...")
    start = time.time()
    try:
        trending = get_trending(limit=12)
        print(f"Got {len(trending)} trending books in {time.time()-start:.2f}s")
        for b in trending:
            print(b.get("title"), b.get("source"))
    except Exception as e:
        print(f"Error in get_trending: {e}")
    
    print("\nTesting get_topic_based() with dummy query...")
    start = time.time()
    try:
        # User ID None for fallback testing
        topic = get_topic_based(user_id=None, limit=12, recent_query="برمجة")
        res = topic.get('books', []) if isinstance(topic, dict) else topic
        print(f"Got {len(res)} topic books in {time.time()-start:.2f}s")
    except Exception as e:
        print(f"Error in get_topic_based: {e}")
