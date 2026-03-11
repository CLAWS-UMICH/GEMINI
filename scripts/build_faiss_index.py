import sys
from langchain_community.document_loaders import DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from src.config import EVA_PROCEDURES_DIR, FAISS_INDEX_DIR, MINILM_MODEL_DIR

def main():
    loader = DirectoryLoader(str(EVA_PROCEDURES_DIR), glob="**/*.txt")
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
    index.save_local(str(FAISS_INDEX_DIR))

    print(f"Loaded {len(docs)} documents")
    print(f"Created {len(chunks)} chunks")
    print(f"Index saved to {FAISS_INDEX_DIR}")

if __name__ == "__main__":
    main()