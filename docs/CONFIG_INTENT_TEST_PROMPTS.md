# CONFIG Intent — Sample Test Prompts

> Copy-paste prompts for exercising the CONFIG intent end-to-end via the chat UI
> (or `POST /api/v1/chat`). Covers **all 19 config types** plus edge cases.
> Companion to [`CONFIG_INTENT_PROGRESS.md`](CONFIG_INTENT_PROGRESS.md).
>
> Last updated: **2026-06-15** · Platform: Cisco IOS · Delivery: Manual (v1)

---

## How to test

- **One test = one conversation.** Click **New Chat** between tests so each starts a clean session.
- The UI persists the `session_id`, so multi-turn replies chain automatically.
- **Every flow ends the same way** once required fields are collected — the
  **"standard tail"**:

  ```
  → assistant asks: Integrated or Standalone?
  1                         (choose Integrated — pick from inventory)
  → assistant shows a numbered device list
  1                         (pick a device by number or name)
  → assistant shows the approval summary
  approve                   (deliver: playbook YAML + ansible command)
  ```

  Wherever a test says **"…then standard tail"**, run those 3 replies (`1`, `1`, `approve`).
- Watch the backend log for `Classified intent: CONFIG`, `resolved by keyword/LLM`,
  `target device picked`, and `delivery=...`.

---

## A. Happy-path prompts — one per config type

Each prompt below supplies **all required fields** in one shot, so the flow goes straight to
the target/approval tail. (Group shown = which dummy devices the picker lists.)

| # | Type | Prompt | Then |
|---|------|--------|------|
| 1 | hostname | `Set the hostname on R1 to CORE-RTR-01` | standard tail |
| 2 | ssh_access ⚠️ | `Enable SSH with domain name smartshift.local` | tail — note **HIGH-risk** warning |
| 3 | user_account | `Create local user netadmin with password Demo@123 and privilege 15` | standard tail |
| 4 | banner | `Set the login banner to "Authorized access only"` | standard tail |
| 5 | save_config | `Save the running configuration to startup` | tail (no fields needed) |
| 6 | vlan | `Create VLAN 30 named FINANCE` | tail (group: switches) |
| 7 | interface_l2 | `Configure GigabitEthernet0/1 as an access port in VLAN 30` | tail (switches) |
| 8 | port_channel | `Bundle GigabitEthernet0/1 and GigabitEthernet0/2 into Port-channel 10 using LACP active` | tail (switches) |
| 9 | interface_l3 | `Configure GigabitEthernet0/1 with IP 10.1.1.1 and prefix 24` | tail (routers) |
| 10 | static_route | `Add a static route to 10.10.10.0/24 via 192.168.1.254` | tail (routers) |
| 11 | ospf | `Enable OSPF process 1 for network 10.1.1.0 wildcard 0.0.0.255 in area 0` | tail (routers) |
| 12 | acl | `Create ACL BLOCK_GUEST to deny 10.20.0.0 to any` | tail (routers) |
| 13 | ntp | `Configure NTP server 10.0.0.200` | standard tail |
| 14 | snmp | `Configure SNMP community public for host 10.0.0.50 read-only` | standard tail |
| 15 | syslog | `Send syslog to 10.0.0.60 at informational level` | standard tail |
| 16 | aaa ⚠️ | `Configure AAA using TACACS+ server 10.0.0.30 with key Secret123` | tail — note **HIGH-risk**; key never displayed |
| 17 | hsrp | `Configure HSRP group 1 on Vlan10 with virtual IP 10.1.1.1 priority 110` | tail (group: routers) |
| 18 | vrrp ⚠️ | `Configure VRRP group 5 on Vlan20 with virtual IP 10.2.2.1` | tail (routers) — note **HIGH-risk** warning |
| 19 | vrf | `Create VRF CUSTOMER_A with route distinguisher 100:1` | tail (routers) |

> ⚠️ **HIGH-risk types** — **#2 ssh_access**, **#16 aaa**, **#18 vrrp** — render `risk: HIGH` + a
> `--check` warning in the approval summary, and the delivered command ends with
> `# high-risk: run with --check first`.
> For **#16 aaa**, the `shared_key` (like any secret) is **never shown** in the summary or the
> delivered command/inventory.

---

## B. Missing-field prompts — test consolidated collection

These omit required fields so the assistant asks for **all** outstanding fields in one message.
Provide the rest, then run the standard tail.

