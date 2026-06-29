# CONFIG Intent — Design & Implementation Plan

> Status: **Proposal / Plan only — no code changes made.**
> Author: AI assistant • Date: 2026-06-09
> Scope: Add a new `CONFIG` intent to the Smart-AI-Migration assistant: detect
> config type from the query, iteratively collect required fields via dynamic
> follow-up questions, gate on approval, **render a vetted reference playbook** with
> the collected values, and (v1) **return the script for the user to run** — with an
> automated "system applies it" path kept open for the future.
>
> This revision folds in the final refinements agreed before execution. See §2.

---

## 1. Objective

Enable the assistant to:

1. Understand configuration-related queries (Hostname, VLAN, Interface IP, Static
   Route, SSH, …).
2. Iteratively refine intent through follow-up questions (asking for **all
   outstanding fields together**) until every required field is collected.
3. Select the correct **vetted reference playbook** and render it with the
   collected values (no from-scratch generation — §scope guardrails).
4. Require explicit **approval** before delivering/applying (full gate — §7).
5. **Deliver the rendered playbook for the user to run (Manual — v1)**, or apply it
   automatically (Automated — future). §10.1

Plus the cross-cutting behaviours requested by the product owner:

| # | Requirement | Where it lands |
|---|-------------|----------------|
| 1 | Request–response **chaining** (remember previous chat for follow-ups) | §5 (CONFIG) + §5.1 (other four intents, done last) |
| 2 | **Approval** mechanism for CONFIG + report missing fields | §7 Approval + §6 Slot filling |
| 3 | If LLM is **short of context** → ask for short example prompts and **reconfirm** | §6/§8 `DISAMBIGUATE` stage |
| 4 | If LLM needs **2 answers but user gave 1** → ask for the remainder before proceeding | §6 Slot filling (cumulative state) |

### Scope guardrails
- **Work from vetted reference playbooks, not from scratch.** The system selects a
  vetted template from the playbook registry (§9) and fills it with the collected
  variables. The model **parameterises** the reference template — it must not invent
  new directives or unrelated config. Templates are sent **directly to the LLM as
  reference today**; in production they will be served from **RAG** (§9, decision M).
- **Config types are dynamic.** Which types exist is driven entirely by the registry
  + mapping; adding a type = add a template + a mapping entry, no code change (§9).
