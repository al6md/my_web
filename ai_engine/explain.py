from typing import List, Dict

class ExplainabilityEngine:
    def explain_recommendation(self, user_interests: List[str], book_metadata: Dict) -> str:
        """
        Generates a natural language explanation for why a book was recommended.
        """
        # Logic: Find intersection between user interests and book tags/description
        matched_keywords = []
        book_text = (book_metadata.get('title', '') + " " + book_metadata.get('description', '')).lower()
        
        for interest in user_interests:
            if interest.lower() in book_text:
                matched_keywords.append(interest)
                
        if matched_keywords:
            return f"Recommended because you are interested in {', '.join(matched_keywords[:3])}."
        
        return "Recommended based on your reading history and reading patterns."

explainer = ExplainabilityEngine()
