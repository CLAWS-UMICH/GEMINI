import logging
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from src.config import FAISS_INDEX_DIR, MINILM_MODEL_DIR

class LangChainFAISSStore:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=str(MINILM_MODEL_DIR),
            model_kwargs={"device": "cpu"}
        )

        try:
            self.vectorstore = FAISS.load_local(
                folder_path=str(FAISS_INDEX_DIR),
                embeddings=self.embeddings, 
                allow_dangerous_deserialization=True
            )
            logging.info("FAISS index loaded successfully")
        except Exception as e:
            logging.warning(f"FAISS index not found, RAG disabled: {e}")
            self.vectorstore = None

    def get_retriever(self, k=3):
        if self.vectorstore is None:
            return None
        return self.vectorstore.as_retriever(search_kwargs={"k": k})