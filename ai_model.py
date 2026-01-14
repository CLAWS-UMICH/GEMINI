
import re
from typing import Dict, List, Optional

class IntentClassifier:
    """
    Classifies user commands into predefined intents using keyword matching.
    Simple placeholder classifier - upgrade to AI later.
    """

    def __init__(self, intent_mappings: Dict[str, str]):
        """
        Initialize classifier with intent mappings from config.
        """
        self.intent_mappings = intent_mappings
    
    def classify(self, text: str) -> dict:
        """
        Classify user command into an intent with confidence score
        """

        # Handle empty or whitespace text
        if not text or not text.strip():
            return {
                "intent": "unknown_intent",
                "confidence": 0.0,
                "matched_keywords": []
            }
        
        # Clean/Preprocess Text
        processed_text = self._preprocess(text)

        # Find matching keywords
        matches = self._match_keywords(processed_text)

        # If no matches found
        if not matches:
            return {
                "intent": "unknown_intent",
                "confidence": 0.0,
                "matched_keywords": []
            }
        
        # Get the best match
        best_match = matches[0]
        keyword = best_match["keyword"]
        intent = best_match["intent"]

        confidence = self._calculate_confidence(matches, processed_text)

        return {
            "intent": intent,
            "confidence": confidence,
            "matched_keywords": [keyword]
        }
    
    def _preprocess(self, text: str) -> str:
        """
        Clean and normalize text for matching
        """

        # Convert to lowercase
        text = text.lower()

        # Remove extra whitespaces
        text = text.strip()

        # Remove punctuation, keep alphanumeric + spaces only
        text = re.sub(r'[^\w\s]', '', text)

        return text

    def _match_keywords(self, text: str) -> List[dict]:
        """
        Find all keywords that appear in the text.
        """

        matches = []

        # Check each keyword in our mappings
        for keyword, intent in self.intent_mappings.items():
            # Check if keyword appears in text
            if keyword in text:
                matches.append({
                    "keyword": keyword,
                    "intent": intent
                })
        
        return matches

    def _calculate_confidence(self, matches: List[dict], text: str) -> float:
        """
        Calculate confidence score based on keyword matches.
        """

        if not matches:
            return 0.0
        
        best_match = matches[0]
        keyword = best_match["keyword"]

        # Base confidence on keyword length and text length
        keyword_length = len(keyword.split())
        text_length = len(text.split())

        # Longer, more specific keywords = higher confidence
        if keyword_length > 1:
            base_confidence = 0.9
        else:
            base_confidence = 0.85

        # Boost confidence if keyword takes up significant portion of text
        keyword_ratio = keyword_length / text_length if text_length > 0 else 0

        # Calculate final confidence
        confidence = base_confidence + keyword_ratio * 0.1

        # Clamp between 0.0 and 1.0
        confidence = min(1.0, max(0.0, confidence))

        return round(confidence, 2)
