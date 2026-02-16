from src.config import ONNX_MODEL_PATH, LABELS_PATH
from src.classifier.ai_model import DistilBertClassifier
import json

def main():
    print("Loading Classifier...")
    classifier = DistilBertClassifier(ONNX_MODEL_PATH, LABELS_PATH)

    print("Ready!\n")

    while True:
        command = input("Enter command (or 'quit' to exit): ")

        if command.lower() == 'quit':
            break

        result = classifier.classify(command)

        response = {
            "status": "success",
            "intent": result["intent"],
            "all_intents": result["all_intents"],
            "confidence": result["confidence"],
            "parameters": result["parameters"]
        }

        print(response)
        print()
        print(json.dumps(response, indent=2))
        print()

if __name__ == "__main__":
    main()