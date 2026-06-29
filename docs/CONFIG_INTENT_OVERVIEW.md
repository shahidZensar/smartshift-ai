# CONFIG Intent — Approach & Workflow (Meeting Brief)

> One-page explainer for the CONFIG intent: what it does, how a request flows
> end-to-end, and the design/safety decisions worth highlighting.
> Companion to [`CONFIG_INTENT_TEST_PROMPTS.md`](CONFIG_INTENT_TEST_PROMPTS.md).
> Platform: Cisco IOS · Delivery: **Manual (v1)** · Last updated: **2026-06-15**

---

## 1. Elevator pitch

The assistant already answers questions (SQL / RAG / HYBRID / SEARCH). **CONFIG** adds the
ability to *act*: turn a plain-English request like *"create VLAN 30 named FINANCE"* into a
**vetted, ready-to-run Ansible playbook + command**, after a guided, validated, human-approved
conversation. It never writes device config itself and (in v1) never touches a device — it
prepares the change and hands it back for the engineer to run.

**Why it matters:** safe, conversational config change with a human in the loop — not a
free-text LLM generating router commands.

---

## 2. Building blocks

| Component | Role |
|-----------|------|
| **Intent router** (`router.py` + `INTENT_CLASSIFIER_PROMPT`) | Classifies the turn; **CONFIG wins** when the user gives an imperative to change device state. |
| **ConfigService** (`services/config_service.py`) | The per-turn **state machine** — the heart of the flow. |
| **Config registry** (`config_registry.py` + `repositories/playbook-registry/required_fields.yaml`) | Single source of truth: maps each `config_type` → playbook, target group, required/optional fields, risk, keywords, per-field prompts & validators. **19 types** today. |
| **LLM helpers** (`chains/config_chain.py`) | `detect_type` (type detection fallback), `extract_fields` (pull stated values, never invent), `phrase_question` (optional natural phrasing). |
| **Config inventory** (`config_inventory.py`) | Demo device list (own `config_inventory` table) for the "Integrated" target picker. Passwords never surfaced. |
| **Conversation store** (`services/conversation_store.py`) | Persists per-session CONFIG state + chat history → multi-turn & idempotent. |

> **Extensibility:** adding a new config type = add a playbook + a `required_fields.yaml` entry
> + (optional) a keywords/field block. **No code changes** — the 4 newest types (`aaa`, `hsrp`,
> `vrrp`, `vrf`) were added exactly this way.

---

## 3. End-to-end workflow

```
User turn → POST /api/v1/chat
      │
      │  CONFIG already in progress for this session?  ──yes──► skip classifier, resume flow
      │                         │ no
      ▼                         ▼
  classify_intent()        ConfigService.handle(message, session_id)   ← runs every CONFIG turn
      │ = CONFIG                │
      └────────────────────────┘
                               ▼
   ┌─────────────┐   ambiguous   ┌──────────────┐
   │ DETECT_TYPE │ ────────────► │ DISAMBIGUATE │  (offer numbered candidates)
   └─────────────┘ ◄──────────── └──────────────┘
        │ resolved
        ▼
   ┌────────────────┐   missing / invalid fields (ask, consolidated)
   │ COLLECT_FIELDS │ ◄──────────────┐
   └────────────────┘ ───────────────┘  (cumulative, validated)
        │ all required fields present
        ▼
   ┌────────────────┐   Integrated → pick device from inventory
   │ RESOLVE_TARGET │   Standalone → collect device/IP/user/password (session-only)
   └────────────────┘
        │ target known
        ▼
   ┌──────────────────┐   "approve"        ┌──────────┐        ┌──────┐
   │ CONFIRM_APPROVAL │ ────────────────►  │ DELIVER  │ ─────► │ DONE │
   └──────────────────┘  (edit re-opens)   └──────────┘        └──────┘
        gate shows summary + risk          playbook YAML +     idempotent
                                           ansible command     re-approve
```

### Stage-by-stage

