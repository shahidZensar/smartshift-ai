"""
ConfigService — the CONFIG-intent state machine (CONFIG_INTENT_PLAN.md §6).

Per-turn contract:  handle(message, session_id) -> response dict (additive fields
merged into the /api/v1/chat JSON). State is persisted in the conversation_store
between turns, so the flow is multi-turn and idempotent.

Scope (step 1 — manual delivery vertical slice):
  DETECT_TYPE (keyword -> LLM fallback -> DISAMBIGUATE)
  -> COLLECT_FIELDS (consolidated, cumulative, validated)
  -> CONFIRM_APPROVAL (full gate)
  -> DELIVER (manual: vetted playbook + ready-to-run ansible command)

Deferred to later steps: RESOLVE_TARGET / config_inventory device picker, and the
automated ansible-runner branch.
"""
import re
import json
import hashlib
from typing import Any, Optional

from .. import logger
from ..models import ConfigState, ConfigStage
from ..config_registry import config_registry, ConfigTypeSpec, FieldMeta
from ..config import CONFIG_LLM_PHRASING, CONFIG_LLM_PREFLIGHT, CONFIG_USE_FORMS
from .. import config_inventory
from ..chains.config_chain import (
    detect_type, extract_fields, extract_connection, phrase_question, preflight_validate, build_form,
    GATE_ROUTES,
)
from .conversation_store import conversation_store

MAX_ATTEMPTS = 8
# Confidence bands for the LLM type-detection fallback (§8):
#   >= HIGH on a keyword collision  -> trust the LLM's pick among the colliding types
#   >= LOW  with no keyword hit      -> resolve directly
#   below LOW / no pick              -> DISAMBIGUATE with candidates
DETECT_CONFIDENCE_LOW = 0.6
DETECT_CONFIDENCE_HIGH = 0.8
MAX_DISAMBIG_CANDIDATES = 4
INVENTORY_FILE = "inventory.ini"

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


# ---------------------------------------------------------------------------
# small intent helpers
# ---------------------------------------------------------------------------
_APPROVE_WORDS = {"approve", "approved", "yes", "confirm", "confirmed", "go ahead", "proceed", "ok", "okay", "do it"}
_CANCEL_WORDS = {"cancel", "abort", "stop", "discard", "nevermind", "never mind", "forget it"}
_AUTOMATED_PHRASES = ("automatically", "automated", "apply it for me", "apply it to the device",
                      "push it for me", "run it for me", "run it on the device", "do it for me on")

# Connection fields, described once as FieldMeta so they reuse the same validation and
# form-widget machinery as config fields. The password carries secret=True so it renders
# as a masked input (frontend) and is redacted in every echo/log (backend).
_CONN_FIELD_METAS: list[FieldMeta] = [
    FieldMeta(name="device_name", required=True,
              prompt="What name/hostname identifies the device?", example="core-rtr-01"),
    FieldMeta(name="ansible_host", required=True,
              prompt="What is the management IP address?", example="10.0.0.1", validate_as="ipv4"),
    FieldMeta(name="username", required=True,
              prompt="What login username should be used?", example="netadmin"),
    FieldMeta(name="password", required=True,
              prompt="What is the login password? (used only this session, never stored or logged)",
              example="Demo@123", secret=True),
]
_CONN_META = {m.name: m for m in _CONN_FIELD_METAS}
# Standalone supplies everything incl. credentials. Integrated reads credentials securely
# from inventory, so it only ever asks for connectivity fields the inventory row is missing.
_STANDALONE_CONN_FIELDS = ["device_name", "ansible_host", "username", "password"]
_INTEGRATED_CONN_FIELDS = ["device_name", "ansible_host", "username"]


def _is_approve(message: str) -> bool:
    m = (message or "").strip().lower().rstrip(".!")
    return m in _APPROVE_WORDS or m.startswith("approve")


def _is_cancel(message: str) -> bool:
    m = (message or "").strip().lower().rstrip(".!")
    return m in _CANCEL_WORDS


def _wants_automated(message: str) -> bool:
    m = (message or "").strip().lower()
    return any(p in m for p in _AUTOMATED_PHRASES)


# ---------------------------------------------------------------------------
# field validation / normalisation
# ---------------------------------------------------------------------------
def _validate(meta: FieldMeta, value: Any) -> tuple[bool, Any, Optional[str]]:
    """Return (ok, normalized_value, error_message)."""
    v = value
    kind = meta.validate_as
    try:
        if kind == "int":
            return True, int(str(v).strip()), None
        if kind == "vlan_id":
            n = int(str(v).strip())
            if not (1 <= n <= 4094):
                return False, v, "VLAN ID must be between 1 and 4094"
            return True, n, None
        if kind == "prefix":
            n = int(str(v).strip())
            if not (0 <= n <= 32):
                return False, v, "subnet mask (prefix length) must be between 0 and 32"
            return True, n, None
        if kind == "ipv4":
            parts = str(v).strip().split(".")
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return False, v, f"'{v}' is not a valid IPv4 address"
            return True, str(v).strip(), None
        if kind == "list":
            if isinstance(v, list):
                items = v
            else:
                items = [s.strip() for s in str(v).replace(";", ",").split(",") if s.strip()]
            return True, items, None
        if kind == "state":
            s = str(v).strip().lower()
            if s not in ("present", "absent"):
                return False, v, "value must be 'present' or 'absent'"
            return True, s, None
    except (ValueError, TypeError):
        return False, v, f"'{v}' is not a valid value for {meta.name}"
    # no validator -> accept as-is (string)
    return True, v, None


