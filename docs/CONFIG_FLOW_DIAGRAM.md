# CONFIG Intent — Flow Diagram (review slide)

Two formats below: **Mermaid** (renders in GitHub, VS Code, Notion, many slide tools) and an
**ASCII** fallback (paste anywhere). Both show one request flowing through the system.

---

## 1. Mermaid — full flow

```mermaid
flowchart TD
    U([User message]) --> APP["app.py · /api/v1/chat<br/>resolve session_id · load history"]
    APP --> RESUME{CONFIG flow<br/>already in progress?}
    RESUME -- yes --> H
    RESUME -- no --> CLS["router.py · classify_intent (LLM)"]
    CLS -- "SQL / RAG / SEARCH / HYBRID" --> OTHER["other chains<br/>(history injected)"]
    CLS -- CONFIG --> H["config_service.handle()"]

    H --> DONECHK{stage == DONE?}
    DONECHK -- "repeat 'approve'" --> CACHE["return cached result<br/>(idempotent)"]
    DONECHK -- "new request" --> DETQ

    DETQ{config_type<br/>known?}
    DETQ -- no --> DETECT["DETECT_TYPE<br/>keywords → LLM → confidence"]
    DETECT -- resolved --> FIELDS
    DETECT -- unsure --> DISAMB["DISAMBIGUATE<br/>show 'did you mean…' list"]
    DISAMB -. user picks .-> H
    DETQ -- yes --> FIELDS

    FIELDS["COLLECT_FIELDS<br/>extract (LLM) · validate · merge"]
    FIELDS --> MISS{all required<br/>fields present?}
    MISS -- no --> ASK["ask for ALL missing<br/>(phrased naturally)"]
    ASK -. user replies .-> H
    MISS -- yes --> TGT

    TGT{target<br/>resolved?}
    TGT -- no --> MODE["RESOLVE_TARGET<br/>Integrated or Standalone?"]
    MODE -- Integrated --> DB[("config_inventory<br/>MySQL SELECT")]
    DB --> PICK["device picker"]
    MODE -- Standalone --> CONN["collect device + login<br/>(password hidden)"]
    PICK -. user picks .-> H
    CONN -. user replies .-> H
    TGT -- yes --> APPR

    APPR{approved?}
    APPR -- no --> SUMMARY["CONFIRM_APPROVAL<br/>show summary · wait"]
    SUMMARY -. "user: approve" .-> H
    APPR -- yes --> DELIVER["DELIVER<br/>read vetted playbook file<br/>build ansible -e command"]
    DELIVER --> DONE(["return playbook + command<br/>stage = DONE · cache"])

    classDef stage fill:#e8f0fe,stroke:#4285f4,color:#000;
    classDef io fill:#e6f4ea,stroke:#34a853,color:#000;
    classDef store fill:#fef7e0,stroke:#f9ab00,color:#000;
    class DETECT,DISAMB,FIELDS,MODE,CONN,PICK,SUMMARY,DELIVER stage;
    class U,DONE,CACHE io;
    class DB store;
```

---

## 2. Mermaid — condensed (cleaner for a single slide)

```mermaid
flowchart LR
    U([User]) --> C{classify<br/>or resume}
    C -- CONFIG --> D[1 · DETECT<br/>what to configure]
    D --> F[2 · COLLECT<br/>ask missing fields]
    F --> T[3 · TARGET<br/>pick device · DB]
    T --> A[4 · APPROVE<br/>summary + gate]
    A --> R[5 · DELIVER<br/>playbook + command]
    R --> Z([Done])
    F -. still missing .-> F
    A -. edit .-> A
```

---

## 3. ASCII fallback

```
                         ┌─────────────────────────────┐
   User message ───────► │ app.py  /api/v1/chat         │
                         │  • session_id  • load history│
                         └───────────────┬──────────────┘
                                         ▼
                            CONFIG already in progress?
                              │ yes               │ no
                              ▼                   ▼
                              │           router.py: classify_intent
                              │             │CONFIG     │ SQL/RAG/SEARCH/HYBRID
                              │             ▼                   ▼
                              └────────►  config_service.handle()   other chains (+history)
                                              │
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        ▼                                                                             │
  ┌───────────────┐  unsure   ┌──────────────┐                                       │
  │ 1. DETECT     │ ────────► │ DISAMBIGUATE │ ──"did you mean…"── user picks ───────►┤
  │ type?         │           └──────────────┘                                       │
  │ keyword→LLM   │ resolved                                                          │
  └──────┬────────┘                                                                   │
         ▼                                                                            │
  ┌───────────────┐  missing  ┌───────────────────────┐                              │
  │ 2. COLLECT    │ ────────► │ ask for ALL missing    │ ── user replies ────────────►┤
  │ extract+valid │           │ (cumulative, phrased)  │                              │
  └──────┬────────┘  complete └───────────────────────┘                              │
         ▼                                                                            │
  ┌───────────────┐           ┌──────────────────────────┐                           │
  │ 3. TARGET     │ Integrated│  config_inventory (MySQL) │ → device picker ──────────►┤
  │ mode?         │ ──────────►  SELECT … FROM …           │                           │
  │               │ Standalone│  collect device+login     │ (password hidden) ────────►┤
  └──────┬────────┘           └──────────────────────────┘                           │
         ▼                                                                            │
  ┌───────────────┐  not yet  ┌───────────────────────┐                              │
  │ 4. APPROVE    │ ────────► │ show summary · WAIT    │ ── "approve" ───────────────►┘
  │ gate          │           │ (edits re-open gate)   │
  └──────┬────────┘ approved  └───────────────────────┘
         ▼
  ┌─────────────────────────────────────────────┐
  │ 5. DELIVER                                   │
  │  • read vetted playbook FILE from registry   │
  │  • build  ansible-playbook … -e '{vars}'     │
  │  • return playbook + command   (no device    │
  │    is contacted — manual mode)               │
  └──────────────────┬──────────────────────────┘
                     ▼
              stage = DONE · cache result
          (repeat "approve" → returns cached, no re-apply)
```

---

## 4. One-line legend for the slide

> **DETECT → COLLECT → TARGET → APPROVE → DELIVER** — a 5-step refinement loop.
> Each step either advances or asks one question and waits. Nothing runs on a device:
> the output is a vetted playbook + the exact command to run it.
