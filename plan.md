# CORVUS: Next Tasks Checklist

## Task 1 — Fix config.py ✅

- [x] Fix `NN_MODEL_DIR`: remove leading space, change path `nn-model` → `minilm-nn`
- [x] Add `NN_MODEL_PATH = NN_MODEL_DIR / "intent_nn.pt"`
- [x] Add `USE_NN_MODEL = True` flag (replaces `USE_ONNX_MODEL` eventually)
- [x] Add `FAISS_INDEX_DIR = BASE_DIR / "data" / "rag" / "faiss_index"`
- [x] Add `EVA_PROCEDURES_DIR = BASE_DIR / "data" / "rag" / "eva_procedures"`
- [x] Add `TRAINING_DATA_PATH = BASE_DIR / "data" / "intents" / "training_data.json"`
- [x] Move `training_data.json` to `data/intents/`

**File:** `src/config.py`

---

## Task 2 — Update embedder.py (load local fine-tuned MiniLM) ✅

- [x] Change `SentenceTransformer("all-MiniLM-L6-v2")` to load from `MINILM_MODEL_DIR`
- [x] Import `MINILM_MODEL_DIR` from `src.config`
- [x] Add fallback: if local path doesn't exist, load from HuggingFace and log a warning

**File:** `src/classifier/embedder.py`
**Saved model at:** `models/embeddings/minilm/`

---

## Task 3 — Wire MiniLM classifier into websocket_handler.py ✅

### 3a. Load classifiers as singletons (not per-client)
- [x] Move `IntentClassifier` + `RoutingClassifier` initialization to module level (before `handle_client`)
- [x] Load label list from `training_data.json` (intent labels in order)
- [x] Import `IntentClassifier` from `src.classifier.intent_classifier`
- [x] Import `RoutingClassifier` from `src.classifier.routing_classifier`

### 3b. Add USE_NN_MODEL branch
- [x] Add `elif USE_NN_MODEL:` branch alongside existing `USE_ONNX_MODEL` in `handle_client`
- [x] Pass shared classifier instance to `handle_message` instead of creating per-client

### 3c. Update handle_message response
- [x] Call `router.route(command, classification)` after classifying
- [x] Add `"route"` field to response JSON (`"local"` or `"cloud"`)
- [x] Add `"reason"` field to response JSON (routing reason string)
- [x] Made optional fields (`all_intents`, `matched_keywords`, `parameters`) conditional — all three classifiers (NN, DistilBERT, keyword) work without breaking

**File:** `src/server/websocket_handler.py`

---

## Task 4 — Prepare EVA procedure documents

- [ ] Add `.txt` files to `data/rag/eva_procedures/` when available:
  - `uia_egress.txt`, `uia_ingress.txt`, `erm_procedure.txt`
  - `ltv_diagnosis.txt`, `ltv_nav_restart.txt`, `physical_repair.txt`, `final_system_checks.txt`
- [ ] Format: plain text, one step per line, with section headings
- [ ] Then run `uv run python scripts/build_faiss_index.py` to build the index

**Note:** Infrastructure (Tasks 5-10) works without documents — FAISS tool returns "no procedures available" gracefully.

**Directory:** `data/rag/eva_procedures/`

---

## Task 5 — Update config.py with LLM settings

- [ ] Add LLM provider config using `os.getenv`:
  - `LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")`
  - `GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")`
  - `GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")`
  - `LLM_MODEL_GROQ = "llama-3.3-70b-versatile"`
  - `LLM_MODEL_GEMINI = "gemini-1.5-flash"`
  - `LLM_TEMPERATURE = 0.2`

**File:** `src/config.py`

---

## Task 6 — Write `src/rag/vector_store.py` (LangChain FAISS wrapper)

- [ ] `LangChainFAISSStore` class:
  - `__init__`: load FAISS from `data/rag/faiss_index/` using `HuggingFaceEmbeddings` pointing at `MINILM_MODEL_DIR` — log warning and set `self.vectorstore = None` if index missing
  - `get_retriever(k=3)`: returns LangChain retriever or `None`
- [ ] Uses `langchain_community.vectorstores.FAISS` + `langchain_huggingface.HuggingFaceEmbeddings`

**File:** `src/rag/vector_store.py`

---

## Task 7 — Write `scripts/build_faiss_index.py` (LangChain-based)

- [ ] Steps:
  1. Load `.txt` files from `data/rag/eva_procedures/` via `DirectoryLoader`
  2. If empty → print "No documents found. Add .txt files and re-run." and exit
  3. Chunk with `RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)`
  4. Embed with `HuggingFaceEmbeddings` (same fine-tuned MiniLM)
  5. Build `FAISS.from_documents()` and save to `data/rag/faiss_index/`
  6. Print: docs loaded, chunks created, index saved
- [ ] No code changes needed to add documents later — just drop files and re-run

**File:** `scripts/build_faiss_index.py`

---

## Task 8 — Write `src/context/context_window.py` (conversation memory)

- [ ] `ConversationMemory` class (one instance per WebSocket session):
  - `__init__`: wraps `ConversationTokenBufferMemory(max_token_limit=1000)`
  - `add_turn(user_msg, assistant_msg)`: appends to history
  - `get_history()`: returns LangChain message list
  - `clear()`: resets memory
- [ ] Token limit keeps memory within Jetson RAM budget

**File:** `src/context/context_window.py`

---

## Task 9 — Write `src/cloud/` (LLM client + prompt + agent)

