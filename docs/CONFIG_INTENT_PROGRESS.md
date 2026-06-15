# CONFIG Intent — Implementation Progress

> Companion to [`CONFIG_INTENT_PLAN.md`](CONFIG_INTENT_PLAN.md). The plan is the design;
> **this document records what is actually built in the code**, what was changed vs. the
> plan, what was verified, and what remains deferred.
>
> Last updated: **2026-06-12**
> Scope delivered: CONFIG intent end-to-end (manual delivery) + chaining for all intents.
> Platform: Cisco IOS. Delivery mode: **Manual (v1)**. Automated runner: **deferred**.

---

## 1. Status at a glance

| Phase / Feature | Plan ref | Status | Notes |
|---|---|---|---|
| Phase 0 — Conversation store (CONFIG chaining) | §5, §14 | ✅ Done | In-process dict + TTL |
| Phase 1 — CONFIG skeleton (classifier, registry, keyword detect, slot-fill) | §1, §8, §9 | ✅ Done | All **15** types wired |
| Phase 2 — LLM fallback, disambiguation, approval gate | §7, §8 | ✅ Done | + confidence-band tuning |
| Phase 3 — Render + Manual delivery + RESOLVE_TARGET + `config_inventory` | §10 | ✅ Done | MySQL-backed inventory |
| LLM question phrasing (natural follow-ups) | §6 dec. C | ✅ Done | Optional, toggleable |
| Phase 5 — Chaining for SQL / RAG / SEARCH / HYBRID | §5.1 | ✅ Done | Reused conversation store |
| Phase 4 — Automated ansible runner | §10.3 | ⛔ Deferred | Stub returns manual fallback |
| Production session backend (Redis/SQLite) | §17 | ⛔ Deferred | Prototype uses dict |
| Audit trail table | §17 | ⛔ Deferred | — |
| RAG-served templates | §9 dec. M | ⛔ Deferred | Templates read from disk |
| Platform-specific playbooks (NX-OS, etc.) | §17 | ⛔ Deferred | IOS only |

---

## 2. Reconciliations vs. the plan (decisions made during build)

These are deliberate deviations from `CONFIG_INTENT_PLAN.md`, made because the plan and the
delivered playbook registry diverged, or because a simpler/safer path existed.

1. **Registry is the source of truth for type names + field names.**
   The plan's §9 sketch used types like `INTERFACE_IP` with fields `interface, ip, subnet`.
   The delivered registry (`repositories/playbook-registry/required_fields.yaml`) uses
   `interface_l3` with `interface_name, ip_address, subnet_mask`, etc. **The registry wins.**
   The working set is **15 config types**, not the plan's 5.

2. **4 missing playbooks were authored.** The registry mapping referenced playbooks that did
   not exist on disk: `vlan.yml`, `interface.yml` (interface_l2), `static_route.yml`, `acl.yml`.
   These were created using Cisco IOS resource modules in the same vetted style.

