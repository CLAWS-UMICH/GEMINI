from src.config import NN_MODEL_PATH, TRAINING_DATA_PATH
from src.classifier.intent_classifier import IntentClassifier
from src.classifier.routing_classifier import RoutingClassifier
import json

def main():
    print("Loading Classifier...")

    with open(TRAINING_DATA_PATH) as f:
        _data = json.load(f)
    _labels = [intent["label"] for intent in _data["intents"]]
    classifier = IntentClassifier(_labels, NN_MODEL_PATH)
    router = RoutingClassifier()

    print("Ready!\n")

    while True:
        command = input("Enter command (or 'quit' to exit): ")

        if command.lower() == 'quit':
            break

        classification = classifier.classify(command)
        routing = router.route(command, classification)

        response = {
            "status": "success",
            "intent": classification["intent"],
            "confidence": classification["confidence"],
            "route": routing["route"],
            "reason": routing["reason"]
        }

        print(response)
        print()
        print(json.dumps(response, indent=2))
        print()

if __name__ == "__main__":
    main()