### 9a. `src/cloud/api_client.py`
- [ ] `get_llm()` — returns initialized LangChain chat model:
  - `"groq"` → `ChatGroq(api_key=GROQ_API_KEY, model=LLM_MODEL_GROQ, temperature=LLM_TEMPERATURE)`
  - `"gemini"` → `ChatGoogleGenerativeAI(model=LLM_MODEL_GEMINI, temperature=LLM_TEMPERATURE)`

### 9b. `src/cloud/prompt_builder.py`
- [ ] `SYSTEM_PROMPT`: CORVUS persona, EVA context, 1-3 sentence brevity for TTS, tool-use instruction
- [ ] `get_prompt_template()` → `ChatPromptTemplate` with `{chat_history}`, `{input}`, `{agent_scratchpad}`

### 9c. `src/cloud/cloud_handler.py`
- [ ] `CloudHandler` singleton class:
  - Two tools:
    1. `lookup_procedure(query)` — calls FAISS retriever; returns "no procedures available" if no index
    2. `get_telemetry(metric)` — mock vitals dict (`heart_rate`, `oxygen`, `suit_pressure`, `co2`, `temperature`) — replace with LMCC call later
  - Agent: `create_tool_calling_agent(llm, tools, prompt)` wrapped in `AgentExecutor(max_iterations=3)`
  - `handle(command, memory)` → invokes agent with history, calls `memory.add_turn()`, returns response string

**Files:** `src/cloud/api_client.py`, `src/cloud/prompt_builder.py`, `src/cloud/cloud_handler.py`

---

## Task 10 — Wire cloud path into `websocket_handler.py`

- [ ] Import `CloudHandler` + `ConversationMemory` at module level
- [ ] Instantiate `cloud_handler = CloudHandler()` as singleton (module level)
- [ ] In `handle_client`: instantiate `memory = ConversationMemory()` per session
- [ ] Pass `memory` into `handle_message`
- [ ] In `handle_message`: if `routing["route"] == "cloud"` → call `cloud_handler.handle(command, memory)` and add `"response"` to JSON
- [ ] Install deps: `uv add langchain langchain-community langchain-groq langchain-google-genai langchain-huggingface faiss-cpu`

**File:** `src/server/websocket_handler.py`

---

## New Agentic Features Added

| Feature | Benefit |
|---------|---------|
| Tool-calling agent (Groq, free) | Agent decides when to look up procedures vs answer directly |
| FAISS RAG tool | Retrieves EVA procedures into context (graceful empty fallback) |
| Mock telemetry tool | Tests tool-calling; swap for real LMCC data when ready |
| Per-session conversation memory | Resolves anaphora ("is that normal?" knows what "that" refers to) |

---

## Future Feature Ideas (RAG + LangChain + Cloud API)

### Conversational Intelligence
- **Conversation memory** — retains context across turns; resolves anaphora ("is that normal?", "do it again")
- **Session summarization** — at end of EVA, summarize what was asked and flagged
- **Follow-up detection** — recognize follow-up vs new command, route accordingly

### Retrieval & Knowledge
- **EVA procedure RAG** — pull relevant checklist steps into cloud context when astronaut asks "how do I...?"
- **Multi-doc synthesis** — agent combines info from multiple procedure docs to answer compound questions
- **Knowledge graph** — link procedures to intents so "egress" queries auto-pull UIA egress steps

### Tool-Calling Agent Capabilities
- **Live telemetry tool** — agent queries real suit vitals before answering health questions (replaces mock)
- **Timer/reminder tool** — "remind me in 10 minutes to check CO2"
- **Checklist tool** — agent marks tasks complete, reads back remaining steps
- **Alert tool** — triggers flagged alert to mission control when anomaly detected in a query
- **Navigation tool** — queries current waypoint or reroutes via LMCC

### Accuracy & Confidence
- **Confidence-gated RAG** — when local confidence is 0.5–0.65, add RAG context before routing decision
- **Clarification requests** — agent asks follow-up when query is too ambiguous to act on safely
- **Structured output enforcement** — LLM returns validated JSON so Unity can parse reliably

### Voice-Specific Optimizations
- **Streaming TTS pipeline** — stream LLM tokens into Piper TTS queue; audio starts before response finishes
- **Filler response** — while agent runs tools (~500ms), send "checking now..." to TTS immediately
- **Urgency detection** — flag safety-critical queries ("I feel dizzy") for immediate escalation
- **Response length control** — enforce 1–2 sentences for voice; detail available on follow-up

### Multimodal / Future
- **Image-grounded RAG** — HoloLens camera frame → Gemini Vision describes scene → pulls relevant procedures
- **Mission log ingestion** — RAG over past EVA logs to answer "did we see this issue before?"

---

## Verification

After each task, verify:
- **Task 2** ✅: `python -c "from src.classifier.embedder import MiniLMEmbedder; e = MiniLMEmbedder(); print(e.encode('test').shape)"` → `(384,)`
- **Task 3** ✅: Server running, send `{"command": "check my vitals"}` → response includes `"route": "local"`
- **Task 7**: `uv run python scripts/build_faiss_index.py` → "No documents found" (until docs added)
- **Task 10**: Set `GROQ_API_KEY`, start server, send `{"command": "is my oxygen level normal?"}` → `"route": "cloud"`, `"response": "Your oxygen is at 98%..."` (agent calls get_telemetry), then send `{"command": "what about my heart rate?"}` → agent uses memory to resolve context
