import torch
from torch import nn
from src.classifier.embedder import MiniLMEmbedder

class IntentNN(nn.Module):
    def __init__(self, num_intents):
        super().__init__()
        self.device = torch.accelerator.current_accelerator().type if torch.accelerator.is_available() else "cpu"
        print(f"Using {self.device} device")
        
        self.model = nn.Sequential(
            nn.Linear(384, 256),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(256, num_intents),
        )

    def forward(self, x):
        return self.model(x)

class IntentClassifier:
    def __init__(self, labels, model_path):
        self.labels = labels
        self.embedder = MiniLMEmbedder()
        self.model = IntentNN(num_intents=len(labels))
        if(model_path.exists()):
            self.model.load_state_dict(torch.load(model_path, weights_only=True))
        self.model.eval()
        
    def classify(self, command):
        X = torch.tensor(self.embedder.encode(command), dtype=torch.float32)
        with torch.no_grad():
            predX = self.model(X)
            pred_probab = torch.softmax(predX, dim=0)
            y_pred = pred_probab.argmax()
            intent = self.labels[y_pred.item()]
            return {
                "intent": intent,
                "confidence": pred_probab[y_pred].item()
            }

      



    
        