def _merge_and_validate(spec: ConfigTypeSpec, collected: dict, extracted: dict) -> tuple[dict, dict]:
    """Merge extracted values onto collected (new overrides), validating each.

    Returns (merged_collected, errors) where errors maps field -> message for any
    value that failed validation (the bad value is NOT stored)."""
    merged = dict(collected)
    errors: dict[str, str] = {}
    for field, value in (extracted or {}).items():
        meta = spec.field_meta(field)
        ok, norm, err = _validate(meta, value)
        if ok:
            merged[field] = norm
        else:
            errors[field] = err or f"invalid value for {field}"
    return merged, errors


# ---------------------------------------------------------------------------
# rendering (manual delivery)
# ---------------------------------------------------------------------------
def _devices(state: ConfigState) -> list[dict]:
    """The resolved target device(s) as a list. Prefers the multi-device list; falls back
    to the single `target_device` (so all single-device behaviour is unchanged)."""
    if state.target_devices:
        return list(state.target_devices)
    if state.target_device:
        return [state.target_device]
    return []


def _target_hosts(spec: ConfigTypeSpec, state: ConfigState) -> str:
    """The Ansible host pattern: the chosen device(s) if any, else the mapping group.
    Multiple devices render as a comma-separated pattern (a valid Ansible host pattern)."""
    names = [d["device_name"] for d in _devices(state) if d.get("device_name")]
    if names:
        return ",".join(names)
    return spec.target_group


def _extra_vars(spec: ConfigTypeSpec, state: ConfigState) -> dict:
    """Extra-vars payload: collected fields + resolved target_hosts."""
    ev: dict[str, Any] = {"target_hosts": _target_hosts(spec, state)}
    ev.update(state.collected)
    return ev


def _inventory_line(state: ConfigState) -> Optional[str]:
    """Sample inventory.ini line(s) for the chosen device(s) (password never written).
    One line per device; returns None if no device has the minimum connectivity fields."""
    lines: list[str] = []
    for td in _devices(state):
        if not td.get("device_name") or not td.get("ansible_host"):
            continue
        parts = [td["device_name"], f"ansible_host={td['ansible_host']}"]
        if td.get("username"):
            parts.append(f"ansible_user={td['username']}")
        parts.append("ansible_network_os=cisco.ios.ios")
        lines.append(" ".join(parts))
    return "\n".join(lines) if lines else None