| Stage | What happens | Key behaviour |
|-------|--------------|---------------|
| **DETECT_TYPE** | Map request → one of 19 `config_type`s. | **Keywords first** (deterministic, no LLM). 1 hit → resolved. Collision → LLM picks if confident (≥0.8), else disambiguate. No hit → LLM (≥0.6 resolve). |
| **DISAMBIGUATE** | Offer a short numbered candidate list when unsure. | User replies number / type name / rephrase. |
| **COLLECT_FIELDS** | LLM extracts **only stated** values; merge + validate; ask for everything still missing **in one message**. | **Never invents values**; **cumulative** (earlier slots kept); validators: `vlan_id`, `ipv4`, `prefix`, `int`, `list`, `state`. Bad values rejected & re-asked. |
| **RESOLVE_TARGET** | Choose where it runs. | **Integrated**: pick from inventory (filtered by the type's target group; creds read securely). **Standalone**: user supplies connection details — **transient, never persisted or logged**. |
| **CONFIRM_APPROVAL** | Show full summary: fields, target, template, delivery mode, **risk**. | Hard gate — must reply `approve`. **Any edit re-opens the gate.** HIGH-risk types add a `--check` warning. |
| **DELIVER** | Render the vetted playbook + the `ansible-playbook … -e '{vars}'` command + sample `inventory.ini` line. | **Manual mode**: handed back to run. **Idempotent** (sha256 of type+fields). |
| **DONE** | Flow complete; result cached. | Re-sending `approve` returns the same result (no double-apply). |

---

## 4. Design & safety decisions (talking points)

- **Human-in-the-loop by default** — nothing is delivered without an explicit approval gate.
- **No device is touched in v1** — delivery is *manual*: we produce the playbook + command; the
  engineer runs it. "Automated execution" is wired but returns a *not-available-yet* notice.
- **The LLM never writes router config** — playbooks are pre-vetted and unchanged; the LLM only
  (a) routes intent, (b) detects type, (c) extracts values the user actually stated. Determinism
  comes from keyword matching + validators, not the model.
- **Secrets are protected end-to-end** — passwords / shared keys are marked `secret`, shown as
  `***` in summaries, and never written into commands, inventory lines, or logs.
- **Robust conversation handling** — consolidated multi-field asks, cumulative slot-filling,
  validation with re-ask, **cancel anytime**, **amend at the gate**, **mid-flow topic switch**,
  idempotent re-approve, and an attempts cap (8) that gives up gracefully instead of looping.
- **Risk-aware** — each type carries a `low/high` risk; HIGH-risk types (`ssh_access`, `aaa`,
  `vrrp`) surface a warning and a `--check`-first command.
- **Config-driven, not code-driven** — the registry YAML is authoritative; new types drop in
  with no code change.

---

## 5. Worked example (happy path)

```
User: Create VLAN 30 named FINANCE
  → DETECT_TYPE: keyword "vlan" → config_type=vlan (no LLM needed)
  → COLLECT_FIELDS: vlan_id=30, vlan_name=FINANCE extracted & validated → all present
Assistant: Integrated or Standalone?
User: 1                       → RESOLVE_TARGET: lists the 2 switches
User: 1                       → picks core-sw-01
Assistant: <approval summary: vlan_id 30, name FINANCE, target core-sw-01, risk LOW>
User: approve
  → DELIVER: returns vlan.yml playbook + `ansible-playbook -i inventory.ini layer2/vlan.yml -e '{...}'`
```

A missing field (e.g. *"create a VLAN named SERVERS"*) simply pauses at COLLECT_FIELDS to ask for
the VLAN ID, then continues the same tail.

---

## 6. Scope

| ✅ Built (v1) | 🔜 Deferred |
|--------------|-------------|
| Intent routing + stateful refinement loop | Automated execution (ansible-runner against live devices) |
| 19 config types, registry-driven | Real inventory / vault-backed credentials (currently demo data) |
| Keyword + LLM type detection, disambiguation | Multi-device / bulk changes per request |
| Validation, approval gate, manual delivery | Post-run verification & rollback automation |
| Secret redaction, idempotency, cancel/amend/give-up | |
```