- Only **predefined** fields per type; **no hardcoded assumptions** — fields are read
  from the mapping (derived from the template's variables) at runtime.
- **No hardcoded question flows** — questions are derived dynamically from the
  missing fields' metadata.
- Support **multi-turn** interaction and be **idempotent** across steps (§15).
- **Connection details are resolved separately from config fields** — the user
  **chooses** integrated (device from the `config_inventory` table) or standalone
  (user-supplied) at runtime. §10.2

---

## 2. Design Decisions (resolved)

| # | Topic | **Decision** | Notes |
|---|-------|--------------|-------|
| A | Config-type detection | **Keyword mapping first, then LLM + confidence** | Deterministic keyword pass; LLM (`PydanticOutputParser`) fallback with confidence when keywords miss/clash. §8 |
| B | Follow-up cadence | **Consolidated — ask for all missing fields together** | One message lists every outstanding field. §6 |
| C | Question wording | **Dynamically derived, no hardcoding** | Built from each field's metadata in the mapping. §6, §9 |
| D | State model | **`collected{}` + `stage` enum** | Slot dict `collected`, lifecycle tracked by a `stage` enum. §6 |
| E | Response contract | **`answer` / `stage` / … + `ExecutionResult` / rendered playbook** | §11 |
| F | Approval step | **Full gate (mandatory)** | Delivery/execution always blocked until the user approves. §7 |
| G | Ambiguous / low-context | **Dedicated `DISAMBIGUATE` stage** | Offers example prompts + asks to reconfirm (req #3). §6, §8 |
| H | Mapping form | **Data mapping including `keywords`** | `config_type → {keywords, required_fields, template, …}`. §9 |
| I | Idempotency | **Explicit requirement** | Re-sending the same turn does not double-apply. §15 |
| J | Target / credentials | **Two modes; user chooses at runtime** | *Integrated:* device + creds from the new **`config_inventory`** table. *Standalone:* prompt the user for device/IP/user/pass. §10.2 |
| K | Execution status | **Keep `partial`** (automated mode) | `ExecutionResult.status ∈ {success, failed, partial}`. §10.3/§11 |
| **L** | **Post-approval mode** | **Manual (v1) vs Automated (future)** | **Manual** = render + return the playbook script for the user to run. **Automated** = system runs it. v1 builds Manual only; Automated is stubbed/kept open. §10.1 |
| **M** | **Playbook sourcing** | **Vetted reference templates in the repo registry** | Stored under `playbooks/`; sent **directly to the LLM** now; **RAG-served** in production. §9 |
| **N** | **Approver** | **Session user is enough** | No special role/RBAC required for v1. §7 |

---

## 3. Current Architecture (As-Is)

```
POST /api/v1/chat  (app/app.py: askv1_question)
        │
        ▼
classify_intent(question)        app/router.py  → INTENT_CLASSIFIER_PROMPT (app/prompts.py)
        │   returns one word: SQL | RAG | HYBRID | SEARCH
        ▼
   ┌─────────────┬───────────────┬───────────────┐
  SQL          HYBRID          SEARCH           (CONFIG ← does not exist yet)
   │             │               │
 sql_chain   sql_chain        web_search_chain
   │         + final_chain
final_structured_chain
   │
   ▼
 JSONResponse { answer, session_id, timestamp, sources, follow_up_questions }
```

**Key facts that shape the design:**

- `classify_intent()` returns a **bare string**, dispatched by `tool.strip()` in
  [`app/app.py`](../app/app.py) (`/api/v1/chat`). The hook comment
  *"We have to add one more intent here - Config"* already exists at `app/app.py:221`.
- Each request is **stateless** today on `/api/v1/chat`; `session_id` is echoed back
  but never used to load history.
- `chat_sessions: dict` exists in [`app/models.py`](../app/models.py) but is **unused**.
- FAISS memory (`app/memory.py`) is wired **only** into legacy `/api/chat`, and is
  *semantic recall*, not a turn-ordered transcript or slot store.
- LLM access is centralized via `llm` / `openai_llm` in [`app/decision.py`](../app/decision.py).
- Existing **MySQL `inventory` table** holds the device data used by the SQL/HYBRID
  flows (we will add a **separate `config_inventory` table** for CONFIG — §10.2).
- Structured decisions already use `PydanticOutputParser` (`RoutingDecision`, …).
- **No Ansible assets exist** in the repo.

### Gaps to close
1. No CONFIG intent / branch.
2. No durable per-session conversation state (chaining).
3. No slot-filling / required-field tracking.
4. No approval gate.
5. No low-confidence "ask for examples & reconfirm" path.
6. No playbook registry, rendering, or delivery/execution layer.
7. No chaining for the existing four intents (added last — §5.1).

---

## 4. Target Architecture (To-Be)

```
POST /api/v1/chat
   │
   ▼
SessionStore.load(session_id)         ← NEW: history + pending CONFIG state
   │
   ├─ If a CONFIG conversation is in progress → resume ConfigService
   │
   ▼
classify_intent(question, history)    ← history added for chaining (req #1)
   │   SQL | HYBRID | SEARCH | CONFIG
   ▼
 ┌────────── CONFIG ──────────────────────────────────────────────┐
 │ ConfigService.handle(message, state)                            │
 │   1. Detect config_type: keyword → else LLM + confidence        │
 │        low conf / ambiguous → DISAMBIGUATE (req #3)             │
 │   2. Load required_fields from mapping (dynamic, from template) │
 │   3. Extract provided fields from message + history (req #4)    │
 │   4. Missing fields? → COLLECT_FIELDS: ask for ALL missing      │
 │   4b. Resolve target (user picks Integrated/Standalone) §10.2  │
 │   5. All present & not approved → CONFIRM_APPROVAL (req #2)     │
 │   6. Approved → RENDER vetted template with collected values    │
 │        • Manual (v1): return the playbook script  ──────────┐   │
 │        • Automated (future): ansible_runner.run(...)        │   │
 │   Persist state every turn (req #1, idempotent)             │   │
 └─────────────────────────────────────────────────────────────┼───┘
   │                                                            │
   ▼                                                            ▼
SessionStore.save(...)                              rendered playbook / result
```

SQL / HYBRID / SEARCH keep their current chains for now; a **separate chaining util
service** is added for them **last** (§5.1).

---

## 5. Conversation State Store — CONFIG (Requirement #1 — Chaining)

A store holds, per `session_id`, the **chat transcript** and any **in-progress
CONFIG state**. This is the **CONFIG-specific** chaining; the other four intents get
their own util service (§5.1) so the two concerns stay decoupled.

```python
# app/services/conversation_store.py  (sketch)

class ConversationState(BaseModel):
    session_id: str
    history: list[ChatMessage] = []               # ordered turns (reuse ChatMessage)
    config_state: Optional[ConfigState] = None    # set only mid-CONFIG flow
    updated_at: datetime

class ConversationStore:
    def load(self, session_id) -> ConversationState: ...
    def append_turn(self, session_id, role, content) -> None: ...
    def set_config_state(self, session_id, state) -> None: ...
    def clear_config_state(self, session_id) -> None: ...
```

- **Phase 0 (MVP):** in-process `dict` — formalize the existing `chat_sessions` dict
  with a TTL.
- **Production:** swap to a shared backend (Redis/SQLite) behind the same interface.
  Backend choice is **open** — this is a prototype, decided at production time (§17).
- The last N turns feed `classify_intent` and every CONFIG LLM call so follow-ups
  ("make it VLAN 30 instead") resolve against context. Distinct from FAISS
  (`app/memory.py`), which we keep for RAG.

### 5.1 Chaining for the other four intents (SQL / RAG / SEARCH / HYBRID) — **done last**

- The four existing intents will get their **own separate chaining util service**
  (e.g. `app/services/intent_history.py`), independent of the CONFIG store above.
- Rationale: CONFIG chaining carries slot-filling/approval *state*; the other four
  only need a lightweight rolling transcript injected into their prompts. Keeping
  them separate avoids coupling the simple case to the stateful one.
- Sketch: an `IntentHistoryService` that records `(session_id, role, content)` and
  exposes `recent(session_id, n)` to prepend prior turns into the SQL/RAG/SEARCH/
  HYBRID prompts.
- **Sequencing:** implemented **after** the CONFIG feature is complete (final phase,
  §14). Listed here only so the design is visible.

---

## 6. ConfigService — The State Machine

### Stages (`stage` enum — decision D)
```
DETECT_TYPE → COLLECT_FIELDS → RESOLVE_TARGET → CONFIRM_APPROVAL → DELIVER → DONE
                   ↑   ↓
              (re-ask remaining missing fields)
   (any stage) → DISAMBIGUATE (low confidence) → back to DETECT_TYPE
```

### `ConfigState` (persisted between turns)
```python
class ConfigState(BaseModel):
    config_type: Optional[str] = None             # HOSTNAME | VLAN | ... (None until detected)
    collected: dict[str, Any] = {}                # field → value (cumulative)
    missing_fields: list[str] = []
    stage: ConfigStage = ConfigStage.DETECT_TYPE
    target_mode: Optional[str] = None             # "integrated" | "standalone" (user choice §10.2)
    target_device: Optional[dict] = None          # resolved device/connection ref
    delivery_mode: str = "manual"                 # "manual" (v1) | "automated" (future) §10.1
    approved: bool = False
    attempts: int = 0
    last_executed_signature: Optional[str] = None # idempotency key (§15)
```

### Per-turn algorithm (`ConfigService.handle`)
```
1. If config_type is None:
     a. KEYWORD match against mapping[*].keywords → exactly one hit → set type.
     b. zero/multiple hits → LLM fallback (config_chain.detect_type) →
        {config_type, confidence, candidates[]}.
     c. low confidence / multiple candidates → stage = DISAMBIGUATE (req #3).
     d. resolved → load required_fields from mapping.

2. required_fields = mapping[config_type].required_fields      ← DYNAMIC (from template vars)

3. Extract provided fields (config_chain.extract_fields); merge into collected
   (new overrides; prior never dropped — req #4).

4. missing_fields = [f for f in required_fields if f not in collected or invalid(f)]
   If missing_fields:
        stage = COLLECT_FIELDS → ask ONE message listing ALL outstanding fields,
        dynamically worded from field metadata. save; return.   (req #4, consolidated)

4b. RESOLVE_TARGET (see §10.2):
        - If target_mode is None → ask the user to choose Integrated or Standalone.
        - Integrated  → user selects a device from config_inventory; store ref.
        - Standalone  → device/ip/username/password collected as fields (step 4).

5. If all fields + target resolved and not approved:
        stage = CONFIRM_APPROVAL → render summary (type + fields + target +
        chosen delivery mode + which template) → "Reply 'approve' to proceed."
        save; return.                                           (req #2, full gate)

6. If approved:
        stage = DELIVER
        rendered = render_playbook(mapping[config_type].template, collected)  (§10.0)
        if delivery_mode == "manual":      # v1
            return rendered playbook script for the user to run (§11)
        else:                              # automated (future)
            result = ansible_runner.run(rendered, target_device)  (idempotent §15)
            return ExecutionResult
        clear_config_state(session_id); stage = DONE
```

**Req #4 (asked 2, got 1):** `collected` is cumulative and `missing_fields` is
recomputed every turn — a partial answer just fills one slot; the next turn re-lists
only what remains. No field is lost.

**Dynamic questions (no hardcoded flows):** the COLLECT_FIELDS message is assembled
from each missing field's mapping metadata (`prompt`/`description`/`example`),
optionally polished by the LLM.

**Approval parsing (while `stage == CONFIRM_APPROVAL`):** "approve"/"yes" →
`approved = True`; field-like content → merge + re-summarize (stay); "cancel" →
clear state. `attempts` cap (~8) → graceful restart.

---

## 7. Approval Mechanism (Requirement #2 — full gate)

- Approval is a **mandatory gate**: delivery/execution is **always blocked** until
  `approved` is `True` (decision F). `CONFIG_REQUIRE_APPROVAL` (in `app/config.py`)
  defaults to and stays `True`.
- **Approver:** the **session user is enough** — no special role/RBAC for v1
  (decision N).
- The approval summary is explicit and also states the **delivery mode**:

  ```
  Ready to prepare a VLAN configuration:
    • config_type   : VLAN
    • vlan_id        : 30
    • vlan_name      : FINANCE
    • ports          : Gi1/0/1-2
    • target device  : core-sw-01  (integrated / config_inventory)
    • template       : playbooks/vlan.yml
    • delivery       : MANUAL → I'll return the playbook for you to run
  Reply "approve" to proceed, or tell me what to change.
  ```
- The user never reaches approval with an incomplete set — fields and target are
  resolved first.

---

## 8. Config-Type Detection (keyword-first, then LLM + confidence)

1. **Keyword pass (primary):** match the message against each type's `keywords` in
   the mapping. Exactly one hit → resolved deterministically (no LLM cost).
2. **LLM fallback (secondary):** zero/multiple hits → `config_chain.detect_type`
   (`{config_type, confidence, candidates[]}`).
3. **DISAMBIGUATE (req #3):** unresolved / low confidence / multiple candidates →
   state what was understood, offer **2-3 example prompts drawn from the mapping**,
   ask the user to **reconfirm**:

   ```
   I think you want a network configuration change, but I'm not sure which.
   Did you mean something like:
     1. "Set the hostname on R1"
     2. "Create VLAN 30 named FINANCE and assign Gi1/0/1-2"
     3. "Add a static route to 10.10.10.0/24 via 192.168.1.254"
   Please pick one or rephrase.
   ```
   Examples come from the mapping, so they only advertise capabilities that exist.

---

## 9. Playbook Registry & Mapping (vetted reference templates — decisions H, M)

**Where playbooks live:** vetted templates live **in the repo** under a registry
directory (e.g. `playbooks/`). For now (small number) they are **sent directly to
the LLM as reference**; in production they will be **loaded into RAG** and retrieved
by config type (decision M).

**Config types are dynamic** — driven by the mapping + registry. v1 starts with
these **5 vetted use cases** (each is a reference template + its variables):

| config_type | hosts | template variables (→ required_fields) |
|-------------|-------|----------------------------------------|
| `HOSTNAME` | routers | `hostname` |
| `VLAN` | switches | `vlan_id`, `vlan_name`, `ports` |
| `INTERFACE_IP` | routers | `interface`, `ip`, `subnet` |
| `STATIC_ROUTE` | routers | `destination`, `mask`, `next_hop` |
| `SSH` | routers | `domain_name` (+ fixed hardening lines from the template) |

```jsonc
// config_map.json  (or an equivalent Python dict)  — required_fields derive from template vars
{
  "HOSTNAME": {
    "keywords": ["hostname", "device name", "rename"],
    "required_fields": ["hostname"],
    "template": "playbooks/hostname.yml",
    "fields": { "hostname": { "prompt": "What hostname should the device have?" } },
    "example": "Set the hostname on R1 to CORE-RTR-01"
  },
  "VLAN": {
    "keywords": ["vlan", "trunk", "access port"],
    "required_fields": ["vlan_id", "vlan_name", "ports"],
    "template": "playbooks/vlan.yml",
    "fields": {
      "vlan_id":   { "prompt": "Which VLAN ID (1-4094)?", "validate": "vlan_id" },
      "vlan_name": { "prompt": "What name should the VLAN have?" },
      "ports":     { "prompt": "Which interfaces/ports should be assigned?" }
    },
    "example": "Create VLAN 20 named SERVERS and assign Gi1/0/1-2"
  },
  "INTERFACE_IP": {
    "keywords": ["interface ip", "ip address", "configure interface"],
    "required_fields": ["interface", "ip", "subnet"],
    "template": "playbooks/interface_ip.yml",
    "example": "Configure Gi0/0 with 192.168.1.1 255.255.255.0"
  },
  "STATIC_ROUTE": {
    "keywords": ["static route", "ip route", "next hop"],
    "required_fields": ["destination", "mask", "next_hop"],
    "template": "playbooks/static_route.yml",
    "example": "Add static route 10.10.10.0/24 via 192.168.1.254"
  },
  "SSH": {
    "keywords": ["ssh", "secure management", "vty"],
    "required_fields": ["domain_name"],
    "template": "playbooks/ssh.yml",
    "example": "Enable SSH with domain lab.local"
  }
}
```

- The mapping is the **single source of truth**: `keywords`, `required_fields`
  (derived from the template's variables), the template path, optional per-field
  prompts/validators, and a disambiguation example.
- Adding a new type = add a template + mapping entry. **No code path generates YAML
  from scratch** — the LLM only parameterises the chosen vetted template.
- **Platform (Nexus 2900 vs 9300, NX-OS vs IOS):** whether a type needs different
  templates per platform is **still undecided** — see §17.

---

## 10. Rendering, Delivery & Execution

### 10.0 Rendering the playbook
`render_playbook(template, collected)` produces the final playbook by substituting
the collected values into the **vetted reference template**:
- **Now:** the template is sent to the LLM as reference along with the collected
  variables; the LLM returns the finalised playbook, **constrained to the template**
  (fill variables only — no invented directives). Output is validated against the
  template's variable set.
- **Production:** the reference template is retrieved from **RAG** instead of being
  hard-shipped to the LLM (decision M).
- A pure-Jinja2/extra-vars substitution path (no LLM) can replace this later for
  determinism if desired.

### 10.1 Execution mode — Manual (v1) vs Automated (future) — decision L
| Mode | What happens after approval | Status |
|------|-----------------------------|--------|
| **Manual** | Render the template with the collected values and **return the playbook script** to the user, who runs it themselves (optionally with a sample inventory line for the chosen device). **No device connection is made.** | **v1 — build this** |
| **Automated** | Render, then the system runs `ansible-playbook` against the resolved target and returns an `ExecutionResult`. | **Future — keep open** (stub the branch + a "not available yet" response) |

The user picks the mode (default `manual`); the automated branch is wired but
returns a "coming soon" response in v1.

### 10.2 Target & Connection Resolution (two modes; **user chooses** — decision J)
| Mode | When | Target / connection source | Credentials |
|------|------|----------------------------|-------------|
| **Integrated** | Tool runs **inside** the network | User **selects a device** from the new **`config_inventory`** table; IP/user/pass read from that row | Never prompted |
| **Standalone** | Tool runs **apart from** the network | Assistant **asks** for device, IP, username, password (extra fields in §6 step 4) | Collected from user (transient) |

- **The user is asked to choose** the mode at runtime (`target_mode`); there is no
  fixed default (decision J).
- **`config_inventory` table (NEW):** separate from the existing SQL `inventory`
  table. Suggested columns: `device_name`/`hostname`, `platform`/`os` (e.g.
  ios/nxos), `ansible_host` (IP), `username`, `password` (or a vault/secret ref),
  `group`. **Dummy data now; populated with real data in production.**
- Ansible needs an inventory at run time (automated mode only): we **generate a
  transient inventory from `config_inventory`** rather than maintaining a static
  `inventory.yaml`. (A DB table is preferred over a static `inventory.yaml` for a
  web app — queryable, drives a device-picker, easy to populate; the YAML is just a
  derived artifact.) In **manual** mode no connection happens, so creds are not used.
- Standalone connection fields are **not** persisted beyond the session and kept out
  of logs. The approval summary shows the device but **never** the password.

### 10.3 Ansible runner (Automated mode — future)
```python
# app/services/ansible_runner.py  (sketch — future/automated path)
def run(rendered_playbook, target, inventory) -> ExecutionResult:
    # 1. Path/whitelist guards on the rendered playbook.
    # 2. Build a transient inventory from config_inventory (integrated) or
    #    user-supplied vars (standalone).
    # 3. subprocess: ansible-playbook -i <inv> <pb> --extra-vars <json> [--check]
    # 4. Parse PLAY RECAP → ExecutionResult.
```
```python
class ExecutionResult(BaseModel):
    config_type: str
    template: str
    status: Literal["success", "failed", "partial"]   # decision K
    changed: bool
    summary: str
    raw_recap: Optional[str] = None
    applied_fields: dict
```
- `--check` (dry-run) **only applies to this automated path** — it simulates the run
  with no changes. Not relevant to v1/manual; revisit when Automated is built (§17).
- `extra_vars` passed as JSON (not shell-interpolated); runs via `asyncio.to_thread`.

---

## 11. Response Format (decision E)

`/api/v1/chat` returns a rich object; CONFIG fields are additive/backward-compatible.

### In-flow (DISAMBIGUATE / COLLECT_FIELDS / RESOLVE_TARGET / CONFIRM_APPROVAL)
```json
{
  "answer": "I still need the VLAN ID and the ports to assign.",
  "session_id": "abc-123",
  "intent": "CONFIG",
  "stage": "COLLECT_FIELDS",
  "config_type": "VLAN",
  "collected": { "vlan_name": "SERVERS" },
  "missing_fields": ["vlan_id", "ports"],
  "awaiting": "user_input",          // user_input | choose_target_mode | approval | none
  "timestamp": "..."
}
```

### Manual delivery (v1) — returns the rendered playbook
```json
{
  "answer": "Here is the VLAN playbook. Run it against your inventory.",
  "session_id": "abc-123",
  "intent": "CONFIG",
  "stage": "DONE",
  "config_type": "VLAN",
  "delivery_mode": "manual",
  "playbook": "playbooks/vlan.yml",
  "rendered_playbook": "- name: Configure VLAN\n  hosts: switches\n  ...",
  "awaiting": "none",
  "timestamp": "..."
}
```

### Automated delivery (future) — embeds `ExecutionResult`
```json
{
  "answer": "Configuration applied successfully.",
  "stage": "DONE",
  "delivery_mode": "automated",
  "execution_result": { "status": "success", "changed": true, "summary": "...", "raw_recap": "..." }
}
```

- `session_id` is **functionally required** for CONFIG (chaining); auto-generated and
  returned if absent.

---

## 12. Prompt Additions (in `app/prompts.py`)

1. **Extend `INTENT_CLASSIFIER_PROMPT`** — add `CONFIG` (+ few-shot), pass recent
   `history` for chained classification.
2. **`CONFIG_TYPE_DETECT_PROMPT`** (LLM fallback) → `{config_type, confidence, candidates[]}`.
3. **`CONFIG_FIELD_EXTRACT_PROMPT`** — extract `{collected: {field: value}}`; never
   invent values; omit unknowns.
4. **`CONFIG_RENDER_PROMPT`** — given the **vetted reference template** + collected
   values, return the finalised playbook, constrained to the template (§10.0).
5. (Optional) **`CONFIG_QUESTION_PROMPT`** — phrase the consolidated follow-up.

All follow the existing `PydanticOutputParser` pattern.

---

## 13. State Machine (Reference Diagram)

```
                 ┌──────────────┐
 new CONFIG ───▶ │ DETECT_TYPE  │  (keyword → LLM + confidence)
                 └──────┬───────┘
            low conf │           │ confident
                     ▼           ▼
              ┌────────────┐  ┌───────────────┐
              │DISAMBIGUATE│  │COLLECT_FIELDS │◀────┐ still missing (req #4)
              └─────┬──────┘  └──────┬────────┘     │
                    │                │ all present  │
                    │                ▼              │
                    │        ┌────────────────┐     │
                    │        │ RESOLVE_TARGET  │ (user picks Integrated/Standalone)
                    │        └──────┬─────────┘     │
                    │               ▼               │
                    └──────▶┌────────────────┐──────┘ amendment
                            │CONFIRM_APPROVAL │
                            └──────┬─────────┘
                                   │ approved (full gate)
                                   ▼
                            ┌──────────────┐
                            │   DELIVER    │  Manual(v1): return script
                            │              │  Automated(future): run + ExecutionResult
                            └──────┬───────┘
                                   ▼
                                 DONE → clear state
```

---

## 14. Implementation Phases

**Phase 0 — Foundations (CONFIG chaining)**
- `ConversationStore` (dict + TTL); wire `/api/v1/chat` to load/append/save history;
  pass history into `classify_intent`. *(Req #1, CONFIG)*

**Phase 1 — CONFIG skeleton**
- Add `CONFIG` to classifier + router. Add `ConfigState` + `ConfigStage`.
- Build the registry mapping + the 5 vetted templates in `playbooks/`.
- Keyword detection → consolidated slot filling. *(Req #4)*

**Phase 2 — LLM fallback, disambiguation, approval**
- `config_chain.detect_type` / `extract_fields`; `DISAMBIGUATE` (req #3);
  `CONFIRM_APPROVAL` full gate (req #2).

**Phase 3 — Render + Manual delivery (v1 execution path)**
- `render_playbook` (template sent to LLM); RESOLVE_TARGET + the `config_inventory`
  table (dummy data); user mode choice; **return rendered script (Manual)**.
- Stub the **Automated** branch (returns "coming soon").

**Phase 4 — Future / Automated (kept open)**
- `ansible_runner`, transient inventory from `config_inventory`, `--check` dry-run,
  `ExecutionResult`; RAG-served templates; production session backend + audit log.

**Phase 5 — Chaining util for the other four intents (done last)**
- Separate `IntentHistoryService` for SQL/RAG/SEARCH/HYBRID (§5.1).

---

## 15. Edge Cases & Safety

- **Idempotency (decision I):** before delivering/executing, compute a signature
  from `session_id + config_type + collected`; if it equals
  `last_executed_signature`, return the prior result instead of re-running.
- **Consolidated but cumulative:** asking for all missing fields never drops prior
  values (`collected` is additive).
- **Mid-flow intent switch:** offer to pause/discard a half-filled CONFIG if the user
  changes topic.
- **Infinite clarification:** `attempts` cap → graceful give-up.
- **Stale session resume:** TTL expiry clears `config_state`.
- **Invalid field values:** per-field validators reject and re-ask.
- **Rendering safety:** the LLM is constrained to the vetted template; output is
  validated against the template's variable set — no invented directives.
- **Secrets:** standalone creds are session-only, never logged; approval summary
  hides passwords.
- **Concurrent workers:** dict store is per-process; production backend needed before
  `workers > 1` (today `workers=1`).

---

## 16. Testing

- Unit-test `ConfigService.handle` as `(message, state) → (response, new_state)`:
  keyword detect, LLM fallback, disambiguation (req #3), consolidated partial answers
  (req #4), target-mode choice, approval accept/amend/cancel (req #2), manual render
  output, idempotent re-delivery.
- Validate rendered playbooks against their template variables (no extra directives).
- Mock the automated runner so tests never touch real devices.
- Integration-test the multi-turn loop on `/api/v1/chat` with a fixed `session_id`.

---

## 17. Open Questions (remaining)

**Resolved (now in the design):** config types (dynamic; 5 use cases — §9) •
playbooks live in repo registry, LLM now / RAG prod (§9, M) • approver = session user
(§7, N) • target mode = user chooses, integrated reads new `config_inventory` table
(§10.2, J) • dry-run = automated-only, deferred (§10.3) • post-approval = Manual v1 /
Automated future (§10.1, L).

**Still open:**
1. **Platform-specific playbooks** — do any of the 5 types need different templates
   for Nexus 2900 vs 9300 (NX-OS) vs IOS, or one template parameterised by platform?
   *(Networking team input needed.)*
2. **Production session backend** (Redis vs SQLite) and TTL/retention — deferred;
   prototype stage.
3. **Audit trail** — is a dedicated DB table needed to log executed/delivered configs
   (likely yes once Automated mode lands)?
4. **`config_inventory` schema** — confirm final columns and how credentials are
   stored (plain dummy now; vault/secret ref in production).

---

## 18. Questions & Expected Outcomes (behaviour walkthrough)

Each scenario below shows a **user turn**, the **expected outcome**, and the
**resulting state** the engine should hold afterward. Together they form the
acceptance scenarios referenced in §16.

> Legend — `stage`: where the state machine lands • `collected`: slot values held •
> `→ next`: what the assistant asks/returns next.

---

### Q1 — Happy path, all info in one shot (keyword detection)

> **User:** "Set the hostname on R1 to CORE-RTR-01"

**Expected outcome**
- Keyword pass matches `HOSTNAME` **deterministically** — no LLM type-detection cost (§8).
- `hostname` is extracted; nothing is missing, so the flow moves straight toward target + approval.

| field | value |
|-------|-------|
| `config_type` | `HOSTNAME` |
| `collected` | `{ hostname: "CORE-RTR-01" }` |
| `stage` | `RESOLVE_TARGET` → `CONFIRM_APPROVAL` |
| → next | "Integrated or Standalone target?" then the approval summary |

---

### Q2 — Missing fields → one consolidated question (req #2/#4)

> **User:** "Create a VLAN named SERVERS"

**Expected outcome**
- Type resolves to `VLAN`. Only `vlan_name` is captured; `vlan_id` and `ports` are missing.
- The assistant asks for **all** outstanding fields in **one** message (not one at a time).

| field | value |
|-------|-------|
| `config_type` | `VLAN` |
| `collected` | `{ vlan_name: "SERVERS" }` |
| `missing_fields` | `["vlan_id", "ports"]` |
| `stage` | `COLLECT_FIELDS` |

> **Assistant → next:** "I still need the **VLAN ID** (1–4094) and the **ports** to assign."

---

### Q3 — Partial answer, cumulative slots (req #4: asked 2, got 1)

> **User (reply to Q2):** "VLAN 30"

**Expected outcome**
- One slot fills; prior values are **never dropped**. `missing_fields` recomputes and only the remainder is re-asked.

| field | value |
|-------|-------|
| `collected` | `{ vlan_name: "SERVERS", vlan_id: 30 }` |
| `missing_fields` | `["ports"]` |
| `stage` | `COLLECT_FIELDS` |

> **Assistant → next:** "Which **ports** should be assigned to VLAN 30?"

---

### Q4 — Vague request → disambiguation (req #3)

> **User:** "I want to change something on the network"

**Expected outcome**
- Keywords miss; LLM fallback returns low confidence / multiple candidates → `DISAMBIGUATE`.
- Assistant offers 2–3 **example prompts drawn from the mapping** (so it only advertises real capabilities) and asks the user to reconfirm.

| field | value |
|-------|-------|
| `config_type` | `None` (unresolved) |
| `stage` | `DISAMBIGUATE` |

> **Assistant → next:** "I'm not sure which change you mean. Did you want to:
> (1) set a hostname, (2) create a VLAN, or (3) add a static route?"

---

### Q5 — Approval → manual delivery (v1 happy ending)

> **User (at the approval summary):** "approve"

**Expected outcome**
- Full gate satisfied (`approved = True`). Manual mode renders `playbooks/vlan.yml` with the collected values and **returns the script** for the user to run. **No device is contacted** (§10.1).

| field | value |
|-------|-------|
| `delivery_mode` | `manual` |
| `stage` | `DELIVER` → `DONE` (state cleared) |
| returns | `rendered_playbook` (YAML) |

---

### Q6 — Amendment at the approval gate (gate stays closed)

> **User (at the approval summary):** "actually make it VLAN 40"

**Expected outcome**
- Field-like input during `CONFIRM_APPROVAL` is treated as an **edit**, not an approval. The summary re-renders; delivery stays blocked until an explicit "approve".

| field | value |
|-------|-------|
| `collected.vlan_id` | `40` (updated) |
| `approved` | `False` |
| `stage` | `CONFIRM_APPROVAL` (re-summarized) |

---

### Q7 — Double "approve" (idempotency — decision I)

> **User:** "approve"  →  (re-sent / double-click)  "approve"

**Expected outcome**
- Signature `session_id + config_type + collected` equals `last_executed_signature`, so the **prior result is returned** — no re-render, no re-run, no double-apply (§15).

---

### Q8 — Automated mode requested (stubbed in v1)

> **User:** "Apply it to the device for me automatically"

**Expected outcome**
- `delivery_mode = automated` selects the Automated branch, which is **wired but stubbed**: it returns a "coming soon / not available yet" message. No `ansible-playbook` runs (§10.1, decision L).

---

### Q9 — Topic switch mid-flow (don't silently lose state)

> **User (half-way through a VLAN flow):** "Actually, show me all switches in inventory"

**Expected outcome**
- The assistant detects the intent switch and **offers to pause or discard** the half-filled CONFIG state before handing off, so in-progress slots aren't lost silently (§15).

---

### Q10 — Endless vague input (graceful give-up)

> **User:** "Enable SSH" … (repeated vaguely, no `domain_name` ever given)

**Expected outcome**
- Each turn re-asks for `domain_name`. When `attempts` hits the cap (~8), the flow **gives up gracefully / restarts** rather than looping forever (§6/§15).
