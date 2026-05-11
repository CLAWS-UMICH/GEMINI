import sys
from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from src.config import MINILM_MODEL_DIR

_BASE_DIR = Path(__file__).parent.parent
_EVA_PROCEDURES_DIR = _BASE_DIR / "data" / "rag" / "eva_procedures"
_FAISS_INDEX_DIR = _BASE_DIR / "data" / "rag" / "faiss_index"

def main():
    loader = DirectoryLoader(str(_EVA_PROCEDURES_DIR), glob="**/*.txt")
    docs = loader.load()

    if not docs:
        print("No documents found. Add .txt files to data/rag/eva_procedures/ and re-run.")
        sys.exit(0)

    textSplitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = textSplitter.split_documents(docs)

    embeddings = HuggingFaceEmbeddings(
        model_name=str(MINILM_MODEL_DIR),
        model_kwargs={"device": "cpu"}
    )

    index = FAISS.from_documents(chunks, embeddings)
    index.save_local(str(_FAISS_INDEX_DIR))

    print(f"Loaded {len(docs)} documents")
    print(f"Created {len(chunks)} chunks")
    print(f"Index saved to {_FAISS_INDEX_DIR}")

if __name__ == "__main__":
    main()