| Type | Start prompt | Assistant should ask for | Example reply |
|------|-------------|--------------------------|---------------|
| vlan | `Create a VLAN named SERVERS` | VLAN ID | `30` |
| user_account | `Add a user called netadmin` | password | `password Demo@123` |
| interface_l2 | `Set up switchport GigabitEthernet0/2` | mode + access VLAN | `access mode, VLAN 20` |
| interface_l3 | `Configure an IP on GigabitEthernet0/3` | IP address + prefix | `10.2.2.2 /24` |
| static_route | `Add a static route to 172.16.0.0/24` | next hop | `via 192.168.1.1` |
| ospf | `Enable OSPF process 1` | network + wildcard + area | `network 10.5.5.0 wildcard 0.0.0.255 area 0` |
| acl | `Create an ACL named WEB_FILTER` | action + source + destination | `permit tcp from any to 10.0.0.5` |
| snmp | `Set up SNMP community public` | host | `host 10.0.0.50` |
| port_channel | `Create Port-channel 20` | member interfaces + mode | `members Gi0/3 and Gi0/4, mode on` |
| aaa | `Set up AAA with a RADIUS server` | server IP + shared key | `server 10.0.0.30, key Secret123` |
| hsrp | `Configure HSRP on Vlan10` | group ID + virtual IP | `group 1, virtual IP 10.1.1.1` |
| vrrp | `Configure VRRP group 1 on Vlan20` | virtual IP | `virtual IP 10.2.2.1` |
| vrf | `Create a VRF named CUSTOMER_A` | route distinguisher | `route distinguisher 100:1` |

---

## C. Target-resolution flows

### C1 — Integrated (pick from inventory)
```
Create VLAN 40 named GUEST
1                       → choose Integrated
                          (picker lists switches: core-sw-01, access-sw-02)
2                       → pick access-sw-02
approve
```
Expect: command `target_hosts: "access-sw-02"` + a sample `inventory.ini` line; **no password shown**.

### C2 — Standalone (user-supplied device)
```
Set the hostname on a router to EDGE-09
2                       → choose Standalone
device R9, ip 10.9.9.9, user admin, password Secret123
approve
```
Expect: approval summary shows `target: R9 (10.9.9.9) [standalone]` — **password never displayed**;
delivered command/inventory line contain no password.

### C3 — Standalone, drip-fed connection details
```
Configure NTP server 10.0.0.200
standalone
the device is lab-rtr-7
ip 10.7.7.7
username admin
password Pa55w0rd
approve
```
Expect: consolidated re-asks for whatever is still missing each turn, then approval.

### C4 — Group filtering check
- `Set the hostname on R1 to X` then `1` → picker lists **all 4** devices (hostname group = `all`).
- `Create VLAN 50 named LAB` then `1` → picker lists **only the 2 switches** (vlan group = `switches`).

---

## D. Edge cases

### D1 — Disambiguation: vague request → LLM candidates
```
I need to configure a server on the device
```
Expect: "not sure which one" + a numbered candidate list (e.g. NTP / SNMP / Syslog). Then:
```
2                       → picks the 2nd candidate
```
or reply with a type name (`syslog`) or rephrase entirely.

### D2 — Disambiguation: keyword collision
```
configure the access port with an ip address
```
Expect: disambiguation between **interface_l2** and **interface_l3** (or a confident auto-resolve).
Reply `interface_l3` or `2`.

### D3 — Cumulative slot-filling (asked 2, got 1)
```
Create a VLAN named SERVERS
30                      → vlan_name SERVERS is NOT lost; only ports/ID remainder is re-asked
```
Expect: `collected` keeps `vlan_name: SERVERS` and adds `vlan_id: 30`.

### D4 — Amendment at the approval gate (gate stays closed)
```
Create VLAN 20 named GUEST
1
1
actually make it VLAN 40      → summary re-renders with vlan_id 40, NOT delivered
approve                       → now delivers with vlan_id 40
```

### D5 — Cancel mid-flow
```
Configure GigabitEthernet0/1 with IP 10.1.1.1 /24
cancel                        → "I've discarded that configuration request."
```
Next message starts fresh.

### D6 — Idempotent double-approve
```
Set the hostname on R2 to EDGE-RTR-02
1
1
approve                       → delivers
approve                       → returns the SAME result (no re-render, no double-apply)
```

### D7 — Automated execution requested (stubbed)
```
Set the hostname on R7 to LAB-RTR-07
1
1
apply it to the device for me automatically   → summary now shows delivery: AUTOMATED (NOT available yet)
approve                       → "Automated execution isn't available yet" notice + the manual playbook
```
Expect: **no device is contacted**; the manual playbook is handed back as the usable path.

### D8 — Validation errors (rejected + re-asked)
| Prompt | Bad value | Expect |
|--------|-----------|--------|
| `Create VLAN 9999 named TEST` | vlan_id 9999 > 4094 | "VLAN ID must be between 1 and 4094" → re-ask |
| `Configure GigabitEthernet0/1 with IP 999.1.1.1 prefix 24` | invalid IPv4 | "'999.1.1.1' is not a valid IPv4 address" |
| `Configure GigabitEthernet0/2 with IP 10.1.1.1 prefix 40` | prefix 40 > 32 | "subnet mask (prefix length) must be between 0 and 32" |

### D9 — Optional fields captured
```
Set the MOTD banner to "Maintenance window Sat 2am" 
```
Expect: `banner_type: motd` (optional) captured alongside required `banner_text`.
```
Create user opsadmin with password Ops@123 privilege 5
```
Expect: optional `privilege: 5` captured.

### D10 — State = absent (removal intent)
```
Delete VLAN 30
```
Expect: type vlan; optional `state: absent` captured (asks for vlan_name if not given).
Delivered command carries `state` so the playbook uses `state=deleted`.

