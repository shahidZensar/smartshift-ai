# SmartShift-AI — End-to-End Architecture

> **Source of truth:** This document is reconstructed directly from the code (commit `35c7dc0`), not from prior docs. Where older docs conflict, trust this.

---

## 0. Tech Stack at a Glance

| Layer | Technology |
|---|---|
| API server | FastAPI + Uvicorn (`app/app.py`), CORS open |
| Intent router | LLM-based, `app/router.py` |
| LLM providers | Ollama / OpenAI / Azure OpenAI / LocalAI / llama.cpp (`app/decision.py`) |
| Relational store | MySQL `inventory` DB (`mysql+pymysql`) — SQL & HYBRID intents |
| Config device store | MySQL `config_inventory` table — CONFIG intent targeting |
| RAG knowledge base | **FAISS** index on disk at `data/rag_index/` |
| Per-session semantic memory | FAISS files at `data/session_memory/<session_id>/` |
| Conversation / CONFIG state | **In-memory Python dict**, 2h TTL (process-local) |
| Playbook registry | YAML files in `repositories/playbook-registry/` |
| Web search | SerpAPI |
| LLM cache | **None active** (LangChain `InMemoryCache` is commented out) |

---

## 1. System Component Diagram

```mermaid
flowchart TB
    subgraph Client["Client (UI)"]
        UI[React UI / HTTP POST]
    end

    subgraph API["FastAPI — app/app.py"]
        EP["/api/v1/chat (askv1_question)"]
        EPlegacy["/api/chat, /api/chat/upload (legacy)"]
        ADMIN["/api/admin/upload-file (ingest docs)"]
    end

    subgraph Orchestration["Orchestration"]
        ROUTER["router.py — classify_intent (LLM)"]
        GATE["CONFIG semantic gate (config_service._detect)"]
        DISPATCH{Intent dispatch}
    end

    subgraph Chains["Intent Chains"]
        CFG[config_service.handle]
        SQLc[sql_chain + final_structured_chain]
        RAGc[rag_chain]
        HYB[sql_chain + retrieve_docs + final_chain]
        SRCH[web_search_chain]
    end

    subgraph LLM["LLM Instances — decision.py"]
        L1[llm — RAG, SEARCH, classify, config]
        L2[openai_llm — SQL, HYBRID]
        EMB[embeddings — nomic-embed-text]
    end

    subgraph Storage["Storage"]
        MYSQL[(MySQL: inventory)]
        CFGINV[(MySQL: config_inventory)]
        FAISS[(FAISS: data/rag_index)]
        MEM[(FAISS: data/session_memory)]
        CONV[(In-mem dict: conversation_store)]
        PBR[(YAML: playbook-registry)]
    end

    UI --> EP --> ROUTER --> GATE --> DISPATCH
    DISPATCH --> CFG & SQLc & RAGc & HYB & SRCH
    ROUTER -.uses.-> L1
    SQLc & HYB -.use.-> L2
    RAGc & SRCH -.use.-> L1
    CFG -.uses.-> L1
    SQLc --> MYSQL
    HYB --> MYSQL & FAISS
    RAGc --> FAISS
    RAGc -.embed.-> EMB
    SRCH --> SerpAPI[(SerpAPI)]
    CFG --> CFGINV & PBR
    DISPATCH -.read/write.-> CONV
    ADMIN --> FAISS
```

---

## 2. Master Request Flow (entry → classification → dispatch)

**Primary endpoint:** `POST /api/v1/chat` → `askv1_question()` (`app/app.py:181`). Synchronous JSON response (no streaming).

```mermaid
flowchart TD
    A[POST /api/v1/chat] --> B{question empty?}
    B -- yes --> B1[HTTP 400]
    B -- no --> C[session_id = request.session_id or new uuid]
    C --> D[history_str = conversation_store.format_recent session_id<br/>last 8 turns, 500 chars each]
    D --> E{Active CONFIG state?<br/>get_config_state, stage != DONE}
    E -- yes --> F[tool = CONFIG  -- bypass classifier]
    E -- no --> G["classify_intent(question, history) — LLM call #1"]
    G --> H{tool == CONFIG?}
    F --> H
    H -- yes --> I["config_service.handle() — semantic gate _detect"]
    I --> J{route == NOT_CONFIG?}
    J -- yes --> K["re-classify with allow_config=False<br/>(breaks endless-config loop)"]
    J -- no --> L[persist turns + return CONFIG payload]
    H -- no --> M
    K --> M{Dispatch on tool}
    M -- SQL --> N[await sql_chain → final_structured_chain]
    M -- RAG --> O[rag_chain]
    M -- HYBRID --> P[sql_chain + retrieve_docs → final_chain]
    M -- SEARCH --> Q[web_search_chain]
    N & O & P & Q --> R[append_turn user + assistant]
    R --> S[JSONResponse]
```

