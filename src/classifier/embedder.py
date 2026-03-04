from sentence_transformers import SentenceTransformer
from src.config import MINILM_MODEL_DIR
import logging

class MiniLMEmbedder:
    def __init__(self):
        if MINILM_MODEL_DIR.exists():
            self.model = SentenceTransformer(str(MINILM_MODEL_DIR))
        else:
            logging.warning("Local MiniLM not found, loading from HuggingFace")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def encode(self, command):
        return self.model.encode(command)