### D11 — Endless vague input → graceful give-up
Repeatedly send vague/unanswerable text in one session (e.g. `do something`, `change it`,
`whatever`, … 8+ times). Expect: after the attempts cap the flow gives up gracefully and invites
a fresh start (rather than looping forever).

### D12 — Mid-flow topic switch
```
Create VLAN 30 named FINANCE
1
list all switches in inventory     → a clearly different (SQL) request mid-flow
```
Expect: the new request is handled; the half-filled CONFIG isn't silently completed.

---

## E. Non-CONFIG routing + chaining sanity

Confirms CONFIG didn't break the other intents and that history chaining works.

| Turn | Prompt | Expect |
|------|--------|--------|
| — | `list all switches in inventory` | routes to **SQL** |
| follow-up | `show only the ones in Pune` | resolves "the ones" via history |
| — | `what does the internal policy say about EOL devices?` | routes to **RAG** |
| follow-up | `summarize that in two bullet points` | "that" resolves to the prior answer |
| — | `what is end of life in networking?` | routes to **SEARCH** |
| follow-up | `give a real-world example of that` | "that" resolves |

---

## F. Quick smoke sequence (covers the most ground fast)

```
Set the hostname on R1 to CORE-RTR-01      # keyword detect + happy path
1
1
approve                                     # manual delivery
--- New Chat ---
Create a VLAN named SERVERS                 # missing field
30                                          # cumulative slot
2                                           # standalone
device R9, ip 10.9.9.9, user admin, password Secret123
actually make the VLAN name PROD            # amendment at gate
approve                                     # delivery (password hidden)
--- New Chat ---
I need to configure a server on the device  # disambiguation
2                                           # pick candidate
```

---

## G. Form mode (dynamic LLM-built forms)

> Requires `CONFIG_USE_FORMS=true` (default). On the **first** turn the assistant builds a
> form card (one LLM call) that extracts anything you already said and renders inputs for the
> rest. **Form submissions are structured — no LLM, no NL parsing per turn.** Collection ends
> with the **standard tail** (`1` → `1` → `approve`); target/approval are still text this round.
>
> Tip: prompts that name **no values** produce the biggest forms (all mandatory fields shown).

### Examples with MANY mandatory fields (bare prompts → full forms)

| Type | Prompt | Form shows (★ = required) |
|------|--------|---------------------------|
| ospf | `Set up OSPF` | ★Process ID (number), ★Network, ★Wildcard Mask, ★Area ID, Router ID, State (select) |
| acl | `Create an access list` | ★ACL Name, ★Action, ★Source, ★Destination, Protocol, Port, State (select) |
| port_channel | `Configure a port-channel` | ★Channel Group ID (number), ★Member Interfaces, ★Mode, State (select) |
| interface_l3 | `Configure an interface IP` | ★Interface Name, ★IP Address, ★Subnet Mask (number), Description, Admin State |
| static_route | `Add a static route` | ★Destination Network, ★Subnet Mask (number), ★Next-hop IP, Admin Distance, State |
| hsrp | `Set up HSRP` | ★Interface Name, ★Group ID (number), ★Virtual IP, Priority, Preempt, State |
| aaa ⚠️ | `Configure AAA` | ★Server IP, ★Shared Key (**masked**), ★Auth Type, Server Name, State |
| user_account | `Create a local user` | ★Username, ★Password (**masked**), Privilege, State |

### Form behaviours to verify

| # | Steps | Expect |
|---|-------|--------|
| G1 | `Create a VLAN` | Form: ★VLAN ID (number), ★VLAN Name (text), State (select). Each field has heading + short description + example placeholder. |
| G2 | In G1, leave VLAN Name blank | **Continue stays greyed/disabled** until all ★ required fields are filled. |
| G3 | In a VLAN form, enter VLAN ID `9999`, fill name, Continue | Form **re-pops** with `vlan_id` error "must be between 1 and 4094"; other values preserved; **no LLM re-call** in the log. |
| G4 | `Create VLAN 30 named FINANCE` | Pre-fill: both values were given, so the form omits them (shows only State, or proceeds straight to the target question). |
| G5 | `Create a local user` | **Password** renders as a masked input; complete + tail → approval/delivery never shows the password. |
| G6 | `Configure AAA` → complete → tail | Approval shows **risk HIGH**; **Shared Key never displayed** anywhere. |
| G7 | `Add a static route` | All three mandatory fields appear in **one** form (the old two-IP ambiguity is gone). |
| G8 | Fill some fields → **Clear** | All inputs reset to empty. |
| G9 | Open any form → **Cancel** | "I've discarded that configuration request." Next message starts fresh. |
| G10 | Any form with **State** | Rendered as a dropdown (`present` / `absent`), not a free-text box. |
| G11 | `Set up OSPF` → fill all 6 → Continue → `1` → `1` → `approve` | Full path with a large form → manual delivery. |

### Backend log signals
- First form turn → one `build_form` LLM call.
- Each **form submit** → **no** extraction LLM call (values merged structurally); only the
  `preflight` call fires once all mandatory fields are present.
- Set `CONFIG_USE_FORMS=false` to confirm graceful fallback to conversational text questions.
