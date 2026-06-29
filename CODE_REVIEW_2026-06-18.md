# 🔍 Code Review & Security Assessment — SmartShift AI

**Date:** 2026-06-18
**Scope:** Entire codebase — FastAPI backend (`app/`), React frontend (`ui/`), playbook registry (`repositories/`), tests, scripts, and configuration.
**Reviewer:** Code quality & security analysis
**Supersedes:** [`CODE_REVIEW.md`](CODE_REVIEW.md) (2026-05-05) — that review predates the CONFIG subsystem and does not cover the security issues below. It is retained for history.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope & Methodology](#2-scope--methodology)
3. [Architecture Overview](#3-architecture-overview)
4. [What Was Done Right (Strengths)](#4-what-was-done-right-strengths)
5. [Real Vulnerabilities](#5-real-vulnerabilities)
6. [Correctness Bugs](#6-correctness-bugs)
7. [What Can Be Improved (Code Quality)](#7-what-can-be-improved-code-quality)
8. [Limitations](#8-limitations)
9. [Advantages](#9-advantages)
10. [Prioritized Remediation Roadmap](#10-prioritized-remediation-roadmap)

---

## 1. Executive Summary

SmartShift AI is an ambitious full-stack RAG application. A FastAPI backend classifies each question into one of five intents — **SQL**, **RAG**, **HYBRID**, **SEARCH**, **CONFIG** — backed by a multi-provider LLM layer (Ollama / OpenAI / Azure / LocalAI / llama.cpp), a FAISS vector store, and a stateful **CONFIG** flow that converts natural language into vetted Ansible playbook commands with a human approval gate.

The engineering quality is **uneven but in places genuinely strong** — the CONFIG state machine is well-designed. However, the application's **security posture is prototype-grade**: there is no authentication on any endpoint, LLM-generated SQL is executed against a database superuser with no statement allowlist, and a live API secret is committed to source control.

### Overall Verdict

| Dimension | Rating | Notes |
|-----------|:------:|-------|
| Engineering / architecture | **7 / 10** | Clean intent routing; the CONFIG subsystem is excellent. Some dead/legacy code. |
| Security posture | **3 / 10** | No auth, committed secret, LLM→SQL as root, SSRF, path traversal, pickle RCE. |
| Production readiness | ❌ **Not ready** | Safe as a localhost demo; must not be network-exposed without the Critical fixes. |

> **Bottom line:** great prototype, strong CONFIG design, but do **not** deploy beyond a trusted local network until the Critical findings in §5 are fixed.

---

## 2. Scope & Methodology

Every source file outside of `venv/`, `node_modules/`, and the embedded model weights was read and analyzed. Findings were verified against actual line numbers, and the git history was checked for committed secrets (`git log -S`).

**Code size (excluding dependencies):**

| Layer | Notable files |
|-------|---------------|
| Backend core | [`app.py`](app/app.py) (364), [`decision.py`](app/decision.py) (366), [`router.py`](app/router.py), [`config.py`](app/config.py) |
| Chains | [`sql_chain.py`](app/chains/sql_chain.py), [`response_chain.py`](app/chains/response_chain.py), [`rag_chain.py`](app/chains/rag_chain.py), [`web_search.py`](app/chains/web_search.py), [`config_chain.py`](app/chains/config_chain.py) |
| CONFIG subsystem | [`services/config_service.py`](app/services/config_service.py) (836), [`config_registry.py`](app/config_registry.py) (443), [`config_inventory.py`](app/config_inventory.py) |
| Data / RAG | [`rag.py`](app/rag.py), [`memory.py`](app/memory.py), [`models.py`](app/models.py), [`admin.py`](app/admin.py) (591) |
| Frontend | [`ui/src/App.jsx`](ui/src/App.jsx), [`ui/src/components/AdminPanel.jsx`](ui/src/components/AdminPanel.jsx), [`ui/src/components/MessageBubble.jsx`](ui/src/components/MessageBubble.jsx) |
| Tests | [`tests/test_config_gate.py`](tests/test_config_gate.py) (227) |

---

## 3. Architecture Overview

```
                 React UI (Vite + react-markdown)
                        │  REST (fetch)
                        ▼
        FastAPI  ──  /api/v1/chat  (main entry)
                        │
             classify_intent(router.py)
        ┌──────┬────────┬────────┬─────────┬──────────┐
       SQL    RAG    HYBRID    SEARCH    CONFIG
        │      │        │        │          │
   sql_chain  rag    sql+rag  web_search  config_service
        │   (FAISS) (FAISS+SQL) (SerpAPI)  (state machine)
        ▼                                     │
   MySQL `inventory`              playbook-registry (YAML) ──► Ansible command
```

The primary, working endpoint is **`POST /api/v1/chat`** ([`app.py:181`](app/app.py#L181)). Two other chat endpoints exist (`/api/chat`, `/api/chat/upload`) and are legacy/partly broken (see §6).

---

## 4. What Was Done Right (Strengths)

| # | Strength | Evidence |
|---|----------|----------|
| 1 | **Clean intent architecture.** Router → per-intent chain separation is readable and easy to extend. | [`router.py:9-27`](app/router.py#L9-L27) |
| 2 | **The CONFIG state machine is excellent.** Semantic gate before type-mapping, deterministic-first then LLM fallback (a single keyword hit resolves with **zero** LLM calls), idempotency via content signatures, and a mandatory human approval gate. | [`config_service.py`](app/services/config_service.py); keyword fast-path [`:738-741`](app/services/config_service.py#L738-L741); signature [`:214-216`](app/services/config_service.py#L214-L216); approval gate [`:684-690`](app/services/config_service.py#L684-L690) |
| 3 | **Playbook-registry as single source of truth.** The field contract for each config type is parsed directly from vetted YAML headers — adding a type = dropping a file. | [`config_registry.py:295-322`](app/config_registry.py#L295-L322) |
| 4 | **Parameterized queries where it counts.** Config-inventory lookups and the SQL chain's value binding use bound params, not string interpolation. | [`config_inventory.py:107-112`](app/config_inventory.py#L107-L112), [`sql_chain.py:43`](app/chains/sql_chain.py#L43) |
| 5 | **Tests guard cost + behavior.** The CONFIG gate suite mocks the LLM and asserts exact call counts — a real regression guard against accidental cost blow-ups. | [`tests/test_config_gate.py`](tests/test_config_gate.py) |
| 6 | **XSS-safe rendering.** `ReactMarkdown` is used *without* `rehype-raw`, so model/DB output cannot inject HTML. The form display also redacts secrets. | [`MessageBubble.jsx:43`](ui/src/components/MessageBubble.jsx#L43), [`App.jsx:36-40`](ui/src/App.jsx#L36-L40) |
| 7 | **Resilience touches.** Embedding retry/backoff on HTTP 429; in-memory fallback when the inventory DB is down; a comprehensive `.gitignore` that successfully kept `.env` files out of git. | [`rag.py:21-40`](app/rag.py#L21-L40), [`config_inventory.py:114-118`](app/config_inventory.py#L114-L118) |
| 8 | **Pluggable provider abstraction.** One factory cleanly swaps five LLM providers. | [`decision.py:17-149`](app/decision.py#L17-L149) |
| 9 | **Secret-aware CONFIG design.** Secret fields are flagged in the registry and redacted in echoed state; the standalone connection password is explicitly excluded from the rendered inventory line. | [`config_service.py:238-249`](app/services/config_service.py#L238-L249), [`:154-163`](app/services/config_service.py#L154-L163) |

---

## 5. Real Vulnerabilities

Severity uses CVSS-style qualitative bands. "Exploitability" assumes the service is reachable on a network (CORS is already wide open).

| # | Severity | Title | Location |
|---|:--------:|-------|----------|
| V1 | 🔴 Critical | Hardcoded SerpAPI key committed to git | [`web_search.py:16`](app/chains/web_search.py#L16) |
| V2 | 🔴 Critical | Live Azure OpenAI key in active config file | [`app/.env.azure`](app/.env.azure) |
| V3 | 🔴 Critical | No authentication on any endpoint (incl. destructive admin) | [`app.py`](app/app.py), [`admin.py`](app/admin.py) |
| V4 | 🔴 Critical | LLM-generated SQL executed with no allowlist, as DB root | [`sql_chain.py:43`](app/chains/sql_chain.py#L43) |
| V5 | 🟠 High | SSRF via unauthenticated URL-ingest endpoint | [`admin.py:292-331`](app/admin.py#L292-L331) |
| V6 | 🟠 High | Path traversal via client-supplied `session_id` | [`memory.py:14-20`](app/memory.py#L14-L20) |
| V7 | 🟠 High | Pickle deserialization of FAISS index (RCE) | [`rag.py:95-97`](app/rag.py#L95-L97), [`memory.py:20`](app/memory.py#L20) |
| V8 | 🟠 High | TLS verification disabled by default on outbound calls | [`web_search.py:17-23`](app/chains/web_search.py#L17-L23) |
| V9 | 🟠 High | Internal error details leaked to clients | [`app.py:122`](app/app.py#L122), passim |
| V10 | 🟡 Medium | CONFIG secrets rendered into responses & chat history | [`config_service.py:147-152`](app/services/config_service.py#L147-L152) |
| V11 | 🟡 Medium | Sensitive data written to INFO logs | [`sql_chain.py:32`](app/chains/sql_chain.py#L32), [`app.py:77`](app/app.py#L77) |
| V12 | 🟡 Medium | Unbounded in-memory session store + no rate limiting (DoS) | [`conversation_store.py`](app/services/conversation_store.py) |
| V13 | 🟡 Medium | Unpinned dependencies (supply chain) | [`requirements.txt`](app/requirements.txt) |

---

### V1 — 🔴 Critical: Hardcoded SerpAPI key committed to git

[`web_search.py:16`](app/chains/web_search.py#L16) embeds a live SerpAPI key as a string literal:

```python
params = {"q": query, "api_key": '4e3379351b43635d0a2f402b14f3b0ba8c056b8664e2acc49449219bb6ea0cc9'}
```

**It is present in git history** (commit `b847d70`), so `.gitignore` cannot help — anyone with repo access (now or in the future) has the key.

**Impact:** Credential theft, quota abuse, billing fraud.
**Remediation:** Rotate the key immediately; load it from an environment variable; purge it from history (`git filter-repo` / BFG) and force-push after coordinating with the team.

---

### V2 — 🔴 Critical: Live Azure OpenAI key in the active config file

[`app/.env.azure`](app/.env.azure) contains a real `AZURE_OPENAI_API_KEY`, and [`config.py:8`](app/config.py#L8) defaults `ENV` to `azure` — so this is the **active** credential. It is correctly git-ignored (verified: not in history), but it is a real, billable key in plaintext on disk.

**Impact:** If the file is ever shared, backed up, or the host is compromised, the key is exposed.
**Remediation:** Rotate the key; inject via a secret manager / environment at runtime; never store production keys in repo-adjacent files.

---

### V3 — 🔴 Critical: No authentication on any endpoint

There is no auth anywhere in the application. The only reference to `HTTPBearer` is a *suggestion* in [`app/README.md:257`](app/README.md#L257) that was never implemented. Combined with wide-open CORS at [`app.py:41-46`](app/app.py#L41-L46) (`allow_origins=["*"]`), **anyone who can reach the server** can call destructive admin operations:

| Operation | Endpoint |
|-----------|----------|
| Import arbitrary CSV into MySQL | [`admin.py:496`](app/admin.py#L496) |
| Delete uploaded files | [`admin.py:363`](app/admin.py#L363) |
| Wipe & rebuild the vector index | [`admin.py:399`](app/admin.py#L399) |
| Enumerate DB tables / schemas | [`admin.py:546-581`](app/admin.py#L546-L581) |

**Impact:** Full data tampering, knowledge-base poisoning, denial of service, information disclosure.
**Remediation:** Add an auth dependency (API key or OAuth2/JWT) via `Depends(...)` on all routers; restrict CORS to known origins; segregate admin routes behind stronger auth/roles.

---

### V4 — 🔴 Critical: LLM-generated SQL executed with no allowlist, as DB root

[`sql_chain.py:43`](app/chains/sql_chain.py#L43) runs `pd.read_sql(query, engine, params=params)` where `query` is the **raw LLM output** ([`sql_chain.py:31-36`](app/chains/sql_chain.py#L31-L36)). Values are parameterized, but the **statement body itself is free-form** — nothing enforces that it is a single `SELECT`. The connection string is `root:root` ([`config.py:43`](app/config.py#L43)).

```python
sql_query = sql_response.content if hasattr(sql_response, 'content') else sql_response
sql_query = StrOutputParser().parse(sql_query)
query, params = format_sql_response(sql_query)   # query = whatever the model emitted
...
df = pd.read_sql(query, engine, params=params)   # executed as root
```

**Attack vector:** Prompt injection — directly, or **indirectly** via a poisoned RAG document or web-search result fed into the model — can steer it toward `UPDATE`/`DELETE`/`DROP`. Stacked statements are blocked by PyMySQL defaults, but a single destructive statement is not, and `root` can do anything.

**Remediation:**
1. Reject any query that is not a single `SELECT` (parse + validate before execution).
2. Run the query path under a **least-privilege, read-only** MySQL user.
3. Treat all retrieved documents/web content as untrusted in prompts.

---

### V5 — 🟠 High: SSRF via the URL-ingest endpoint

[`admin.py:292-331`](app/admin.py#L292-L331) (`/api/admin/upload-url`) is unauthenticated and fetches any `http(s)` URL with `WebBaseLoader(url)` ([`admin.py:119`](app/admin.py#L119)) — no host allowlist. The only check is the `http://`/`https://` scheme prefix.

**Impact:** Server-side request forgery against cloud metadata (`http://169.254.169.254/...`) or internal-only services, with the fetched content indexed and later retrievable via chat.
**Remediation:** Require auth; enforce an allowlist of permitted hosts; block link-local/private IP ranges and non-HTTP schemes; disable redirects to internal addresses.

---

### V6 — 🟠 High: Path traversal via `session_id`

[`memory.py:14-20`](app/memory.py#L14-L20) builds a filesystem path directly from the client-supplied `session_id` with no sanitization:

```python
def get_path(session_id):
    return f"{MEMORY_BASE_PATH}/{session_id}"      # session_id is attacker-controlled

def load_or_create(session_id):
    path = get_path(session_id)
    if os.path.exists(path):
        return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
```

A `session_id` like `../../some/dir` reads/writes outside the intended data directory.

**Impact:** Arbitrary file read/write within process permissions; combined with V7, a route to code execution.
**Remediation:** Validate `session_id` against a strict pattern (e.g. UUID/`^[A-Za-z0-9_-]{1,64}$`); reject path separators and `..`.

---

### V7 — 🟠 High: Pickle deserialization of the FAISS index (RCE)

Both [`rag.py:95-97`](app/rag.py#L95-L97) and [`memory.py:20`](app/memory.py#L20) load FAISS with `allow_dangerous_deserialization=True`, which unpickles `index.pkl`. A tampered or attacker-supplied index file = **arbitrary code execution**.

**Impact:** Remote code execution. Reachable when chained with V3 (unauth upload) + V6 (path control).
**Remediation:** Treat index files as trusted-only artifacts; store them outside any upload-writable directory; consider a non-pickle persistence format; verify integrity (checksum/signature) before load.

---

### V8 — 🟠 High: TLS verification disabled by default on outbound calls

[`web_search.py:17-23`](app/chains/web_search.py#L17-L23): `SERPAPI_VERIFY_SSL` defaults to `"false"`, so `requests.get(..., verify=False)` sends the API key over an unverified TLS channel and suppresses the warning.

**Impact:** Man-in-the-middle interception of the (already-leaked) API key and search traffic.
**Remediation:** Default `verify=True`; only allow disabling in explicit dev configs.

---

### V9 — 🟠 High: Internal error details leaked to clients

Numerous handlers return `detail=f"...{str(e)}"`, e.g. [`app.py:122`](app/app.py#L122), [`app.py:178`](app/app.py#L178), [`app.py:285`](app/app.py#L285), and most of [`admin.py`](app/admin.py). This surfaces DB errors, stack details, and file paths to the caller.

**Impact:** Information disclosure that aids further attacks.
**Remediation:** Return a generic message to clients; log the detail server-side only. The global handler at [`app.py:325-335`](app/app.py#L325-L335) already does this correctly — make all handlers follow that pattern.

---

### V10 — 🟡 Medium: CONFIG secrets rendered into responses & chat history

`_extra_vars` includes **all** collected fields ([`config_service.py:147-152`](app/services/config_service.py#L147-L152)), so secret fields such as `user_account.user_password` and `aaa.shared_key` land verbatim in the rendered `command`/`extra_vars` of the delivery payload ([`config_service.py:186-211`](app/services/config_service.py#L186-L211)) and are persisted to conversation history via `append_turn` ([`app.py:229-230`](app/app.py#L229-L230)). The redaction helper `_redact` ([`config_service.py:238-249`](app/services/config_service.py#L238-L249)) only covers the **echoed** `collected`, not the rendered command.

**Impact:** Plaintext secrets in API responses and in stored history. Partly intrinsic to "manual delivery," but still an exposure.
**Remediation:** Render secret extra-vars as placeholders with guidance to supply via Ansible Vault/prompt; never persist secret values to history.

---

### V11 — 🟡 Medium: Sensitive data written to INFO logs

Raw user questions, the generated SQL ([`sql_chain.py:32`](app/chains/sql_chain.py#L32)), and the first 100 characters of uploaded file content ([`app.py:77`](app/app.py#L77)) are logged at INFO.
**Remediation:** Redact/limit logged payloads; use DEBUG for verbose content; never log credentials or file contents in production.

---

### V12 — 🟡 Medium: Unbounded session store + no rate limiting (DoS)

[`conversation_store.py`](app/services/conversation_store.py) keeps sessions in a process dict with a TTL that is only enforced **lazily on access** — there is no global size cap and no background eviction. With no rate limiting anywhere, an attacker can spawn unbounded sessions / oversized histories.
**Remediation:** Add a max-session cap with LRU eviction; add request rate limiting (e.g. SlowAPI); cap history size.

---

### V13 — 🟡 Medium: Unpinned dependencies (supply chain)

[`requirements.txt`](app/requirements.txt) pins only `langchain-community==0.3.31`; everything else floats. Also, `torch` is imported at [`app.py:4`](app/app.py#L4) but is not declared.
**Remediation:** Pin all versions (hash-pinned ideally); declare every direct import; run `pip-audit`/Dependabot.

---

## 6. Correctness Bugs

These are functional defects (not security), each verified against the code.

| # | Bug | Location |
|---|-----|----------|
| B1 | **`/api/chat/upload` is partly broken.** Its `SEARCH_RAG`/`DIRECT_ANSWER`/`CLARIFY`/`REFUSE` branches return dicts (`{"query":...}` / `{"message":...}`) that don't satisfy `response_model=QueryResponse`, causing a 500 `ResponseValidationError`. Only `ANALYZE_FILE` returns a valid shape. | [`app.py:56`](app/app.py#L56), [`:92-114`](app/app.py#L92-L114) |
| B2 | **`/api/chat` (non-v1) is dead/placeholder.** The session path injects the literal string `"RAG context goes here"`; the no-session path retrieves RAG context then **discards** it (`formatted_prompt = request.question`). | [`app.py:147-159`](app/app.py#L147-L159) |
| B3 | **`replace_table` is silently ignored.** The endpoint accepts it but `import_to_mysql` hardcodes `if_exists='append'`. | [`admin.py:500`](app/admin.py#L500) vs [`admin.py:183`](app/admin.py#L183) |
| B4 | **Wasted LLM instances.** `llm`, `sql_llm`, `llm_chat` are three identical objects; `sql_llm` is never used (the SQL chain uses `openai_llm`). | [`decision.py:276-282`](app/decision.py#L276-L282) |
| B5 | **Deprecated global Torch default.** `torch.set_default_tensor_type(...)` is deprecated and forces a global CUDA default tensor type, which can break CPU-tensor libraries. | [`app.py:35`](app/app.py#L35) |
| B6 | **Deprecated startup hooks.** `@app.on_event("startup"/"shutdown")` should be the lifespan context manager in current FastAPI. | [`app.py:339`](app/app.py#L339), [`:352`](app/app.py#L352) |
| B7 | **Inconsistent embeddings.** `memory.py` hardcodes `OllamaEmbeddings(model=MODEL)` regardless of the configured provider — breaks when provider is Azure/OpenAI. | [`memory.py:7`](app/memory.py#L7) |
| B8 | **Dead code.** `final_chain_async` / `process_full_payload` batching path is unused; the final-analysis prompt is duplicated between [`util.py:263`](app/util.py#L263) and [`prompts.py:398`](app/prompts.py#L398). | [`response_chain.py:83`](app/chains/response_chain.py#L83) |

---

## 7. What Can Be Improved (Code Quality)

- **Centralize configuration.** `MYSQL_URI`, Qdrant host/port, and paths are hardcoded in [`config.py:29-43`](app/config.py#L29-L43) rather than read from the environment. (Note: `qdrant-client` is a dependency but the code actually uses FAISS — drop the unused dep or wire it up.)
- **Type hints & docstrings.** Coverage is partial across `app.py`, `util.py`, `router.py`. Public functions like `format_sql_response` would benefit from precise signatures.
- **Input validation.** `QueryRequest` allows arbitrary extra fields (`extra = "allow"`, [`models.py:20-21`](app/models.py#L20-L21)) and does not bound `question` length. Add `min_length`/`max_length` and a non-empty validator.
- **Async correctness.** Several LLM `.invoke(...)` calls run synchronously inside `async` endpoints (e.g. [`app.py:159`](app/app.py#L159)), blocking the event loop. Use `ainvoke`/`run_in_executor`. (Note: the SQL chain already uses `ainvoke` correctly.)
- **Consolidate prompts.** The duplicated final/HYBRID prompts should have one source of truth.

---

## 8. Limitations

- **Does not scale horizontally.** The session store is per-process in-memory and the app is pinned to `workers=1` ([`app.py:361`](app/app.py#L361)); the store's own docstring notes a shared backend (Redis/SQLite) is required for `workers > 1`.
- **Latency.** ~25-30s per response (per README), and there is **no streaming** despite the README claiming "real-time response streaming."
- **CONFIG is manual-delivery only.** Automated execution is intentionally stubbed and returns a "coming soon" notice. | [`config_service.py:404-410`](app/services/config_service.py#L404-L410) |
- **Thin test coverage.** Only the CONFIG gate is tested; SQL/RAG/HYBRID/admin paths have no tests.
- **Fragile data assumptions.** Dates are stored as text in `DD-MMM-YYYY` and require `STR_TO_DATE` everywhere ([`util.py:349`](app/util.py#L349)); the analysis is tightly coupled to one `inventory` schema.

---

## 9. Advantages

- **On-prem / local-LLM capable** (Ollama, llama.cpp, LocalAI) — data can stay in-house, valuable for regulated enterprise networking.
- **Pluggable provider abstraction** — one factory swaps five providers ([`decision.py:17-149`](app/decision.py#L17-L149)).
- **Human-in-the-loop safety** — explicit approval gate and risk flagging before any config change is delivered.
- **Cost-aware design** — deterministic keyword paths avoid LLM calls; LLM results are cached by content signature.
- **Extensible by configuration** — new config types are added by dropping a playbook YAML, no code change.
- **Good documentation** — extensive READMEs and CONFIG plan docs make the system approachable.

---

## 10. Prioritized Remediation Roadmap

### 🔴 Immediate (before any network exposure)
1. **Rotate both keys** (SerpAPI V1, Azure V2); move SerpAPI to env; purge from git history.
2. **Add authentication** + lock down CORS to known origins (V3).
3. **Enforce SELECT-only** SQL and run via a **least-privilege read-only DB user** (V4).

### 🟠 High (within one sprint)
4. **Sanitize `session_id`** (V6) and **add a host allowlist** to URL ingest (V5).
5. **Default TLS verification on** (V8).
6. **Stop returning `str(e)`** to clients (V9).
7. **Isolate FAISS index files** from upload-writable paths (V7).

### 🟡 Medium (within two sprints)
8. Redact secrets from CONFIG delivery payloads and history (V10); reduce sensitive logging (V11).
9. Add rate limiting + a session-store cap (V12); pin dependencies (V13).
10. Fix the broken/legacy chat endpoints — delete `/api/chat`, repair or remove `/api/chat/upload` (B1, B2).

### 🟢 Low (quality / hardening)
11. Remove dead code & duplicate prompts (B4, B8); migrate to FastAPI lifespan (B6).
12. Add tests for the SQL and admin paths; raise type-hint/docstring coverage.
13. Centralize configuration in environment variables; drop the unused Qdrant dependency.

---

*Generated as part of a full-codebase review on 2026-06-18. Code references are clickable and resolve relative to the repository root.*
