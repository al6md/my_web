import requests
import logging

logger = logging.getLogger(__name__)

class AIClient:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()

    def get_recommendations(self, user_id, history_texts=None, interest_texts=None, k=10):
        """
        Call the Two-Tower Neural Recommender.
        """
        payload = {
            "user_id": user_id,
            "history_texts": history_texts or [],
            "interest_texts": interest_texts or [],
            "k": k
        }
        
        try:
            resp = self.session.post(f"{self.base_url}/recommend", json=payload, timeout=2.0)
            resp.raise_for_status()
            return resp.json().get("recommendations", [])
        except requests.exceptions.RequestException as e:
            logger.warning(f"AI Engine unreachable (Recommend): {e}")
            return None # Indicate fallback needed

    def semantic_search(self, query, k=10):
        """
        Call Semantic Search.
        """
        try:
            resp = self.session.post(f"{self.base_url}/search", json={"query": query, "k": k}, timeout=2.0)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except requests.exceptions.RequestException as e:
            logger.warning(f"AI Engine unreachable (Search): {e}")
            return None

    def send_feedback(self, user_id, book_id, event_type, value):
        """
        Fire-and-forget RL feedback.
        """
        payload = {
            "user_id": user_id,
            "book_id": book_id,
            "event_type": event_type,
            "value": value
        }
        try:
            # Short timeout, we don't want to block UI for logging
            self.session.post(f"{self.base_url}/feedback", json=payload, timeout=0.5)
        except:
            pass # Ignore errors for feedback logging

    def get_health(self):
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=1.0)
            return resp.json() if resp.ok else {"status": "error"}
        except:
            return {"status": "offline"}

    def get_stats(self):
        try:
            resp = self.session.get(f"{self.base_url}/stats", timeout=1.0)
            return resp.json() if resp.ok else {}
        except:
            return {}

    def trigger_index_rebuild(self):
        try:
            resp = self.session.post(f"{self.base_url}/admin/build_index", timeout=1.0)
            return resp.json() if resp.ok else {"status": "error"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Singleton
ai_client = AIClient()
