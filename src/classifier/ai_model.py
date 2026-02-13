
import json
import numpy as np
import onnxruntime as ort
import re
from transformers import AutoTokenizer
from typing import Dict, List, Optional

def sigmoid(x):
    """Converts model outputs (logits) to probabilities between 0 and 1"""
    return 1 / (1 + np.exp(-x))

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

class DistilBertClassifier:

    def __init__(self, model_path, labels_path):
        """Load ONNX mode, tokenizer, and label mappings"""

        # Get model directory
        model_dir = model_path.parent

        # Load ONNX runtime session
        self.session = ort.InferenceSession(str(model_path))

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))

        with open(labels_path, "r") as f:
            labels = json.load(f)
            self.tool_labels = labels["tool_labels"]
            self.token_labels = labels["token_labels"]

    def classify(self, text:str) -> dict:
        """Classify user command and extract entities"""
        if not text or not text.strip():
            return {
                "intent": "unknown_intent",
                "confidence": 0.0,
                "parameters": {}
            }
    
        inputs = self.tokenizer(text, return_tensors="np")

        input_ids = inputs["input_ids"].astype(np.int64)
        attention_mask = inputs["attention_mask"].astype(np.int64)

        input_feed = {
            "input_ids": input_ids,
            "attention_mask": attention_mask
        }

        outputs = self.session.run(None, input_feed)

        tag_logits = outputs[0][0]
        count_pred = outputs[1][0][0]
        token_logits = outputs[2][0]

        tag_probs = sigmoid(tag_logits)

        k = max(1, int(round(count_pred)))

        top_indices = np.argsort(tag_probs)[-k:][::-1]

        top_tools = [self.tool_labels[i] for i in top_indices]
        top_confidence = [float(tag_probs[i]) for i in top_indices]

        primary_intent = top_tools[0]
        primary_confidence = top_confidence[0]

        parameters = self._extract_entities(text, inputs, token_logits)

        return {
            "intent": primary_intent,
            "confidence": round(primary_confidence, 3),
            "all_intents": list(zip(top_tools, top_confidence)),
            "parameters": parameters
        }
    

    def _extract_entities(self, text:str, inputs, token_logits) -> dict:
        """Extract named entities from token predictions"""

        parameters = {}

        token_pred_indices = np.argmax(token_logits, axis=-1)

        tokens = self.tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])

        current_entity = None
        current_tokens = []

        for token, label_idx in zip(tokens, token_pred_indices):
            if token in ["[CLS]", "[SEP]", "[PAD]"]:
                continue

            label = self.token_labels[label_idx]


            if label != "TEXT":  # "TEXT" means not an entity
                if label == current_entity:
                    # Same entity continues - add token
                    current_tokens.append(token)
                else:
                    # Different entity - save previous, start new
                    if current_entity and current_tokens:
                        entity_text = self._merge_tokens(current_tokens)
                        parameters[current_entity] = entity_text
                    # Start tracking new entity
                    current_entity = label
                    current_tokens = [token]
            else:
                # Hit a TEXT token - save current entity if exists
                if current_entity and current_tokens:
                    entity_text = self._merge_tokens(current_tokens)
                    parameters[current_entity] = entity_text
                current_entity = None
                current_tokens = []

        # Don't forget the last entity (if sentence ends with one)
        if current_entity and current_tokens:
            entity_text = self._merge_tokens(current_tokens)
            parameters[current_entity] = entity_text

        return parameters
    
    def _merge_tokens(self, tokens: list) -> str:                                                                                                                                                                      
        """    
        Merge subword tokens back into readable text.
        """
        text = ""
        for token in tokens:
            if token.startswith("##"):
                # Subword token - append without space, remove ##
                text += token[2:]
            else:
                # Regular token - add space before (if not first)
                if text:
                    text += " "
                text += token
        return text

    