def _playbook_text(spec: ConfigTypeSpec) -> str:
    """The vetted playbook YAML (used as grounding for the LLM pre-flight)."""
    if spec.playbook_file:
        try:
            with open(spec.playbook_file, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError as exc:
            logger.error("Could not read playbook %r: %s", spec.playbook_file, exc)
    return ""


def _preflight_message(issues: list[str]) -> str:
    lines = ["Before I prepare this change, a few things need attention:"]
    for i in issues:
        lines.append(f"  • {i}")
    lines.append("")
    lines.append("Please correct these and resend.")
    return "\n".join(lines)


def _render_manual(spec: ConfigTypeSpec, state: ConfigState) -> dict:
    """Produce the manual-delivery payload: the vetted playbook (unchanged) plus the
    ready-to-run ansible-playbook command with collected values as extra-vars."""
    extra_vars = _extra_vars(spec, state)
    extra_vars_json = json.dumps(extra_vars)
    playbook_path = spec.playbook_rel or spec.playbook_name
    command = (
        f"ansible-playbook -i {INVENTORY_FILE} {playbook_path} "
        f"-e '{extra_vars_json}'"
    )
    if spec.risk == "high":
        command += "  # high-risk: run with --check first"

    playbook_yaml = ""
    if spec.playbook_file:
        try:
            with open(spec.playbook_file, "r", encoding="utf-8") as fh:
                playbook_yaml = fh.read()
        except OSError as exc:
            logger.error("Could not read playbook %r: %s", spec.playbook_file, exc)
    return {
        "command": command,
        "extra_vars": extra_vars,
        "playbook_yaml": playbook_yaml,
        "inventory_line": _inventory_line(state),
    }


def _signature(config_type: str, collected: dict) -> str:
    payload = json.dumps({"t": config_type, "c": collected}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# response builder
# ---------------------------------------------------------------------------
def _resp(answer: str, state: ConfigState, awaiting: str, extra: Optional[dict] = None) -> dict:
    payload = {
        "answer": answer,
        "intent": "CONFIG",
        "stage": state.stage.value,
        "config_type": state.config_type,
        "collected": _redact(state),
        "missing_fields": state.missing_fields,
        "delivery_mode": state.delivery_mode,
        "target_device": _redact_target(state),
        "target_devices": _redact_targets(state),
        "awaiting": awaiting,
    }
    if extra:
        payload.update(extra)
    return payload


def _redact(state: ConfigState) -> dict:
    """Hide secret field values (e.g. passwords) in the echoed `collected`."""
    if not state.config_type:
        return dict(state.collected)
    spec = config_registry.get(state.config_type)
    out = {}
    for k, v in state.collected.items():
        if spec and spec.field_meta(k).secret:
            out[k] = "***"
        else:
            out[k] = v
    return out


def _mask_conn(td: dict) -> dict:
    """Mask secret connection fields (e.g. password) in a single device dict."""
    return {k: ("***" if _CONN_META.get(k, FieldMeta(name=k, required=False, prompt="")).secret else v)
            for k, v in (td or {}).items()}


def _redact_target(state: ConfigState) -> Optional[dict]:
    """The single/primary device, safe to echo (password masked). Back-compat field."""
    devs = _devices(state)
    return _mask_conn(devs[0]) if devs else None


def _redact_targets(state: ConfigState) -> Optional[list]:
    """All resolved device(s), safe to echo (passwords masked)."""
    devs = _devices(state)
    return [_mask_conn(d) for d in devs] if devs else None


# ---------------------------------------------------------------------------
# dynamic form (LLM-built copy, grounded to the registry contract)
# ---------------------------------------------------------------------------
def _widget_type(meta: FieldMeta) -> str:
    """Input widget for a field, derived from its validator (backend-owned)."""
    if meta.secret:
        return "password"
    if meta.validate_as in ("int", "vlan_id", "prefix"):
        return "number"
    if meta.validate_as == "state":
        return "select"
    return "text"


def _build_form(spec: ConfigTypeSpec, state: ConfigState, missing: list[str], errors: dict[str, str]) -> dict:
    """Assemble the form card: LLM copy (cached) reconciled with the registry contract.

    Shows fields not yet collected (required + optional), plus any that failed validation.
    Field order follows the registry (required first, then optional). The LLM never adds,
    drops, or types fields — it only supplies headings/descriptions/examples."""
    copy = (state.form_cache or {}).get("fields", {})       # {name: {heading, description, example}}
    title = (state.form_cache or {}).get("title") or f"{spec.config_type.replace('_', ' ').title()} Configuration"
    description = (state.form_cache or {}).get("description") or ""

    # Fields to show: required+optional that aren't validly collected yet (errors included
    # since invalid values are not stored), in registry order.
    show = [f for f in (spec.required_fields + spec.optional_fields) if f not in state.collected]
    fields = []
    for fname in show:
        meta = spec.field_meta(fname)
        c = copy.get(fname, {})
        field = {
            "name": fname,
            "heading": c.get("heading") or fname.replace("_", " ").title(),
            "description": c.get("description") or meta.prompt,
            "example": c.get("example") or meta.example,
            "type": _widget_type(meta),
            "required": fname in spec.required_fields,
            "value": None,
            "error": errors.get(fname),
        }
        if field["type"] == "select":
            field["options"] = ["present", "absent"]
        fields.append(field)

    return {
        "title": title,
        "description": description,
        "fields": fields,
        "actions": {"submit": "Continue", "clear": "Clear", "cancel": "Cancel"},
    }


def _merge_conn(conn: dict, values: dict, fields: list[str]) -> tuple[dict, dict]:
    """Merge connection values (form submission or NL extraction) onto `conn`, validating
    each against its FieldMeta. Returns (merged_conn, errors); bad values are not stored."""
    merged = dict(conn)
    errors: dict[str, str] = {}
    for f, v in (values or {}).items():
        if f not in fields or v in (None, "", []):
            continue
        ok, norm, err = _validate(_CONN_META[f], v)
        if ok:
            merged[f] = norm
        else:
            errors[f] = err or f"invalid value for {f}"
    return merged, errors


def _merge_conn_list(rows: list, fields: list[str]) -> tuple[list[dict], dict[int, dict]]:
    """Validate a list of connection rows (multi-device standalone submission), NO LLM.

    Returns (validated_rows, row_errors) where row_errors maps a row index to a
    {field: message} dict for any row that has an invalid OR missing required field.
    A row that is entirely empty is skipped (lets the client leave a trailing blank row)."""
    validated: list[dict] = []
    row_errors: dict[int, dict] = {}
    for row in (rows or []):
        row = row or {}
        if not any(str(row.get(f, "")).strip() for f in fields):
            continue  # blank row -> ignore
        conn, errs = _merge_conn({}, row, fields)
        for f in fields:
            if not conn.get(f) and f not in errs:
                errs[f] = "required"
        if errs:
            row_errors[len(validated)] = errs
        validated.append(conn)
    return validated, row_errors


def _build_connection_form(state: ConfigState, missing: list[str], errors: dict[str, str],
                           mode: str, fields: list[str]) -> dict:
    """Form card for the target's connection details — same shape/widgets as the config
    form so the frontend renders it identically (password -> masked input)."""
    show = [f for f in fields if f in missing or f in errors]
    field_cards = []
    for fname in show:
        meta = _CONN_META[fname]
        field_cards.append({
            "name": fname,
            "heading": fname.replace("_", " ").title(),
            "description": meta.prompt,
            "example": meta.example,
            "type": _widget_type(meta),       # password -> masked input on the client
            "required": True,
            "value": None,                    # secrets/values are never pre-filled into the form
            "error": errors.get(fname),
        })
    if mode == "standalone":
        title = "Device Connection (Standalone)"
        description = ("Provide the device's connection details. Credentials are used only "
                       "for this session — never stored or logged.")
    else:
        dev = (_devices(state)[0] if _devices(state) else {}).get("device_name", "this device")
        title = "Complete Device Details"
        description = (f"Some connection details for **{dev}** are missing from the inventory. "
                       "Please provide them to continue.")
    return {
        "title": title,
        "description": description,
        "fields": field_cards,
        "actions": {"submit": "Continue", "clear": "Clear", "cancel": "Cancel"},
    }


def _build_multi_connection_form(row_errors: dict[int, dict]) -> dict:
    """Repeatable standalone connection form: one row template the client renders 1..N
    times. Same widgets/masking as the single form (password -> masked). Values are never
    pre-filled by the backend; the client retains its own rows across re-validation."""
    field_template = []
    for fname in _STANDALONE_CONN_FIELDS:
        meta = _CONN_META[fname]
        field_template.append({
            "name": fname,
            "heading": fname.replace("_", " ").title(),
            "description": meta.prompt,
            "example": meta.example,
            "type": _widget_type(meta),       # password -> masked input on the client
            "required": True,
        })
    return {
        "title": "Device Connections (Standalone)",
        "description": ("Add one or more devices — the same configuration is applied to "
                        "each. Credentials are used only for this session, never stored or logged."),
        "repeatable": True,
        "form_kind": "connection_multi",
        "fields": field_template,
        "row_errors": {str(k): v for k, v in (row_errors or {}).items()},
        "actions": {"submit": "Continue", "addRow": "Add device",
                    "removeRow": "Remove", "clear": "Clear", "cancel": "Cancel"},
    }


# ---------------------------------------------------------------------------
# message composers
# ---------------------------------------------------------------------------
def _collect_message(spec: ConfigTypeSpec, missing: list[str], errors: dict[str, str]) -> str:
    lines = []
    if errors:
        lines.append("A couple of values need fixing:")
        for f, err in errors.items():
            lines.append(f"  • {f}: {err}")
        lines.append("")
    asks = missing or list(errors.keys())
    if len(asks) == 1:
        meta = spec.field_meta(asks[0])
        eg = f" (e.g. {meta.example})" if meta.example else ""
        lines.append(f"{meta.prompt}{eg}")
    else:
        lines.append(f"To configure **{spec.config_type}**, I still need:")
        for f in asks:
            meta = spec.field_meta(f)
            eg = f" — e.g. {meta.example}" if meta.example else ""
            lines.append(f"  • {meta.prompt}{eg}")
    return "\n".join(lines)


def _target_summary(state: ConfigState) -> str:
    """One-line description of the resolved target(s) (password never shown)."""
    mode = state.target_mode or "?"
    devs = _devices(state)
    if not devs:
        return mode
    names = []
    for td in devs:
        host = f" ({td['ansible_host']})" if td.get("ansible_host") else ""
        names.append(f"{td.get('device_name', '?')}{host}")
    label = names[0] if len(names) == 1 else f"{len(names)} devices: " + ", ".join(names)
    return f"{label}  [{mode}]"


def _approval_summary(spec: ConfigTypeSpec, state: ConfigState) -> str:
    delivery = state.delivery_mode.upper()
    delivery_note = ("I'll return the playbook + command for you to run"
                     if state.delivery_mode == "manual"
                     else "the system would run it against the target (NOT available yet)")
    lines = [f"Ready to prepare a **{spec.config_type}** configuration:"]
    lines.append(f"  • config_type   : {spec.config_type}")
    for f in spec.required_fields:
        if f in state.collected:
            meta = spec.field_meta(f)
            val = "***" if meta.secret else state.collected[f]
            lines.append(f"  • {f:<14}: {val}")
    for f in spec.optional_fields:
        if f in state.collected:
            meta = spec.field_meta(f)
            val = "***" if meta.secret else state.collected[f]
            lines.append(f"  • {f:<14}: {val}  (optional)")
    lines.append(f"  • target        : {_target_summary(state)}")
    lines.append(f"  • template      : {spec.playbook_name}")
    lines.append(f"  • delivery      : {delivery} → {delivery_note}")
    lines.append(f"  • risk          : {spec.risk.upper()}")
    if spec.risk == "high":
        lines.append("")
        lines.append("⚠️  This is a HIGH-RISK change (command-template based, not idempotent). "
                     "Run it with `--check` first.")
    if state.preflight_warnings:
        lines.append("")
        lines.append("Heads-up (pre-flight):")
        for w in state.preflight_warnings:
            lines.append(f"  • {w}")
    lines.append("")
    lines.append('Reply "approve" to proceed, or tell me what to change.')
    return "\n".join(lines)


def _delivery_message(spec: ConfigTypeSpec, state: ConfigState, rendered: dict) -> str:
    parts = [
        f"Here is the vetted **{spec.config_type}** playbook and the command to run it.",
        "",
        "**Run this:**",
        "```bash",
        rendered["command"],
        "```",
    ]
    if rendered.get("inventory_line"):
        parts += [
            "",
            f"**Sample `{INVENTORY_FILE}` line** (add your password via vault/prompt — never store it):",
            "```ini",
            rendered["inventory_line"],
            "```",
        ]
    parts += [
        "",
        f"**Playbook ({spec.playbook_name}):**",
        "```yaml",
        rendered["playbook_yaml"].rstrip(),
        "```",
        "",
        f"Target: `{_target_summary(state)}` · Risk: `{spec.risk}`. "
        f"No device was contacted (manual mode).",
    ]
    return "\n".join(parts)


def _automated_notice() -> str:
    """Automated mode is wired but not built yet (§10.1, decision L). We show the
    coming-soon notice and still hand back the manual playbook as the usable path —
    no `ansible-playbook` is ever run against a device in v1."""
    return ("⚙️ **Automated execution isn't available yet** — I won't run "
            "`ansible-playbook` against the device in this version. "
            "Here's the manual playbook so you can run it yourself:\n")


# ---------------------------------------------------------------------------
# the service
# ---------------------------------------------------------------------------
class ConfigService:

    def _history_text(self, session_id: str) -> str:
        turns = conversation_store.recent(session_id)
        # Exclude the just-appended current user turn handled by caller ordering.
        return "\n".join(f"{t.role}: {t.content}" for t in turns) or ""

    def _phrase(self, text: str) -> str:
        """Optionally polish a follow-up so it reads naturally (§6, decision C)."""
        if CONFIG_LLM_PHRASING:
            return phrase_question(text)
        return text

    # ----- target resolution (§10.2) -----
    def _resolve_target(self, message: str, state: ConfigState, spec: ConfigTypeSpec,
                        form_values: Optional[dict] = None, device_rows: Optional[list] = None):
        """Drive RESOLVE_TARGET one step per turn. Returns a response dict while more
        input is needed, or None once the target is fully resolved.

        `device_rows` carries a multi-device standalone submission (the repeatable form's
        `devices` list); single-device and integrated targeting ignore it."""
        m = (message or "").strip().lower()

        # 1) choose the mode (Integrated vs Standalone) — no fixed default (decision J).
        if state.target_mode is None:
            if state.stage == ConfigStage.RESOLVE_TARGET:
                state.target_mode = self._parse_mode(m)
            if state.target_mode is None:
                return _resp(self._target_mode_question(), state, "choose_target_mode")
            just_set_mode = True  # don't read this same reply as a device/connection answer
        else:
            just_set_mode = False

        # 2) integrated -> pick a device from config_inventory, then fill any connection
        #    fields the inventory row is missing (asked via the same form mechanism).
        if state.target_mode == "integrated":
            if state.target_device is None and not state.target_devices:
                devices = config_inventory.list_devices(spec.target_group) or config_inventory.list_devices()
                if not just_set_mode:
                    picked = self._resolve_devices(message, devices)
                    if len(picked) == 1:
                        # single pick -> existing path (allows per-device field completion below).
                        state.target_device = picked[0].public()  # password never stored here
                        logger.info("CONFIG target device picked: %r", picked[0].device_name)
                    elif len(picked) > 1:
                        # multi-select: integrated creds come from inventory, so we require
                        # complete records rather than prompting per device.
                        rows = [p.public() for p in picked]
                        incomplete = [r.get("device_name", "?") for r in rows
                                      if any(not r.get(f) for f in _INTEGRATED_CONN_FIELDS)]
                        if incomplete:
                            return _resp(self._incomplete_devices_message(incomplete, devices, spec),
                                         state, "choose_device")
                        state.target_devices = rows
                        logger.info("CONFIG target devices picked: %s",
                                    [r.get("device_name") for r in rows])
                if state.target_device is None and not state.target_devices:
                    return _resp(self._device_picker_question(devices, spec), state, "choose_device")

            # multi-device integrated rows are complete by construction -> nothing more to ask.
            if state.target_devices:
                return None

            # apply user-supplied values only once we've started asking for missing fields
            # (so the device-pick reply itself is never read as a field value).
            conn = dict(state.target_device or {})
            errors: dict[str, str] = {}
            if state.target_filling and not just_set_mode:
                values = form_values if form_values else extract_connection(message, conn)
                conn, errors = _merge_conn(conn, values, _INTEGRATED_CONN_FIELDS)
                state.target_device = conn
            missing = [f for f in _INTEGRATED_CONN_FIELDS if not conn.get(f)]
            if missing or errors:
                state.target_filling = True
                return self._connection_response(state, missing, errors, "integrated")
            state.target_filling = False
            return None

        # 3) standalone -> collect connection details (transient, session-only).
        #    Forms on: a repeatable form gathers 1..N devices in a single submission
        #    (structured merge, NO LLM). Forms off: single-device free-text (unchanged).
        if state.target_mode == "standalone":
            if CONFIG_USE_FORMS:
                row_errors: dict[int, dict] = {}
                if not just_set_mode and device_rows is not None:
                    validated, row_errors = _merge_conn_list(device_rows, _STANDALONE_CONN_FIELDS)
                    if not row_errors and validated:
                        state.target_devices = validated
                devices = _devices(state)
                complete = bool(devices) and all(
                    all(d.get(f) for f in _STANDALONE_CONN_FIELDS) for d in devices)
                if row_errors or not complete:
                    return self._standalone_form_response(state, row_errors)
                return None

            # forms off: single-device, free-text extraction (existing behaviour, unchanged).
            conn = dict(state.target_device or {})
            errors: dict[str, str] = {}
            if not just_set_mode:
                values = extract_connection(message, conn)
                conn, errors = _merge_conn(conn, values, _STANDALONE_CONN_FIELDS)
                state.target_device = conn
            missing = [f for f in _STANDALONE_CONN_FIELDS if not conn.get(f)]
            if missing or errors:
                return self._connection_response(state, missing, errors, "standalone")
            return None

        return None

    def _connection_response(self, state: ConfigState, missing: list[str],
                             errors: dict[str, str], mode: str) -> dict:
        """Ask for the missing/invalid connection fields — as a form when forms are on,
        else as a plain-text question (both paths mask the password)."""
        fields = _STANDALONE_CONN_FIELDS if mode == "standalone" else _INTEGRATED_CONN_FIELDS
        asks = missing or list(errors.keys())
        if CONFIG_USE_FORMS:
            form = _build_connection_form(state, missing, errors, mode, fields)
            return _resp(self._connection_question(asks), state, "form", extra={"form": form})
        return _resp(self._phrase(self._connection_question(asks)), state, "user_input")

    def _standalone_form_response(self, state: ConfigState, row_errors: dict[int, dict]) -> dict:
        """Render the repeatable standalone connection form (1..N devices, no LLM)."""
        form = _build_multi_connection_form(row_errors)
        if row_errors:
            msg = "Some device rows need fixing — please correct the highlighted fields."
        else:
            msg = ("Add the device(s) this should run on — you can add more than one, and the "
                   "same configuration is applied to each. Credentials are used only for this "
                   "session and are never stored or logged.")
        return _resp(msg, state, "form", extra={"form": form})

    def _parse_mode(self, m: str) -> Optional[str]:
        if any(w in m for w in ("standalone", "myself", "provide", "supply", "manual creds")) or m.strip() == "2":
            return "standalone"
        if any(w in m for w in ("integrated", "inventory", "pick", "from the list")) or m.strip() == "1":
            return "integrated"
        return None

    def _resolve_devices(self, message: str, devices: list) -> list:
        """Resolve one OR MORE inventory devices from a picker reply:
          • numeric multi-select — '1,3,5', '1 and 3', '2' (indices >9 supported);
          • device name / management IP (one or several substrings).
        Returns the matched devices in selection order (empty list if none matched)."""
        m = (message or "").strip().lower()
        picked: list = []

        # numeric pick — only when the reply is essentially just numbers/separators, so a
        # rephrased sentence containing a digit is never misread as a selection.
        mm = m.replace(" and ", ",").replace("&", ",")
        if mm and re.fullmatch(r"[\d,\s]+", mm):
            for n in re.findall(r"\d+", mm):
                idx = int(n) - 1
                if 0 <= idx < len(devices) and devices[idx] not in picked:
                    picked.append(devices[idx])
            if picked:
                return picked

        # name / IP match (may select several). Guard against blank inventory fields:
        # "" in m is always True, which would make an incomplete row match every reply.
        for d in devices:
            if (d.device_name and d.device_name.lower() in m) or (d.ansible_host and d.ansible_host in m):
                if d not in picked:
                    picked.append(d)
        return picked

    def _incomplete_devices_message(self, names: list[str], devices: list,
                                    spec: ConfigTypeSpec) -> str:
        """Picker re-prompt when a multi-select includes devices missing inventory creds."""
        lines = [
            "Some of those devices don't have complete connection details in the inventory: "
            + ", ".join(names) + ".",
            "For multi-device targeting I use the inventory's stored credentials, so please "
            "select devices that have complete records — or pick a single device and I'll help "
            "you fill in what's missing.",
            "",
            self._device_picker_question(devices, spec),
        ]
        return "\n".join(lines)

    def _target_mode_question(self) -> str:
        return "\n".join([
            "Where should this run? Pick how I should target the device:",
            "  1. **Integrated** — choose a device from the inventory (credentials are read securely, never typed)",
            "  2. **Standalone** — you give me the device name, IP, username, and password",
            "",
            "Reply `1`/`integrated` or `2`/`standalone`.",
        ])

    def _device_picker_question(self, devices: list, spec: ConfigTypeSpec) -> str:
        lines = [f"Which device should this target? (group: **{spec.target_group}**)"]
        for i, d in enumerate(devices, 1):
            lines.append(f"  {i}. {d.device_name} ({d.ansible_host}) — {d.platform}")
        lines.append("")
        lines.append("Reply with the number or the device name. To target several at once, "
                     "list them (e.g. `1,3` or `1 and 3`).")
        return "\n".join(lines)

    def _connection_question(self, missing_conn: list[str]) -> str:
        if len(missing_conn) == 1:
            meta = _CONN_META[missing_conn[0]]
            eg = f" (e.g. {meta.example})" if meta.example else ""
            return f"{meta.prompt}{eg}"
        lines = ["To reach the device, I still need:"]
        for f in missing_conn:
            meta = _CONN_META[f]
            eg = f" — e.g. {meta.example}" if meta.example else ""
            lines.append(f"  • {meta.prompt}{eg}")
        return "\n".join(lines)

    def handle(self, message: str, session_id: str, form_values: Optional[dict] = None) -> dict:
        state = conversation_store.get_config_state(session_id)
        if state is None:
            state = ConfigState()

        # ---- a finished flow: idempotent re-send vs brand-new request ----
        if state.stage == ConfigStage.DONE:
            if _is_approve(message) and state.last_result:
                logger.info("CONFIG idempotent re-send for session %r", session_id)
                return state.last_result
            # Start fresh, but carry the last completed delivery (signature + result)
            # so an identical repeat request returns the cache instead of looping the
            # user back through target/approval (see the duplicate short-circuit below).
            prev_sig, prev_result = state.last_executed_signature, state.last_result
            state = ConfigState()
            state.last_executed_signature = prev_sig
            state.last_result = prev_result

        state.attempts += 1
        history = self._history_text(session_id)

        # ---- cancel any time ----
        if _is_cancel(message) and state.config_type:
            conversation_store.clear_config_state(session_id)
            state.stage = ConfigStage.DONE
            return _resp("Okay, I've discarded that configuration request.", state, "none")

        # ---- delivery mode: the user may ask for automated execution at any point ----
        if _wants_automated(message):
            state.delivery_mode = "automated"

        # ---- attempts cap (graceful give-up) ----
        if state.attempts > MAX_ATTEMPTS:
            conversation_store.clear_config_state(session_id)
            state.stage = ConfigStage.DONE
            return _resp(
                "I'm having trouble pinning down this configuration. Let's start over — "
                "tell me what you'd like to change (e.g. \"create VLAN 30 named FINANCE\").",
                state, "none",
            )

        # ---- 1. detect config_type ----
        if not state.config_type:
            # If we previously offered candidates, try to resolve the reply against
            # them (numeric / ordinal / type-name / keyword pick) before re-detecting.
            if state.stage == ConfigStage.DISAMBIGUATE and state.candidates:
                picked = self._resolve_choice(message, state.candidates)
                if picked:
                    logger.info("CONFIG type resolved by disambiguation pick: %r", picked)
                    state.config_type = picked
                    state.candidates = []

            if not state.config_type:
                route, ctype, candidates = self._detect(message, history)

                # ---- semantic intent gate (runs only here, inside CONFIG, before type mapping) ----
                if route == "DEVICE_REFERENCE":
                    # A device/entity was named but no actionable change -> offer the
                    # actions we actually support (never force it into a config type).
                    actions = config_registry.types()
                    state.stage = ConfigStage.DISAMBIGUATE
                    state.candidates = actions
                    conversation_store.set_config_state(session_id, state)
                    return _resp(self._device_reference_message(), state, "user_input",
                                 extra={"route": "DEVICE_REFERENCE", "options": actions})
                if route == "UNKNOWN":
                    # Too vague to act on. Don't trap the session in CONFIG: clear it so the
                    # next turn is re-classified normally; just ask one clarifying question.
                    conversation_store.clear_config_state(session_id)
                    state.stage = ConfigStage.DONE
                    return _resp(self._unknown_message(), state, "user_input",
                                 extra={"route": "UNKNOWN"})
                if route == "NOT_CONFIG":
                    # The top-level router mis-fired CONFIG. Hand control back to it.
                    conversation_store.clear_config_state(session_id)
                    logger.info("CONFIG gate: NOT_CONFIG for %r -> returning control to router", message)
                    return {"route": "NOT_CONFIG"}

                # route == CONFIG_ACTION -> unchanged type-mapping behaviour.
                if ctype:
                    state.config_type = ctype
                    state.candidates = []
                else:
                    state.stage = ConfigStage.DISAMBIGUATE
                    state.candidates = candidates
                    conversation_store.set_config_state(session_id, state)
                    return _resp(self._disambiguation_message(candidates), state, "user_input")

            # forward progress: a fresh flow's type just resolved -> reset the cap.
            state.attempts = 1

        spec = config_registry.get(state.config_type)
        if spec is None:  # safety
            conversation_store.clear_config_state(session_id)
            state.stage = ConfigStage.DONE
            return _resp("That configuration type isn't available.", state, "none")

        # ---- 2/3. gather field values ----
        # Interpret the reply in context: while RESOLVE_TARGET is active the message
        # is a mode/device/connection answer, not a config field — so skip extraction.
        errors: dict[str, str] = {}
        at_gate = state.stage == ConfigStage.CONFIRM_APPROVAL
        approve_signal = at_gate and _is_approve(message)
        in_target = state.stage == ConfigStage.RESOLVE_TARGET
        # Multi-device standalone payloads ride in their own `devices` key. Pop it so it
        # never reaches the config-field merge, and hand it to target resolution. Single-
        # device / integrated payloads (a flat field->value dict) are unaffected.
        device_rows = None
        if isinstance(form_values, dict) and isinstance(form_values.get("devices"), list):
            device_rows = form_values.pop("devices")
        if not approve_signal and not in_target:
            before = dict(state.collected)
            if form_values:
                # Structured form submission -> merge directly, NO LLM, no NL parsing.
                state.collected, errors = _merge_and_validate(spec, state.collected, form_values)
            elif CONFIG_USE_FORMS and not state.initial_extracted:
                # First turn with forms on: ONE combined LLM call (extract + build copy).
                fb = build_form(spec, message, history)
                state.initial_extracted = True
                if fb is not None:
                    state.form_cache = {
                        "title": fb.title,
                        "description": fb.description,
                        "fields": {fc.name: {"heading": fc.heading, "description": fc.description,
                                             "example": fc.example} for fc in fb.fields},
                    }
                    extracted = fb.extracted
                else:
                    extracted = extract_fields(state.config_type, message, state.collected, history, spec)
                state.collected, errors = _merge_and_validate(spec, state.collected, extracted)
            else:
                # Forms off, OR a typed free-text reply after the form was shown (fallback).
                extracted = extract_fields(state.config_type, message, state.collected, history, spec)
                state.collected, errors = _merge_and_validate(spec, state.collected, extracted)
            if state.collected != before:
                state.attempts = 1  # forward progress: a slot changed -> reset the cap
            if at_gate:
                state.approved = False  # any edit re-opens the gate

        # ---- 4. recompute missing required fields ----
        missing = [f for f in spec.required_fields if f not in state.collected]
        state.missing_fields = missing
        if errors or missing:
            state.stage = ConfigStage.COLLECT_FIELDS
            conversation_store.set_config_state(session_id, state)
            if CONFIG_USE_FORMS:
                form = _build_form(spec, state, missing, errors)
                answer = _collect_message(spec, missing, errors)  # text fallback for non-form clients
                return _resp(answer, state, "form", extra={"form": form})
            return _resp(self._phrase(_collect_message(spec, missing, errors)), state, "user_input")

        # ---- 4·idempotency: an identical, already-delivered request returns the cached
        #      playbook and stays DONE — no re-running target/approval/delivery ("same
        #      thing twice" shortcut). Fires only once a prior delivery exists; the
        #      signature is type + collected fields (target is not part of the request).
        if state.last_result and _signature(state.config_type, state.collected) == state.last_executed_signature:
            logger.info("CONFIG duplicate request -> returning cached delivery for %r", session_id)
            state.stage = ConfigStage.DONE
            conversation_store.set_config_state(session_id, state)
            return state.last_result

        # ---- 4a. LLM pre-flight: validate the collected values against the playbook ----
        # (semantic/safety pass; the deterministic presence/format check already passed).
        # Cached per collected-signature so we don't re-call the LLM every turn.
        if CONFIG_LLM_PREFLIGHT and not approve_signal:
            pf_sig = _signature(state.config_type, state.collected)
            if pf_sig != state.preflight_sig:
                pf = preflight_validate(spec, state.collected, _playbook_text(spec))
                state.preflight_sig = pf_sig
                state.preflight_ok = pf.ok
                state.preflight_issues = pf.issues or []
                state.preflight_warnings = pf.warnings or []
            if not state.preflight_ok:
                state.stage = ConfigStage.COLLECT_FIELDS
                conversation_store.set_config_state(session_id, state)
                return _resp(self._phrase(_preflight_message(state.preflight_issues)), state, "user_input")

        # ---- 4b. resolve target: mode choice -> device picker / standalone details ----
        target_prompt = self._resolve_target(message, state, spec, form_values, device_rows)
        if target_prompt is not None:
            state.stage = ConfigStage.RESOLVE_TARGET
            conversation_store.set_config_state(session_id, state)
            return target_prompt

        # ---- 5. approval gate (full) ----
        if approve_signal:
            state.approved = True
        if not state.approved:
            state.stage = ConfigStage.CONFIRM_APPROVAL
            conversation_store.set_config_state(session_id, state)
            return _resp(_approval_summary(spec, state), state, "approval")

        # ---- 6. deliver — idempotent on signature ----
        sig = _signature(state.config_type, state.collected)
        if sig == state.last_executed_signature and state.last_result:
            return state.last_result

        rendered = _render_manual(spec, state)
        state.stage = ConfigStage.DELIVER
        if state.delivery_mode == "automated":
            answer = _automated_notice() + "\n" + _delivery_message(spec, state, rendered)
        else:
            answer = _delivery_message(spec, state, rendered)
        result = _resp(
            answer, state, "none",
            extra={
                # delivery_mode already echoed by _resp from state; record availability.
                "automated_available": False if state.delivery_mode == "automated" else None,
                "playbook": spec.playbook_name,
                "rendered_playbook": rendered["playbook_yaml"],
                "command": rendered["command"],
                "inventory_line": rendered.get("inventory_line"),
            },
        )
        # finalise: keep state at DONE with the cached result for idempotency.
        state.stage = ConfigStage.DONE
        state.last_executed_signature = sig
        state.last_result = result
        result["stage"] = ConfigStage.DONE.value
        conversation_store.set_config_state(session_id, state)
        return result

    # ----- helpers -----
    def _detect(self, message: str, history: str) -> tuple[str, Optional[str], list[str]]:
        """Semantic gate + config_type resolution, before any config-type mapping.

        Returns (route, resolved_type, candidates):
          - route is one of GATE_ROUTES. Only CONFIG_ACTION proceeds into the config flow;
            DEVICE_REFERENCE / UNKNOWN / NOT_CONFIG short-circuit upstream.
          - resolved_type/candidates are meaningful only for CONFIG_ACTION (same semantics
            as before: a type, or a candidate list to disambiguate).

        Efficiency: a single keyword hit is unambiguously a config ACTION and resolves with
        NO LLM call. Otherwise the EXISTING detect_type call also carries the gate route —
        no extra LLM round-trip is added.
        """
        hits = config_registry.match_keywords(message)

        # 1) exactly one keyword hit -> a clear config action, resolved deterministically.
        if len(hits) == 1:
            logger.info("CONFIG type resolved by keyword: %r", hits[0])
            return "CONFIG_ACTION", hits[0], []

        detection = detect_type(message, history)
        route = detection.route if detection.route in GATE_ROUTES else "CONFIG_ACTION"

        # 2) keyword collision -> config keywords ARE present, so it is a config action;
        #    resolve among the colliding types (trust a confident LLM pick, else disambiguate).
        if len(hits) > 1:
            if detection.config_type in hits and detection.confidence >= DETECT_CONFIDENCE_HIGH:
                logger.info("CONFIG keyword collision %s resolved by LLM: %r (conf=%.2f)",
                            hits, detection.config_type, detection.confidence)
                return "CONFIG_ACTION", detection.config_type, []
            logger.info("CONFIG keyword collision %s -> disambiguate", hits)
            return "CONFIG_ACTION", None, hits[:MAX_DISAMBIG_CANDIDATES]

        # 3) no keyword hit -> the gate route governs. A non-action route stops here
        #    WITHOUT classifying a config type (that stays in the CONFIG pipeline).
        if route != "CONFIG_ACTION":
            logger.info("CONFIG gate route=%s (conf=%.2f) for %r", route, detection.confidence, message)
            return route, None, []

        # 3a) CONFIG_ACTION with no keyword -> resolve by confidence, else disambiguate.
        if detection.config_type and detection.confidence >= DETECT_CONFIDENCE_LOW:
            logger.info("CONFIG type resolved by LLM: %r (conf=%.2f)",
                        detection.config_type, detection.confidence)
            return "CONFIG_ACTION", detection.config_type, []

        # 4) unresolved action -> build candidate list from the LLM's suggestions.
        candidates: list[str] = []
        if detection.config_type and config_registry.get(detection.config_type):
            candidates.append(detection.config_type)
        for c in detection.candidates:
            if config_registry.get(c) and c not in candidates:
                candidates.append(c)
        if not candidates:
            candidates = config_registry.types()[:3]
        logger.info("CONFIG type unresolved (conf=%.2f) -> disambiguate %s",
                    detection.confidence, candidates[:MAX_DISAMBIG_CANDIDATES])
        return "CONFIG_ACTION", None, candidates[:MAX_DISAMBIG_CANDIDATES]

    def _resolve_choice(self, message: str, candidates: list[str]) -> Optional[str]:
        """Match a disambiguation reply to one of the offered candidates."""
        m = (message or "").strip().lower()
        if not m:
            return None

        # numeric / ordinal pick — only when the reply is essentially just a choice.
        if len(m.split()) <= 3:
            num = re.search(r"(?:option\s*|number\s*|#\s*)?\b([1-9])\b", m)
            if num:
                idx = int(num.group(1)) - 1
                if 0 <= idx < len(candidates):
                    return candidates[idx]
            for word, n in _ORDINALS.items():
                if word in m and 0 <= n - 1 < len(candidates):
                    return candidates[n - 1]

        # explicit type name or a keyword belonging to a candidate.
        for c in candidates:
            if c in m or c.replace("_", " ") in m:
                return c
            spec = config_registry.get(c)
            if spec and any(kw in m for kw in spec.keywords):
                return c
        return None

    def _device_reference_message(self) -> str:
        """Gate response for DEVICE_REFERENCE: a device/entity was named but no action."""
        examples = config_registry.examples(3)
        eg = "; ".join(examples) if examples else 'set the hostname to CORE-SW-01'
        return "\n".join([
            "It looks like you named a device but didn't say what to change on it.",
            "I can make configuration changes such as a hostname, VLAN, interface, IP "
            "address, OSPF, ACL, NTP/SNMP/syslog, SSH access, or a local user.",
            "",
            f"Tell me what to change (e.g. {eg}), or rephrase your request.",
        ])

    def _unknown_message(self) -> str:
        """Gate response for UNKNOWN: one clarifying question."""
        return ("I didn't quite catch what you'd like to do. Are you trying to make a "
                "configuration change on a device (for example, set a hostname, create a "
                "VLAN, or configure an interface)? If so, tell me what to change.")

    def _disambiguation_message(self, candidates: list[str]) -> str:
        lines = ["I can tell you want a network configuration change, but I'm not sure which one. Did you mean:"]
        for i, c in enumerate(candidates, 1):
            spec = config_registry.get(c)
            example = spec.example if (spec and spec.example) else c
            lines.append(f"  {i}. {example}  _({c})_")
        lines.append("")
        lines.append("Reply with the number, the type name, or just rephrase your request.")
        return "\n".join(lines)


config_service = ConfigService()