**Intent classification** (`classify_intent`, `router.py:9`):
- Single `llm.invoke(INTENT_CLASSIFIER_PROMPT)` call.
- Override: if response text contains **both** `SQL` and `RAG` → `HYBRID`.
- Else first-match scan over `(CONFIG, HYBRID, SQL, RAG, SEARCH)`; CONFIG filtered out when `allow_config=False`.
- Safe default → `SEARCH`.

**Two config gates** (the "endless config loop" fix):
1. **Resume gate** (`app.py:206`): an in-progress `ConfigState` (stage ≠ DONE) forces CONFIG, skipping the classifier.
2. **Semantic gate** (`app.py:217`): even when classified CONFIG, `config_service._detect` re-checks. A `NOT_CONFIG` route triggers re-classification with CONFIG disabled, preventing bounce-back.

---

## 3. The Five Intents

### 3.1 SQL Intent
```mermaid
flowchart LR
    A[question] --> B["sql_chain() — openai_llm.ainvoke<br/>sql_prompt → QUERY: / PARAMS:"]
    B --> C[format_sql_response → query + params tuple]
    C --> D[pd.read_sql against MySQL inventory table]
    D --> E[pandas post-proc: compute eol day-count, NaN→0, dates→str]
    E --> F[df.to_json → sql_context]
    F --> G["final_structured_chain() — openai_llm.invoke<br/>STRUCTURED_PROMPT → per-device plain text"]
```
- **LLM calls:** 2 (NL→SQL, then format output).
- **DB:** direct `pd.read_sql` on `inventory` table. Safety = prompt + `%s` params + `safe_text()` escaping. **No SQL allowlist/AST validation.**

### 3.2 RAG Intent
```mermaid
flowchart LR
    A[question + history] --> B[vectorstore_manager.retrieve_docs<br/>FAISS similarity_search k=5]
    B --> C["rag_chain() — llm.invoke<br/>RAG_PROMPT: answer from CONTEXT only"]
```
- **Vectorstore:** FAISS at `data/rag_index/` (loaded at startup). Embeddings = `nomic-embed-text:latest`.
- **Ingestion:** offline via `/api/admin/upload-file` → `add_documents()` (batches of 200, 429-retry, incremental save).
- **LLM calls:** 1.

### 3.3 SEARCH Intent
```mermaid
flowchart LR
    A[question] --> B[web_search → SerpAPI organic_results]
    B --> C["web_search_chain() — llm.invoke<br/>WEBESEARCH_PROMPT: summarize, prefer Cisco/Google, drop YouTube"]
```
- **LLM calls:** 1. Returns `[]` if `SERPAPI_API_KEY` missing.

### 3.4 HYBRID Intent
```mermaid
flowchart LR
    A[question] --> B[await sql_chain → sql_context JSON]
    A --> C[retrieve_docs → rag_context FAISS k=5]
    B & C --> D["final_chain() — openai_llm.invoke<br/>final_prompt (util.py): per-device risk + recommendation"]
```
- **Risk classification is done BY THE LLM** inside `final_prompt`, from the pandas-computed `eol` day-count:
  - CRITICAL ≤30d · HIGH 31–90d · MEDIUM 91–180d · LOW >180d · UNKNOWN (no date)
- **LLM calls:** 2 (SQL gen + final synthesis).

### 3.5 CONFIG Intent — see §4.

---

## 4. CONFIG Intent — Stateful Stage Machine

Entry: `ConfigService.handle(message, session_id, form_values)` (`config_service.py:777`). Runs as a **top-to-bottom pipeline each turn**; `state.stage` records where it stopped. State persisted in `conversation_store` (in-mem, 2h TTL).

