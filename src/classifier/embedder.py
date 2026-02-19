from sentence_transformers import SentenceTransformer

class MiniLMEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(self, command):
        return self.model.encode(command)