3. **Manual delivery returns the vetted playbook unchanged + a ready-to-run command** (not an
   LLM-rendered YAML). Every playbook consumes its `required_fields` as `-e` extra-vars by
   design, so rendering = the original YAML + `ansible-playbook … -e '{json}'`. This is
   deterministic and satisfies the plan's "constrained to template, no invented directives"
   guardrail without an LLM render step (§10.0's "pure substitution path" option).

4. **`config_inventory` is a real MySQL table** (not a static file or in-memory only). Lives in
   the same DB as the SQL flow's `inventory` table, behind a query layer with an in-memory
   fallback. Credentials are a **plaintext dummy column** (demo), redacted before reaching the client.

5. **Phase-5 chaining reuses `conversation_store`** rather than building the plan's separate
   `IntentHistoryService` (§5.1). The store already records every turn for every session, so a
   second store would double-record. History is injected into each chain's prompt via a helper.

6. **DISAMBIGUATE and the LLM phrasing pass were built earlier than the plan sequenced them**
   (they were cheap once the detection chain existed).

---

## 3. The state machine as implemented

`ConfigStage` enum (in `app/models.py`):

```
DETECT_TYPE → [DISAMBIGUATE] → COLLECT_FIELDS → RESOLVE_TARGET → CONFIRM_APPROVAL → DELIVER → DONE
```

Per-turn flow (`ConfigService.handle(message, session_id)` in `app/services/config_service.py`):

1. **DONE re-entry** — if the prior flow finished: a repeated `approve` returns the cached
   result (idempotent); anything else starts a fresh `ConfigState`.
2. **attempts++**, then **cancel** check (clears state) and **attempts cap** (`MAX_ATTEMPTS = 8`,
   graceful give-up). The cap resets on forward progress (type resolved / a new slot filled).
3. **Automated-intent detection** — phrases like "automatically" set `delivery_mode = "automated"`.
4. **DETECT_TYPE**
   - Keyword pass (`config_registry.match_keywords`): exactly one hit → resolved, **no LLM cost**.
   - Else LLM fallback (`config_chain.detect_type`) with confidence bands:
     - keyword collision + LLM conf ≥ `0.8` → trust the LLM's pick among the colliding types;
     - no keyword hit + LLM conf ≥ `0.6` → resolve;
     - otherwise → **DISAMBIGUATE** with candidates.
   - A DISAMBIGUATE reply resolves via `_resolve_choice` (number / ordinal / type name / keyword).
5. **COLLECT_FIELDS** — extract fields (`config_chain.extract_fields`), validate + merge
   (cumulative; new overrides, prior never dropped), then ask for **all** outstanding fields in
   one message. Per-field validators: `vlan_id` (1–4094), `prefix` (0–32), `ipv4`, `int`,
   `list`, `state` (present/absent).
6. **RESOLVE_TARGET** (one step per turn):
   - Choose mode: **Integrated** vs **Standalone** (no default — user picks).
   - Integrated → device picker from `config_inventory.list_devices(target_group)`; pick by
     number or name; credentials read from the row, never typed.
   - Standalone → collect `device_name / ansible_host / username / password` via
     `config_chain.extract_connection` (session-only, password redacted everywhere).
7. **CONFIRM_APPROVAL** — full mandatory gate. Summary shows fields, target, template,
   delivery mode, and risk (HIGH risk adds a `--check` warning). Edits at the gate re-open it;
   only an explicit `approve` proceeds.
8. **DELIVER**
   - Manual → vetted playbook YAML + `ansible-playbook -i inventory.ini <pb> -e '{json}'`
     + a sample `inventory.ini` line for the chosen device (no password).
   - Automated → **coming-soon notice + the manual playbook** as the usable path; **no
     `ansible-playbook` is ever run** in v1.
   - Idempotency: a signature of `config_type + collected` short-circuits re-delivery.
9. **DONE** — state retained with the cached result for idempotent re-sends.

---

## 4. Config taxonomy (15 types, all wired)

Source of truth: `repositories/playbook-registry/required_fields.yaml` + enrichment in
`app/config_registry.py`. ✏️ = playbook authored during this work.

| config_type | group | required_fields | risk | playbook |
|---|---|---|---|---|
| hostname | all | hostname | low | hostname.yml |
| ssh_access | all | domain_name | **high** | ssh_access.yml |
| user_account | all | username, user_password | low | user_account.yml |
| banner | all | banner_text | low | banner.yml |
| save_config | all | — | low | save_config.yml |
| vlan | switches | vlan_id, vlan_name | low | vlan.yml ✏️ |
| interface_l2 | switches | interface_name, mode, access_vlan | low | interface.yml ✏️ |
| port_channel | switches | channel_group_id, member_interfaces, mode | low | port_channel.yml |
| interface_l3 | routers | interface_name, ip_address, subnet_mask | low | interface_ip.yml |
| static_route | routers | destination_network, subnet_mask, next_hop | low | static_route.yml ✏️ |
| ospf | routers | process_id, network, wildcard_mask, area_id | low | ospf.yml |
| acl | routers | acl_name, action, source, destination | low | acl.yml ✏️ |
| ntp | all | ntp_server | low | ntp.yml |
| snmp | all | community, host | low | snmp.yml |
| syslog | all | syslog_server | low | syslog.yml |

> Adding a type = add a playbook + a `required_fields.yaml` entry + (optional) a keyword/field
> block in `ENRICHMENT`. No state-machine code changes.

---

## 5. File inventory

### New files
| File | Purpose |
|---|---|
| `app/config_registry.py` | Loads `required_fields.yaml` (authoritative) + enriches with keywords, per-field prompts/examples/validators, disambiguation examples. `match_keywords`, `get`, `examples`. |
| `app/config_inventory.py` | MySQL `config_inventory` table: schema + idempotent dummy seed + `list_devices`/`get_device` query layer (in-memory fallback). `InventoryDevice.public()` redacts the password. |
| `app/services/__init__.py` | Package marker. |
| `app/services/conversation_store.py` | Per-session store (dict + 2h TTL): history + CONFIG state. `format_recent()` (truncated transcript), `set/get/clear_config_state`. |
| `app/services/config_service.py` | The CONFIG state machine (detection, slot-filling, disambiguation, target resolution, approval, render, automated stub, idempotency). |
| `app/chains/config_chain.py` | LLM chains: `detect_type`, `extract_fields`, `extract_connection`, `phrase_question`. |
| `repositories/playbook-registry/{vlan,interface,static_route,acl}.yml` | 4 authored vetted playbooks. |

### Modified files
| File | Change |
|---|---|
| `app/models.py` | `ConfigStage`, `ConfigState` (incl. `candidates`, `target_*`, `delivery_mode`, idempotency fields), `ConfigTypeDetection`, `ConfigFieldExtraction`, `ConfigConnectionExtraction`. |
| `app/config.py` | `CONFIG_REQUIRE_APPROVAL`, `CONFIG_LLM_PHRASING` flags. |
| `app/prompts.py` | `CONFIG` added to `INTENT_CLASSIFIER_PROMPT` (+ history); `CONFIG_TYPE_DETECT_PROMPT`, `CONFIG_FIELD_EXTRACT_PROMPT`, `CONFIG_QUESTION_PROMPT`, `CONFIG_CONNECTION_EXTRACT_PROMPT`. |
| `app/router.py` | `CONFIG` in `VALID_INTENTS`; `classify_intent(query, history)`. |
| `app/app.py` | Session resolve/auto-gen; resume in-progress CONFIG without re-classify; CONFIG branch; history threaded into all chains; `config_inventory` seed on startup. |
| `app/util.py` | `with_history(prompt_text, history)` preamble helper. |
| `app/chains/sql_chain.py`, `response_chain.py`, `rag_chain.py`, `web_search.py` | `history` param threaded into each prompt. |
| `app/requirements.txt` | `pyyaml`. |
| `ui/src/App.jsx` | Persist + resend the backend `session_id`; reset on New Chat (enables multi-turn chaining in the UI). |

---

## 6. Chaining (history) — all intents

- Every turn is recorded in `conversation_store` for every intent.
- `classify_intent` receives recent history (context-aware routing).
- An in-progress CONFIG flow resumes **without re-classifying** (so `approve`, `1`, `cancel`,
  field values route correctly).
- For SQL / RAG / SEARCH / HYBRID, `with_history(...)` prepends a truncated transcript
  (each turn capped at 500 chars; window = last 8 turns) so follow-ups like "those", "that one",
  "what about Pune" resolve. Applied after template formatting → never breaks placeholders.

---

## 7. Config flags & tunables

| Name | Location | Default | Effect |
|---|---|---|---|
| `CONFIG_REQUIRE_APPROVAL` | `config.py` / env | `true` | Mandatory approval gate. |
| `CONFIG_LLM_PHRASING` | `config.py` / env | `true` | LLM-polish COLLECT/DISAMBIGUATE wording (falls back to deterministic text on failure). Set `false` to skip the extra LLM call. |
| `CONFIG_REGISTRY_DIR` | env | repo registry path | Where playbooks + `required_fields.yaml` live. |
| `MAX_ATTEMPTS` | `config_service.py` | `8` | Give-up cap (resets on progress). |
| `DETECT_CONFIDENCE_LOW / _HIGH` | `config_service.py` | `0.6 / 0.8` | LLM detection confidence bands. |
| `SESSION_TTL` | `conversation_store.py` | `2h` | Stale session expiry (clears CONFIG state). |
| `HISTORY_WINDOW` | `conversation_store.py` | `8` | Turns fed to classifier + chains. |

---

## 8. Security / safety properties (implemented)

- **Approval gate** is mandatory before any delivery.
- **Passwords never leave the server**: standalone connection passwords live only in session
  state; `InventoryDevice.public()` strips the inventory password; approval summaries, rendered
  commands, sample inventory lines, and the API response payload all omit passwords.
- **Field values validated** before acceptance (range/format checks); invalid values re-asked.
- **No runtime YAML generation** — only vetted templates + extra-vars.
- **High-risk flagging**: `ssh_access` is marked HIGH (non-idempotent crypto-key regen);
  delivery command appends a `--check` reminder.
- **Idempotency**: duplicate `approve` / identical request returns the cached result.
- **History truncation** prevents prompt bloat / accidental secret echo from long prior turns.

---

## 9. Verification performed

Offline (LLM stubbed, deterministic) + live UI runs against Azure gpt-4o + MySQL:

- **Registry**: all 15 types load; every playbook resolves on disk; keyword matching works.
- **State machine (Q1–Q7)**: keyword happy-path, consolidated + cumulative slot-filling,
  disambiguation, amendment-keeps-gate-closed, idempotent double-approve.
- **Disambiguation tuning**: keyword collision → numbered pick; vague → LLM candidates →
  ordinal pick; confident-LLM auto-resolve skips disambiguation.
- **RESOLVE_TARGET**: integrated device picker, standalone connection collection (password
  hidden), automated request → stub + manual fallback. Verified live.
- **`config_inventory`**: MySQL table seeded; `list_devices` group filter, `get_device`,
  and `public()` redaction verified against the live DB.
- **Chaining helpers**: `with_history` no-op/prepend, `format_recent` truncation verified.
- All changed modules byte-compile.

---

## 10. Known limitations / caveats

1. **Meta/recall questions** ("what did I ask?") depend on intent classification — if routed to
   SQL they still attempt a query. Follow-up *resolution* is fixed; a dedicated recall intent is not built.
2. **In-process session store** — per-process dict; needs a shared backend (Redis/SQLite)
   before running `workers > 1` (today `workers=1`).
3. **Combining two steps in one message** during RESOLVE_TARGET (e.g. "integrated then 1")
   consumes only the mode that turn (by design, to avoid the `1`=mode vs `1`=device ambiguity).
4. **Automated execution is stubbed** — no device is ever contacted.
5. **Dummy credentials** in `config_inventory` are plaintext for the demo; production must move
   to a vault/secret reference.
6. **IOS only** — no platform-specific template selection yet.

---

## 11. Deferred / next candidates

- **Phase 4 — Automated ansible runner**: `ansible_runner` + transient inventory from
  `config_inventory` + `--check` dry-run + `ExecutionResult`. (Parked by request.)
- **Production session backend** (Redis/SQLite) + retention policy.
- **Audit trail** table for delivered/executed configs.
- **RAG-served templates** instead of disk reads.
- **Vault-backed credentials** for `config_inventory`.
- **Platform-aware playbooks** (NX-OS / IOS-XE variants).
- **Recall intent** for "what did I ask" style meta-questions.

---

## 12. How to run

```powershell
# backend (from smartshift-ai/)
.\venv\Scripts\Activate.ps1
python -m app.app            # serves http://localhost:8000 ; auto-creates config_inventory

# seed config_inventory standalone (optional)
python -m app.config_inventory

# UI (from smartshift-ai/ui/)
npm run dev
```

Multi-turn CONFIG flows chain via the `session_id` the UI now persists and resends.
