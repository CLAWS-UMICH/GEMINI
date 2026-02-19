from src.config import CONFIDENCE_THRESH_HIGH
# from src.classifier.intent_classifier import IntentClassifier
class RoutingClassifier:
    def __init__(self):
        self.threshold = CONFIDENCE_THRESH_HIGH
        self.anaphora_list = ["that", "it", "this", "there", "those", "these", "its"]

    def route(self, text, classification):
        if classification['confidence'] < self.threshold:
            return {
                "route": "cloud",
                "reason": "low confidence"
            }
        
        words = text.lower().split()
        if any(word in self.anaphora_list for word in words):
            return {
                "route": "cloud",
                "reason": "anaphora"
            }
        
        return {
            "route": "local",
            "reason": "normal command"
        }

        



        