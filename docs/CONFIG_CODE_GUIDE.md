# CONFIG Intent — Code Navigation Guide

> A map for reviewers: what each file does, how a request flows end-to-end, and the
> non-obvious nuances worth knowing before reading the code. Pairs with
> [`CONFIG_INTENT_PROGRESS.md`](CONFIG_INTENT_PROGRESS.md) (what's built) and
> [`CONFIG_INTENT_TEST_PROMPTS.md`](CONFIG_INTENT_TEST_PROMPTS.md) (how to exercise it).
>
> Last updated: **2026-06-15**

---

## 1. The 30-second mental model

A chat request hits **one** endpoint (`/api/v1/chat`). It is **classified** into one of
five intents — `SQL`, `RAG`, `SEARCH`, `HYBRID`, or **`CONFIG`**. The first four answer
*questions*; **CONFIG makes a device configuration change**.

CONFIG is a **multi-turn state machine**: it figures out *what* to configure, asks for any
*missing parameters*, asks *where* to run it, gets *approval*, then hands back a **vetted
Ansible playbook + the command to run it** (manual mode — no device is touched in v1).

Everything CONFIG can do is **data-driven** by a playbook registry — adding a config type is a
YAML + playbook edit, not a code change.

---

## 2. Folder structure (annotated)

```
smartshift-ai/
├── app/                          # FastAPI backend
│   ├── app.py                    # ENTRY: /api/v1/chat — session, classify, dispatch
│   ├── router.py                 # classify_intent() → SQL|RAG|SEARCH|HYBRID|CONFIG
│   ├── prompts.py                # all LLM prompt templates (incl. CONFIG_* prompts)
│   ├── decision.py               # LLM factory (azure/openai/ollama…) → `llm`, `openai_llm`
│   ├── models.py                 # Pydantic models (incl. ConfigState/ConfigStage + extraction models)
│   ├── config.py                 # env/config + CONFIG_REQUIRE_APPROVAL, CONFIG_LLM_PHRASING
│   ├── util.py                   # SQL helpers + with_history() preamble
│   │
│   ├── config_registry.py        # ★ CONFIG: loads the playbook mapping + enrichment metadata
│   ├── config_inventory.py       # ★ CONFIG: MySQL config_inventory table (device picker source)
│   │
│   ├── chains/                   # one module per "how we answer"
│   │   ├── config_chain.py       # ★ CONFIG LLM calls: detect_type / extract_fields / extract_connection / phrase_question
│   │   ├── sql_chain.py          # NL → SQL → rows
│   │   ├── response_chain.py     # final answer formatting (SQL/HYBRID)
│   │   ├── rag_chain.py          # vector retrieval → answer
│   │   └── web_search.py         # SERP search → answer
│   │
│   └── services/
│       ├── conversation_store.py # ★ per-session history + CONFIG state (dict + TTL)
│       └── config_service.py     # ★★ THE CONFIG STATE MACHINE (the heart of the feature)
│
├── repositories/playbook-registry/   # ★ vetted Ansible playbooks, sorted by category
│   ├── required_fields.yaml      # THE INDEX: type → playbook, category, fields, risk, group
│   ├── management/   hostname, ssh_access, user_account, banner, save_config
│   ├── layer2/       vlan, interface (l2), port_channel
│   ├── layer3/       interface_ip (l3), static_route, ospf
│   ├── security/     acl, aaa
│   ├── services/     ntp, snmp, syslog
│   ├── redundancy/   hsrp, vrrp
│   └── segmentation/ vrf
│
├── ui/                           # React chat UI (App.jsx holds session_id for chaining)
└── docs/                         # CONFIG_INTENT_{PLAN,PROGRESS,TEST_PROMPTS}.md + this guide
```

★ = added/changed for the CONFIG feature.   ★★ = start here when reviewing.

---

## 3. Request lifecycle (end-to-end)

```
UI (App.jsx)
  │  POST /api/v1/chat { question, session_id }
  ▼
app.py: askv1_question()
  │  1. session_id = request.session_id or new uuid
  │  2. history_str = conversation_store.format_recent(session_id)   # truncated transcript
  │  3. if a CONFIG flow is mid-progress → tool = "CONFIG" (skip re-classify)
  │     else → tool = classify_intent(question, history_str)         # router.py + LLM
  ▼
 ┌── CONFIG ────────────────────────────────────────────────┐   ┌── SQL/RAG/SEARCH/HYBRID ──┐
 │ config_service.handle(question, session_id)               │   │ <chain>(question, history)│
 │   → returns a rich payload (answer + stage + …)           │   │   with_history(...) into  │
 │ conversation_store.append_turn(user / assistant)          │   │   the prompt              │
 └───────────────────────────────────────────────────────────┘   └───────────────────────────┘
  │
  ▼  JSONResponse  (answer is the human-readable text the UI renders as markdown)
```

The UI only reads `answer`, so **`answer` is always self-contained** (questions, summary, or the
rendered playbook in code fences). The extra fields (`stage`, `collected`, `config_type`,
`delivery_mode`, …) are additive for future UI use.

---

## 4. The CONFIG state machine (`services/config_service.py`)

This is the file to read first. `ConfigService.handle(message, session_id)` runs once per turn:

```
DONE re-entry (idempotent re-send?) → attempts++ / cancel / cap
  → DETECT_TYPE     keyword first (free), else LLM fallback, else DISAMBIGUATE
  → COLLECT_FIELDS  extract → validate → merge (cumulative); ask for ALL missing at once
  → RESOLVE_TARGET  Integrated (device picker) | Standalone (connection details)
  → CONFIRM_APPROVAL full gate; edits re-open it; only "approve" proceeds
  → DELIVER         manual: vetted playbook + ansible command (+ automated stub)
  → DONE            cache result for idempotency
```

The stages are a `ConfigStage` enum on `ConfigState` (in `models.py`); state persists between
turns in `conversation_store`.

**Reading order inside the file:** `handle()` (top-level flow) → the message composers
(`_collect_message`, `_approval_summary`, `_delivery_message`) → the helpers (`_detect`,
`_resolve_choice`, `_resolve_target`, `_render_manual`).

---

## 5. The registry (`config_registry.py` + `repositories/playbook-registry/`)

Two layers are merged here — **know which is which**:

| Layer | Lives in | Owns |
|---|---|---|
| **Playbook contract** | `required_fields.yaml` | playbook path, `category`, `target_group`, `required_fields`, `optional_fields`, `risk` |
| **Refinement metadata** | `ENRICHMENT` dict in `config_registry.py` | per-type `keywords`, a disambiguation `example`, per-field `prompt`/`example`/`validate`/`secret` |

`ConfigRegistry` loads + merges them into a `ConfigTypeSpec` per type. Key methods the service
calls: `get(type)`, `match_keywords(text)`, `examples(n)`, `all()`.

> **To add a config type:** drop a playbook in the right `category/` folder, add an entry to
> `required_fields.yaml`, and (optionally) a keywords/fields block in `ENRICHMENT`. No
> state-machine code changes.

---

## 6. Code nuances (the non-obvious bits reviewers ask about)

1. **Plan vs. registry field names.** The original plan (`CONFIG_INTENT_PLAN.md`) used names like
   `INTERFACE_IP(interface, ip, subnet)`. **The registry won** — real types are `interface_l3`
   with `interface_name, ip_address, subnet_mask`, etc. The registry is the single source of truth.

2. **"Rendering" = the vetted YAML + an `-e` command, not LLM-generated YAML.** Every playbook
   consumes its `required_fields` as Ansible extra-vars, so manual delivery returns the playbook
   *unchanged* plus `ansible-playbook -i inventory.ini <category>/<file>.yml -e '{json}'`.
   Deterministic, no invented config.

3. **Playbook path resolution is subdir-aware with a fallback.** `config_registry` joins the
   `playbooks/<category>/<file>` path under the registry dir; if that misses, it **recursively
   searches by basename** (`_find_playbook`) so a path/folder drift won't break loading.
   `spec.playbook_rel` (e.g. `security/aaa.yml`) is what the rendered command uses.

4. **Two LLM confidence bands in detection** (`_detect`): keyword collision needs conf ≥ 0.8 to
   auto-resolve; a no-keyword hit needs conf ≥ 0.6; otherwise → DISAMBIGUATE with candidates.
   A disambiguation reply resolves by number / ordinal / type name / keyword (`_resolve_choice`).

5. **Field extraction is gated by stage.** While `RESOLVE_TARGET` is active, a reply is a
   mode/device/connection answer — **not** a config field — so field extraction is skipped that
   turn (prevents "integrated" being parsed as a field). Edits at the approval gate *do* re-extract.

6. **Secrets.** Inventory/standalone **connection passwords never leave the server**
   (`InventoryDevice.public()` strips them; summaries/echo redact). BUT field-level secrets the
   playbook needs as variables (`user_account.user_password`, `aaa.shared_key`) **do** appear in
   the final runnable `-e` command — by necessity, so the user can run it. Marked `secret` only
   redacts them in the *summary/echo*. (AAA's own note says use a vault in production.)

7. **Idempotency.** A signature of `config_type + collected` is stored; a duplicate `approve`
   or identical request returns the cached result instead of re-delivering.

8. **`attempts` cap resets on progress.** The give-up counter (`MAX_ATTEMPTS=8`) resets whenever
   the type resolves or a new slot fills, so a legit multi-field flow can't trip it — only a
   genuinely stuck conversation does.

9. **Chaining reuses one store.** `conversation_store` records every turn for every intent
   (not a separate `IntentHistoryService`). `with_history()` (in `util.py`) prepends a
   **truncated** transcript (500 chars/turn, last 8 turns) into SQL/RAG/SEARCH/HYBRID prompts —
   applied *after* template formatting so it never collides with `{placeholders}`.

10. **Session store is in-process (dict + 2h TTL).** Fine for `workers=1`; needs Redis/SQLite
    before scaling out. The UI must persist + resend `session_id` (it does) or chaining breaks.

11. **`config_inventory` is a real MySQL table**, seeded with dummy data on startup
    (`ensure_schema_and_seed`), in the same DB as the SQL `inventory` table. Falls back to an
    in-memory copy if the DB is down so the picker still works in a demo.

---

## 7. "Where do I look for…?" cheat-sheet

| I want to… | Go to |
|---|---|
| See the whole CONFIG turn logic | `services/config_service.py` → `handle()` |
| Add/change a config type's fields or risk | `repositories/playbook-registry/required_fields.yaml` |
| Change a follow-up question's wording | `ENRICHMENT` in `config_registry.py` (field `prompt`) |
| Change detection keywords | `ENRICHMENT` in `config_registry.py` (type `keywords`) |
| Tune detection thresholds / give-up cap | constants atop `services/config_service.py` |
| See/seed the device inventory | `config_inventory.py` |
| Find the LLM prompts | `prompts.py` (CONFIG_* near the bottom) |
| See how intents are routed | `router.py` + `INTENT_CLASSIFIER_PROMPT` in `prompts.py` |
| See how history is injected | `util.with_history` + `conversation_store.format_recent` |
| Trace the API entrypoint | `app.py` → `askv1_question()` |
| Toggle approval / LLM phrasing | `config.py` (`CONFIG_REQUIRE_APPROVAL`, `CONFIG_LLM_PHRASING`) |

---

## 8. Quick run (for a live demo in the meeting)

```powershell
# backend (from smartshift-ai/)
.\venv\Scripts\Activate.ps1
python -m app.app                 # http://localhost:8000 ; auto-seeds config_inventory

# UI (from smartshift-ai/ui/)
npm run dev
```

Then walk the **F. Quick smoke sequence** in `CONFIG_INTENT_TEST_PROMPTS.md` — it hits keyword
detection, slot-filling, disambiguation, standalone target, amendment, and delivery in one go.