```mermaid
stateDiagram-v2
    [*] --> DETECT_TYPE
    DETECT_TYPE --> DISAMBIGUATE: multiple candidates
    DETECT_TYPE --> COLLECT_FIELDS: type resolved
    DISAMBIGUATE --> COLLECT_FIELDS: user picks
    COLLECT_FIELDS --> COLLECT_FIELDS: missing/invalid fields
    COLLECT_FIELDS --> RESOLVE_TARGET: all fields valid + preflight ok
    RESOLVE_TARGET --> RESOLVE_TARGET: need mode/device/conn
    RESOLVE_TARGET --> CONFIRM_APPROVAL: target resolved
    CONFIRM_APPROVAL --> DELIVER: user approves
    DELIVER --> DONE: render manual payload
    DONE --> [*]
```

**LLM calls in CONFIG (6 possible, all in `config_chain.py`, each Pydantic-parsed):**

| # | Function | When | Produces |
|---|---|---|---|
| 1 | `detect_type` | type not keyword-resolvable | `{route, config_type, confidence, candidates}` — also the **semantic gate** |
| 2 | `build_form` | first collection turn, forms on | form copy **+** extracted values (one combined call) |
| 3 | `extract_fields` | forms off / fallback / typed reply | field values dict |
| 4 | `preflight_validate` | after deterministic checks | validates values vs **playbook YAML**; fail-open; cached by signature |
| 5 | `extract_connection` | standalone/free-text target only | connection details |
| 6 | `phrase_question` | text-question paths only | cosmetic rewrite |

**Form mechanism (LLM-call reduction):**
- First turn: `build_form` = 1 call doing copy + extraction (vs 2). Form copy cached in `state.form_cache`.
- Subsequent form submissions arrive as structured `form_values` → merged with **zero LLM calls** (`_merge_and_validate`).

**Targeting (`_resolve_target`):**
- **Integrated** — picks device(s) from `config_inventory` MySQL table; credentials read securely (password never surfaced).
- **Standalone** — user supplies device_name/ansible_host/username/password (session-only).

**Playbook registry (`config_registry.py`):** parses `repositories/playbook-registry/<category>/*.yml` headers for `config_type`, required/optional fields, target group, risk (high if `ios_config` + `lines:`). `ENRICHMENT` map adds keywords/examples/validators. ~20 config types.

**Delivery (`_render_manual`):** **manual only in v1 — no Ansible executed.** Produces: `ansible-playbook` command (with extra-vars JSON), verbatim playbook YAML, sample `inventory.ini` line (no password). Idempotent via SHA-256 signature of (config_type, collected). Automated path is stubbed ("coming soon").

---

## 5. LLM Instances (`decision.py`)

All built by `create_llm_instance()` from env config (default ENV=`azure`; code fallback `MODEL=llama3.2:3b`, provider `ollama`, temp 0, top_p 0):

| Instance | Used by |
|---|---|
| `llm` | classify_intent, RAG, SEARCH, CONFIG chains, route_query, check_sufficiency |
| `openai_llm` | SQL, HYBRID (real OpenAI-compatible instance if provider is openai/azure/localai; else aliases `llm_chat`) |
| `sql_llm`, `llm_chat` | created but `sql_llm` unused; `llm_chat` only as `openai_llm` fallback |
| `embeddings` | RAG + memory (`nomic-embed-text:latest`) |

**Cache:** `set_llm_cache(InMemoryCache())` is **commented out** → no response/semantic/embedding cache active.

---

## 6. Memory & Storage (two distinct memory systems)

| System | Backend | Scope | Used for |
|---|---|---|---|
| **conversation_store** | In-memory dict, 2h TTL, last 8 turns | per session, per process | intent classification + CONFIG state + history injection via `with_history()` |
| **memory.py** | FAISS files `data/session_memory/<id>` | per session, on disk | semantic recall (`CONVERSTIONAL_MEMORY_PROMPT`); k=5; embeds with `OllamaEmbeddings(MODEL)` |
| **inventory** | MySQL | global | SQL/HYBRID device records |
| **config_inventory** | MySQL | global | CONFIG integrated targeting (seeded, idempotent) |
| **rag_index** | FAISS `data/rag_index/` | global | RAG knowledge base |
| **playbook-registry** | YAML files | global | CONFIG playbook contracts |


---

## 7. LLM Call Count Per Intent (cost view)

| Intent | LLM calls (typical) |
|---|---|
| Classification | 1 (every request) |
| SQL | +2 (gen SQL, format) |
| RAG | +1 |
| SEARCH | +1 |
| HYBRID | +2 (SQL gen, synthesis) |
| CONFIG | 1–6 across the multi-turn flow (forms minimize this) |
