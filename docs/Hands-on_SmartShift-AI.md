# SmartShift AI — Tools, Intents & How-To Guide

> A shareable overview for technical stakeholders: **why** the system exists, **what each
> tool does**, **how each one works**, and **what questions each supports** — with a deeper
> hands-on for the CONFIG (network automation) tool.
>
> Last updated: **2026-06-18** · Backend: FastAPI + Azure GPT-4o · UI: React

---

## 1. What we are building (the intent)

An assistant for **enterprise network device migration** with three jobs:

1. **Analyze the network inventory** — read the customer's deployed-device database and answer
   questions about it (what's deployed, where, end-of-life/end-of-support, counts).
2. **Recommend the best-fit migration** — combine that inventory with internal migration/lifecycle
   policy to produce a structured plan: impacted devices, risk level, recommended replacements.
3. **Automate the configuration** — turn a plain-English change request into a **vetted Ansible
   playbook** ready to run, through a controlled, approval-gated flow (no ad-hoc scripting).

Everything is driven from **one chat endpoint** (`POST /api/v1/chat`). A lightweight **intent
router** reads each message (plus recent history) and dispatches it to exactly one capability
("tool"). **Each tool below = one intent.**

```
                       ┌──────────────────────────────────────────────┐
  user message ──▶ Intent Router ──▶ one of:                           │
                       │   SQL · RAG · HYBRID · SEARCH · CONFIG         │
                       └──────────────────────────────────────────────┘
   (file upload uses a separate endpoint — see the File Analyzer note)
```

---

## 2. The tools at a glance (1 intent = 1 tool)

| Tool (intent) | Its job | Data source | Fires when the user… | Returns |
|---|---|---|---|---|
| **Inventory Analyzer** (`SQL`) | Look up / count / filter the customer's own device records | MySQL `inventory` table | asks about deployed devices, EOL/EOS, counts, locations | structured device list with EOL/risk |
| **Knowledge Assistant** (`RAG`) | Answer from internal documents & policies | FAISS vector store of uploaded PDFs/guides | references a policy/manual or asks "how do I…" from docs | grounded, cited answer |
| **Migration Planner** (`HYBRID`) | Combine inventory **and** policy into a migration plan | SQL + vector store | needs both device data **and** guidance ("list devices and recommend replacements") | per-device plan: risk, replacement, action |
| **Web Research** (`SEARCH`) | General / latest knowledge not in our data | Public web (search API) | asks a definition, concept, or current-info question | concise web-grounded answer (default fallback) |
| **Config Automation** (`CONFIG`) | Turn a change request into a vetted Ansible playbook | Playbook registry + device inventory | asks to **change** device config ("create VLAN 30") | a runnable playbook + command (manual mode) |

**Supporting capability — File Analyzer** (separate `/api/chat/upload` endpoint): a user can upload
a device file; it's parsed and stored in session memory so follow-up questions can be answered
against it. It feeds the same analysis/RAG idea but is not one of the five chat intents.

### Quick "which tool?" guide
| You ask… | Tool |
|---|---|
| "List all switches in Pune" / "which devices reach EOL next quarter" | SQL |
| "What does the migration policy say about EOL devices?" | RAG |
| "List our routers and recommend replacements with risk levels" | HYBRID |
| "What is end-of-life in networking?" | SEARCH |
| "Create VLAN 30 named FINANCE" / "set the hostname to CORE-SW-01" | CONFIG |

**Chaining:** the assistant remembers recent turns per session, so follow-ups like "summarize that"
or "only the ones in Pune" resolve against context — across **every** tool, not just one.

---

## 3. Hands-on: each tool

Each tool below has the same shape: **what it does**, **how it works**, and **what to ask**.
CONFIG is the most involved, so it gets the deepest treatment (§3.6).

### 3.1 Inventory Analyzer (`SQL`) — your device database
**What it does.** Answers questions about the customer's **own** deployed devices: listing,
counting, filtering, lookups, and end-of-life/end-of-support status.

**How it works.** The router picks `SQL`; the question (plus history) is turned into a SQL query
against the MySQL `inventory` table, executed, and the rows are enriched (e.g. **Days Until EOL**
computed from the support date) before being formatted into a clean, structured answer with a
risk read-out per device. If nothing matches, it says so plainly — it does not invent records.

**What to ask.**
- `List all switches in Pune`
- `How many devices reach end-of-support in the next quarter?`
- `Show me every C9300 we have deployed and their support dates`
- `Which devices are already past EOL?`
- *(follow-up)* `now only the ones in Mumbai`

### 3.2 Knowledge Assistant (`RAG`) — your internal documents
**What it does.** Answers from **internal documents and policies** — uploaded PDFs, manuals,
configuration guides, migration/lifecycle policy.

**How it works.** The router picks `RAG`; relevant passages are retrieved from a FAISS vector
store and the answer is generated **strictly from that context**. If the documents don't cover
it, the assistant says the information isn't available rather than guessing — answers stay
grounded in (and traceable to) the source material.

**What to ask.**
- `What does the internal migration policy say about EOL devices?`
- `What are the prerequisites for configuring CGMP per our guide?`
- `How do I configure PortFast according to the documentation?`
- *(follow-up)* `summarize that in two bullet points`

### 3.3 Migration Planner (`HYBRID`) — inventory + policy together
**What it does.** Produces a **best-fit migration plan** by combining the device data (SQL) with
the policy/guidance (RAG) — the core "recommend the migration" job.

**How it works.** The router picks `HYBRID` when a request needs **both** sources. It runs the
SQL lookup **and** retrieves policy context, then asks the model to produce a **per-device** plan:
each device with its computed **risk level** (CRITICAL/HIGH/MEDIUM/LOW from days-to-EOL), a
**recommended replacement**, and the suggested action. If there are no matching devices it says so.

**What to ask.**
- `List our routers nearing EOL and recommend replacements with risk levels`
- `Show the switches in Pune and what we should migrate them to`
- `Which devices are urgent to replace, and what does the policy recommend?`

### 3.4 Web Research (`SEARCH`) — general & latest knowledge
**What it does.** Answers general questions, definitions, concepts, and current/real-time info
that is **not** in our inventory or documents. It's also the **safe default** when intent is unclear.

**How it works.** The router picks `SEARCH`; the question goes to a web search, and the results
are summarized into a concise, relevant answer (prioritising authoritative sources). It's the
fallback so the assistant always has a sensible path even for off-topic or novel questions.

**What to ask.**
- `What is end-of-life in networking?`
- `What are the latest Cisco Catalyst switch models?`
- `Explain the difference between HSRP and VRRP`
- *(follow-up)* `give a real-world example of that`

### 3.5 File Analyzer — bring your own device file
**What it does.** Lets a user **upload a device file** (e.g. a config or inventory export);
it's parsed and kept in session memory so follow-up questions can be answered against it.

**How it works.** A separate upload endpoint (`/api/chat/upload`) parses the file, stores the
content in the session, and routes follow-ups through the same RAG/web logic — so "what does this
file say about…" works just like the Knowledge Assistant, but grounded on **your** uploaded file.
*(Not one of the five chat intents — it's a supporting capability.)*

**How to use.** Attach a file in the UI with your question (e.g. *"analyse this config"*), then
ask follow-ups in the same session.

### 3.6 Config Automation (`CONFIG`) — the network-automation tool

#### 3.6.1 What it does and why
CONFIG converts a natural-language request into a **pre-written, vetted Ansible playbook** filled
with the user's values — it never generates YAML from scratch. Each playbook is reviewed once and
lives in a catalog; the assistant only **parameterises** it. In v1 it returns the playbook + the
exact `ansible-playbook` command for the user to run (**manual delivery — no device is contacted**).

> **Approach in one line:** detect the change → confirm it's a real action → collect the required
> parameters (via a form) → validate against the playbook → choose the target → get approval →
> hand back the vetted playbook + command.

#### 3.6.2 The flow (what happens each turn)
```
1. Intent gate     Is this a real CONFIG ACTION, or just a device name? (see 3.6.3)
2. Detect type     Which of the supported config types? (keyword first, LLM fallback)
3. Collect fields  A dynamic form asks for the required parameters (and pre-fills what you gave)
4. Pre-flight      An AI check validates your values against the actual playbook (safety/sanity)
5. Resolve target  Integrated (pick a device from inventory) or Standalone (you supply details)
6. Approval        A summary is shown; nothing is delivered until you reply "approve"
7. Deliver         The vetted playbook + ready-to-run command are returned
```

#### 3.6.3 The intent gate (handles "device vs action")
Because words like "configure" appear in non-actions, a gate decides — before anything else —
whether a real change was requested. It returns one of:

| Verdict | Example | Behaviour |
|---|---|---|
| **CONFIG_ACTION** | "create VLAN 30 named FINANCE" | proceed into the config flow |
| **DEVICE_REFERENCE** | "configure C9800-L-F-K9" (a device model, no change) | "you named a device but not a change" → offers the supported actions |
| **UNKNOWN** | "asdf qwerty ???" | one clarifying question |
| **NOT_CONFIG** | "what does EOL mean" | hands control back to the router (becomes SEARCH/RAG/etc.) |

This runs inside the existing single AI call (no extra round-trip) and never affects the other tools.

#### 3.6.4 Supported configuration types (the catalog — 19)
Adding a new one is just a vetted playbook file; no code change.

| Category | Types | Example request |
|---|---|---|
| **Management** | hostname, ssh_access ⚠️, user_account, banner, save_config | `Set the hostname to CORE-RTR-01` · `Enable SSH with domain smartshift.local` |
| **Layer 2** | vlan, interface_l2, port_channel | `Create VLAN 30 named FINANCE` · `Bundle Gi0/1 and Gi0/2 into Port-channel 10 (LACP active)` |
| **Layer 3 / Routing** | interface_l3, static_route, ospf | `Configure Gi0/1 with 10.1.1.1/24` · `Add a static route to 10.10.10.0/24 via 192.168.1.254` · `Enable OSPF process 1 …` |
| **Security** | acl, aaa ⚠️ | `Create ACL BLOCK_GUEST to deny 10.20.0.0 to any` · `Configure AAA with TACACS+ server 10.0.0.30` |
| **Services** | ntp, snmp, syslog | `Configure NTP server 10.0.0.200` · `Send syslog to 10.0.0.60` |
| **Redundancy** | hsrp, vrrp ⚠️ | `Configure HSRP group 1 on Vlan10 with virtual IP 10.1.1.1` |
| **Segmentation** | vrf | `Create VRF CUSTOMER_A with route distinguisher 100:1` |

⚠️ = **high-risk** (command-template based, not idempotent): the approval summary warns and the
command suggests a `--check` dry run first.

#### 3.6.5 The kinds of questions CONFIG supports
The tool is built to handle natural, messy phrasing — not a rigid syntax:

| Style | Example | What the tool does |
|---|---|---|
| **All-in-one** | "Create VLAN 30 named FINANCE" | extracts everything; goes straight toward approval |
| **Partial** | "Create a VLAN" | opens a **form** for the missing fields (VLAN ID, name, …) |
| **Vague / ambiguous** | "I need to configure a server on the device" | asks which one, listing only **supported** actions |
| **Device-only** | "configure C9800-L-F-K9" | recognises it's a device, asks what to change (no wrong guess) |
| **Correction** | "actually make it VLAN 40" (at the summary) | updates the value; stays blocked until you approve |
| **Removal** | "delete VLAN 30" | sets the change to *absent* (the playbook removes it) |
| **Cancel** | "cancel" | discards the in-progress request |
| **Target choice** | "integrated" / "standalone" | pick a device from inventory, or supply device + credentials |
| **Automated request** | "apply it automatically" | acknowledges (automated run is not enabled yet) and returns the manual playbook |

#### 3.6.6 How fields are collected (the form)
When parameters are missing, the assistant builds a **form card** in the chat: a heading, and per
field a label, a short description, and an example. You fill it and click **Continue** (greyed
until all mandatory fields are filled), with **Clear** and **Cancel**. Passwords/keys are masked.
If a value is invalid (e.g. a VLAN ID over 4094) the form re-appears with the error. Submitting a
form sends structured values, so there's **no guessing and no extra AI cost** per turn.

#### 3.6.7 Safety properties
- **Approval gate** — nothing is delivered until you explicitly approve.
- **Vetted templates only** — the AI fills variables; it cannot invent configuration.
- **Pre-flight validation** — your values are checked against the real playbook before approval.
- **Risk flagging** — high-risk changes are clearly marked.
- **Secret handling** — device credentials are kept to the session and never shown in summaries.

#### 3.6.8 A worked example
```
You:  Create a VLAN named SERVERS
Bot:  [form] VLAN Configuration → VLAN ID* (number), VLAN Name* = SERVERS, State (present/absent)
You:  (fill VLAN ID = 30) → Continue
Bot:  Where should this run?  1) Integrated   2) Standalone
You:  1
Bot:  Which device?  1) core-sw-01 (10.0.1.1)   2) access-sw-02 (10.0.1.2)
You:  1
Bot:  [approval summary: vlan_id 30, vlan_name SERVERS, target core-sw-01, risk LOW]
You:  approve
Bot:  Here is the vetted vlan.yml playbook + the ansible-playbook command to run it.
```

---

## 4. How to run (for a demo)
```powershell
# Backend (from smartshift-ai/)
.\venv\Scripts\Activate.ps1
python -m app.app                 # http://localhost:8000  (auto-seeds the device inventory)

# UI (from smartshift-ai/ui/)
npm run dev                        # open the printed URL
```

---

## 5. Sample questions to try (whole system)

Copy-paste these into the chat. Each block exercises a different tool; the router picks the right
one automatically. **For CONFIG, one test = one conversation** (click *New Chat* between tests).

### Inventory Analyzer (SQL)
- `List all switches in Pune`
- `How many devices reach end-of-support in the next quarter?`
- `Which devices are already past EOL?`

### Knowledge Assistant (RAG)
- `What does the internal migration policy say about EOL devices?`
- `What are the prerequisites for configuring CGMP per our guide?`

### Migration Planner (HYBRID)
- `List our routers nearing EOL and recommend replacements with risk levels`
- `Which devices are urgent to replace, and what does the policy recommend?`

### Web Research (SEARCH)
- `What is end-of-life in networking?`
- `Explain the difference between HSRP and VRRP`

### Config Automation (CONFIG)
Once required fields are collected, every CONFIG flow ends the same way — the **standard tail**:
reply `1` (Integrated) → `1` (pick the first device) → `approve` (deliver the playbook + command).

**One per config type (all fields in one shot):**

| Type | Prompt |
|------|--------|
| hostname | `Set the hostname on R1 to CORE-RTR-01` |
| ssh_access ⚠️ | `Enable SSH with domain name smartshift.local` |
| user_account | `Create local user netadmin with password Demo@123 and privilege 15` |
| banner | `Set the login banner to "Authorized access only"` |
| save_config | `Save the running configuration to startup` |
| vlan | `Create VLAN 30 named FINANCE` |
| interface_l2 | `Configure GigabitEthernet0/1 as an access port in VLAN 30` |
| port_channel | `Bundle GigabitEthernet0/1 and GigabitEthernet0/2 into Port-channel 10 using LACP active` |
| interface_l3 | `Configure GigabitEthernet0/1 with IP 10.1.1.1 and prefix 24` |
| static_route | `Add a static route to 10.10.10.0/24 via 192.168.1.254` |
| ospf | `Enable OSPF process 1 for network 10.1.1.0 wildcard 0.0.0.255 in area 0` |
| acl | `Create ACL BLOCK_GUEST to deny 10.20.0.0 to any` |
| ntp | `Configure NTP server 10.0.0.200` |
| snmp | `Configure SNMP community public for host 10.0.0.50 read-only` |
| syslog | `Send syslog to 10.0.0.60 at informational level` |
| aaa ⚠️ | `Configure AAA using TACACS+ server 10.0.0.30 with key Secret123` |
| hsrp | `Configure HSRP group 1 on Vlan10 with virtual IP 10.1.1.1 priority 110` |
| vrrp ⚠️ | `Configure VRRP group 5 on Vlan20 with virtual IP 10.2.2.1` |
| vrf | `Create VRF CUSTOMER_A with route distinguisher 100:1` |

**Missing-field / form prompts (assistant opens a form for the rest):**
- `Create a VLAN named SERVERS` → asks for VLAN ID
- `Add a user called netadmin` → asks for password
- `Set up OSPF` → form with Process ID, Network, Wildcard, Area

**Edge cases:**
- **Device-only:** `configure C9800-L-F-K9` → recognises a device, asks what to change
- **Amendment at gate:** after the summary, `actually make it VLAN 40` → re-renders, stays unapproved
- **Removal:** `Delete VLAN 30` → state `absent`
- **Cancel:** `cancel` → discards the in-progress request
- **Validation:** `Create VLAN 9999 named TEST` → "VLAN ID must be between 1 and 4094"

### Chaining (works across tools)
- `list all switches in inventory` → then `show only the ones in Pune`
- `what does the policy say about EOL devices?` → then `summarize that in two bullets`

> Full CONFIG matrix (all 19 types, every edge case, form-mode checks, non-CONFIG chaining):
> [`CONFIG_INTENT_TEST_PROMPTS.md`](CONFIG_INTENT_TEST_PROMPTS.md).

---

## 6. Summary

SmartShift AI is **one chat endpoint** that routes each message to **one of five tools**:
**Inventory Analyzer** (SQL) reads the device database, **Knowledge Assistant** (RAG) answers
from internal docs, **Migration Planner** (HYBRID) combines both into a best-fit plan,
**Web Research** (SEARCH) covers general knowledge, and **Config Automation** (CONFIG) turns a
plain-English change into a **vetted, approval-gated Ansible playbook** across 19 config types.
A **File Analyzer** upload path lets users ask against their own device files. The router picks
the tool per message and remembers recent turns, so follow-ups chain across every tool. CONFIG
never writes YAML from scratch — it parameterises reviewed templates, collects parameters through
a dynamic form, pre-flight-validates them, flags high-risk changes, and only delivers after
explicit approval (manual run in v1; no device is contacted automatically).
