from transformers import pipeline

class ConversationalRecommender:
    def __init__(self):
        # We use a small instruction-tuned model or placeholder
        # For a graduation project, we might stick to simple logic or API wrapper
        print("Initializing LLM for Chat...")
        # self.llm = pipeline("text-generation", model="gpt2") # Placeholder
    
    def chat(self, user_message: str):
        # 1. Intent Classification
        if "recommend" in user_message.lower():
            return self._handle_recommend_intent(user_message)
        
        return "I can help you find books. Tell me what you like!"
        
    def _handle_recommend_intent(self, text):
        # Extract keywords and call internal API
        return "I found some books for you based on your description..."

chatbot = ConversationalRecommender()
