# CORVUS: Next Tasks Checklist

## Task 1 — Fix config.py

- [ ] Fix `NN_MODEL_DIR`: remove leading space, change path `nn-model` → `minilm-nn`
- [ ] Add `NN_MODEL_PATH = NN_MODEL_DIR / "intent_nn.pt"`
- [ ] Add `USE_NN_MODEL = True` flag (replaces `USE_ONNX_MODEL` eventually)
- [ ] Add `FAISS_INDEX_DIR = BASE_DIR / "data" / "rag" / "faiss_index"`
- [ ] Add `EVA_PROCEDURES_DIR = BASE_DIR / "data" / "rag" / "eva_procedures"`

**File:** `src/config.py`

---

## Task 2 — Update embedder.py (load local fine-tuned MiniLM)

- [ ] Change `SentenceTransformer("all-MiniLM-L6-v2")` to load from `MINILM_MODEL_DIR`
- [ ] Import `MINILM_MODEL_DIR` from `src.config`
- [ ] Add fallback: if local path doesn't exist, load from HuggingFace and log a warning

**File:** `src/classifier/embedder.py`
**Saved model at:** `models/embeddings/minilm/`

---

## Task 3 — Wire MiniLM classifier into websocket_handler.py

### 3a. Load classifiers as singletons (not per-client)
- [ ] Move `IntentClassifier` + `RoutingClassifier` initialization to module level (before `handle_client`)
- [ ] Load label list from `training_data.json` (intent labels in order)
- [ ] Import `IntentClassifier` from `src.classifier.intent_classifier`
- [ ] Import `RoutingClassifier` from `src.classifier.routing_classifier`

### 3b. Add USE_NN_MODEL branch
- [ ] Add `elif USE_NN_MODEL:` branch alongside existing `USE_ONNX_MODEL` in `handle_client`
- [ ] Pass shared classifier instance to `handle_message` instead of creating per-client

### 3c. Update handle_message response
- [ ] Call `router.route(command, classification)` after classifying
- [ ] Add `"route"` field to response JSON (`"local"` or `"cloud"`)
- [ ] Add `"reason"` field to response JSON (routing reason string)
- [ ] Remove `"all_intents"` and `"matched_keywords"` (DistilBERT-specific fields, not returned by IntentClassifier)

**File:** `src/server/websocket_handler.py`

---

## Task 4 — Prepare EVA procedure documents

- [ ] Create text files for each TSS 2026 procedure in `data/rag/eva_procedures/`
  - `uia_egress.txt` — UIA egress checklist steps
  - `uia_ingress.txt` — UIA ingress checklist steps
  - `erm_procedure.txt` — Exit Recovery Mode steps
  - `ltv_diagnosis.txt` — LTV system diagnosis steps
  - `ltv_nav_restart.txt` — LTV nav system restart steps
  - `physical_repair.txt` — Bus connector reconnection steps
  - `final_system_checks.txt` — Post-repair final checks
- [ ] Format: plain text, one step per line, include headings per section

**Directory:** `data/rag/eva_procedures/`

---

## Task 5 — Write vector_store.py

- [ ] Create `src/rag/vector_store.py`
- [ ] `FAISSVectorStore` class with:
  - `__init__`: load FAISS index + document list from disk
  - `search(query_embedding, k=3)`: returns top-k most similar document chunks
- [ ] Use `faiss.read_index()` to load from `data/rag/faiss_index/`
- [ ] Store document text alongside index for retrieval

**File:** `src/rag/vector_store.py`

---

## Task 6 — Write build_faiss_index.py

- [ ] Create `scripts/build_faiss_index.py`
- [ ] Steps:
  1. Load all `.txt` files from `data/rag/eva_procedures/`
  2. Chunk each document (~200 tokens per chunk, with overlap)
  3. Embed each chunk using `MiniLMEmbedder`
  4. Build `faiss.IndexFlatIP` (inner product / cosine similarity)
  5. Save index to `data/rag/faiss_index/index.faiss`
  6. Save chunk texts to `data/rag/faiss_index/chunks.json`
- [ ] Print summary: number of documents, chunks, index size

**File:** `scripts/build_faiss_index.py`

---

## Verification

After each task, verify:
- **Task 2**: Run `python -c "from src.classifier.embedder import MiniLMEmbedder; e = MiniLMEmbedder(); print(e.encode('test').shape)"` — should print `(384,)` without HuggingFace download
- **Task 3**: Start server (`uv run python -m src.server.main`), send `{"command": "check my vitals"}` via WebSocket client — response should include `"route": "local"` and `"intent": "open_menu_vitals"`
- **Task 6**: Run `uv run python scripts/build_faiss_index.py` — should print chunk count and confirm files saved to `data/rag/faiss_index/`
