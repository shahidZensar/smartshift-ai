# Session Context — CONFIG Target-Resolution Forms

> Handoff doc for the next Claude session. Last updated: 2026-06-19.
> Project: SmartShift AI network-migration assistant (FastAPI + Azure GPT-4o + React).

## System in one paragraph

Single chat endpoint `POST /api/v1/chat` (`askv1_question` in [app/app.py](../app/app.py))
routes each message to one of five tools/intents via `classify_intent`
([app/router.py](../app/router.py)): **SQL** (Inventory Analyzer), **RAG** (Knowledge
Assistant), **HYBRID** (Migration Planner), **SEARCH** (Web Research, the safe default),
**CONFIG** (Config Automation). Plus a File Analyzer at `/api/chat/upload`. The CONFIG
intent is a multi-turn state machine ([app/services/config_service.py](../app/services/config_service.py))
that turns a natural-language request into a vetted Ansible playbook + ready-to-run command
(manual delivery only in v1 — no device is ever contacted automatically).

## What was done THIS session (the active work)

Three changes to the CONFIG **target-resolution** step (RESOLVE_TARGET stage), all verified
by direct simulation (pytest is NOT installed locally — don't assume the suite runs):

### 1. Form-based collection in **standalone** mode
- The standalone branch of `_resolve_target` ([config_service.py](../app/services/config_service.py))
  now returns a **form card** (when `CONFIG_USE_FORMS` is on) instead of free-text questions.
- Connection fields are defined once as `FieldMeta` objects: `_CONN_FIELD_METAS` /
  `_CONN_META`, with `_STANDALONE_CONN_FIELDS = [device_name, ansible_host, username, password]`
  and `_INTEGRATED_CONN_FIELDS = [device_name, ansible_host, username]` (no password —
  integrated reads creds securely).
- They reuse the same validation (`_validate`, e.g. IPv4 check on `ansible_host`) and
  widget-typing (`_widget_type`) as config fields. New helpers: `_merge_conn`,
  `_build_connection_form`, `_connection_response`.
- Form submissions arrive as `form_values` and flow through `_resolve_target` (the existing
  `in_target` guard in `handle` routes RESOLVE_TARGET submissions here, bypassing config-field
  extraction). `form_values` is now passed into `_resolve_target(message, state, spec, form_values)`.
- Forms-off path still falls back to the text `_connection_question`.

### 2. Secret masking (frontend + backend)
- **Frontend was already covered**: `password` field has `secret=True` → `_widget_type` emits
  `type:"password"` → [ui/src/components/FormCard.jsx](../ui/src/components/FormCard.jsx)
  renders a masked input; [ui/src/App.jsx](../ui/src/App.jsx) line ~38 redacts `pass/key/secret`
  keys in the submission bubble. **No frontend change was needed.**
- **Backend**: new `_redact_target()` masks the password in the `target_device` now echoed by
  `_resp`; forms never pre-fill any value (`value: None`); plaintext password stays server-side
  only (session memory) and is never logged or rendered into playbooks/commands.

### 3. Missing inventory fields → ask via form (integrated mode)
- After a device is picked from `config_inventory`, the integrated branch checks the row for
  blank connectivity fields (`_INTEGRATED_CONN_FIELDS`) and, if any are empty, asks for just
  those via the same form. A new `ConfigState.target_filling: bool` flag ([app/models.py](../app/models.py))
  ensures the device-pick reply is never misread as a field value.
- Credentials (password) are NOT prompted in integrated mode.

### Supporting changes
- [app/models.py](../app/models.py): `ConfigState` gained `target_filling: bool = False`.
- [app/config_inventory.py](../app/config_inventory.py):
  - Added test seed row **`lab-rtr-09`** (`10.0.9.9`, group `routers`) with a **blank `username`**
    to exercise change #3 in the UI. Already inserted into the live MySQL table.
  - `ensure_schema_and_seed()` rewritten to be **insert-only / idempotent**: it inserts only
    seed devices missing by `device_name` (never overwrites), so newly-added seed devices appear
    on the next startup even when the table is already populated.
- [config_service.py](../app/services/config_service.py) `_resolve_device`: guard so a blank
  inventory field can't match every message (`"" in m` is always true) and shadow the real pick.

## How to test change #3 in the UI
1. Send e.g. **"Add a static route to 10.10.10.0/24 via 192.168.1.254"** (or "Set the hostname to LAB-CORE-09").
2. Fill the config form → at "Where should this run?" choose **`1` / Integrated**.
3. In the device picker choose **`lab-rtr-09`**.
4. Because its `username` is blank, a **"Complete Device Details"** form asks only for Username
   (no password prompt). Fill it → proceeds to approval.
5. Picking a complete device (`core-rtr-01`, etc.) resolves straight to approval — no extra form.

## Run commands (PowerShell, from `smartshift-ai/`)
- Backend: `python -m app.app`
- UI: `cd ui; npm run dev`
- Re-seed config_inventory standalone: `python -m app.config_inventory` (idempotent)
- Parse-check a file with Unicode: `python -c "import ast,io; ast.parse(io.open('PATH',encoding='utf-8').read())"`

## Standing constraints (security)
- `config_inventory` plaintext password column is **dummy data only** (demo); production → vault/secret ref.
- Device credentials/secrets must NEVER appear in approval summaries, delivered commands, inventory
  output, logs, or client echoes (`InventoryDevice.public()` + `_redact` + `_redact_target`).
- `MYSQL_URI` must stay `mysql+pymysql://root:root@127.0.0.1:3306/inventory` — no real DB password.
- CONFIG delivery is **manual only** in v1; automated execution is wired but intentionally not built.

## Key files
| File | Role |
|---|---|
| [app/services/config_service.py](../app/services/config_service.py) | CONFIG state machine (this session's main edits) |
| [app/config_inventory.py](../app/config_inventory.py) | INTEGRATED device source; seed + idempotent seeding |
| [app/models.py](../app/models.py) | `ConfigState`, `ConfigFormBuild`, connection models |
| [app/chains/config_chain.py](../app/chains/config_chain.py) | CONFIG LLM calls (detect/extract/form/preflight) |
| [app/config_registry.py](../app/config_registry.py) | 19 config types derived from playbooks; `FieldMeta`/`ConfigTypeSpec` |
| [ui/src/components/FormCard.jsx](../ui/src/components/FormCard.jsx) | Dynamic form renderer (masks `type:password`) |
| [ui/src/App.jsx](../ui/src/App.jsx) | Chat client; form submission + bubble redaction |
| [docs/TOOLS_AND_HOWTO.md](TOOLS_AND_HOWTO.md) | System-wide stakeholder doc (per-tool hands-on) |
| [docs/CONFIG_INTENT_TEST_PROMPTS.md](CONFIG_INTENT_TEST_PROMPTS.md) | Sample prompts per config type / edge cases |

## Pending / not started (do NOT start without confirmation)
- Update [docs/TOOLS_AND_HOWTO.md](TOOLS_AND_HOWTO.md) §3.6 — still describes standalone target
  collection as a free-text prompt; should mention the new form behavior.
- Stale docs `CONFIG_INTENT_PROGRESS.md` / `CONFIG_CODE_GUIDE.md` reference a deleted
  `required_fields.yaml` and "15 types" (now 19).
- Install pytest to run `tests/test_config_gate.py` (10 gate tests, fully mocked LLM).
- Optionally move `MYSQL_URI` to an env var.
