"""
LLM chains for the CONFIG intent:
  - detect_type:    fallback config-type detection when keywords miss/clash (§8).
  - extract_fields: pull stated field values out of a user message (§6 step 3).

Both follow the existing PydanticOutputParser pattern (see decision.py). The LLM is
constrained to a fixed field/type set and instructed never to invent values.
"""
from typing import Any, Optional

from langchain_core.output_parsers import PydanticOutputParser

from .. import logger
from ..decision import llm as _azure_llm
from ..models import (
    ConfigTypeDetection, ConfigFieldExtraction, ConfigConnectionExtraction,
    ConfigPreflight, ConfigFormBuild,
)
from ..config_registry import config_registry, ConfigTypeSpec
from ..prompts import (
    CONFIG_TYPE_DETECT_PROMPT,
    CONFIG_FIELD_EXTRACT_PROMPT,
    CONFIG_QUESTION_PROMPT,
    CONFIG_CONNECTION_EXTRACT_PROMPT,
    CONFIG_PREFLIGHT_PROMPT,
    CONFIG_FORM_BUILD_PROMPT,
)

# Closed set of semantic-gate verdicts the detection call may return (see config_service).
GATE_ROUTES = ("CONFIG_ACTION", "DEVICE_REFERENCE", "UNKNOWN", "NOT_CONFIG")

_detect_parser = PydanticOutputParser(pydantic_object=ConfigTypeDetection)
_extract_parser = PydanticOutputParser(pydantic_object=ConfigFieldExtraction)
_conn_parser = PydanticOutputParser(pydantic_object=ConfigConnectionExtraction)
_preflight_parser = PydanticOutputParser(pydantic_object=ConfigPreflight)
_form_parser = PydanticOutputParser(pydantic_object=ConfigFormBuild)


def _llm_text(output: Any) -> str:
    return output.content if hasattr(output, "content") else str(output)


def detect_type(query: str, history: str = "", llm=None) -> ConfigTypeDetection:
    """LLM fallback: map a request to one config_type with confidence + candidates."""
    _llm = llm if llm is not None else _azure_llm
    types = config_registry.types()
    type_examples = "\n".join(
        f"- {t}: {spec.example}" for t, spec in config_registry.all().items() if spec.example
    )
    prompt = CONFIG_TYPE_DETECT_PROMPT.format(
        config_types=", ".join(types),
        type_examples=type_examples,
        history=history or "(none)",
        query=query,
        format_instructions=_detect_parser.get_format_instructions(),
    )
    try:
        output = _llm.invoke(prompt)
        result = _detect_parser.parse(_llm_text(output))
        # Normalise the semantic-gate route to the closed set. Default to CONFIG_ACTION so
        # a garbled/missing route never blocks an otherwise-valid config request (the gate
        # only ADDS branching for non-action inputs; it never weakens existing behaviour).
        route = (result.route or "").strip().upper()
        result.route = route if route in GATE_ROUTES else "CONFIG_ACTION"
        # Guard: reject hallucinated types not in the registry.
        if result.config_type and result.config_type not in types:
            logger.warning("detect_type returned unknown type %r; discarding", result.config_type)
            result.candidates = [c for c in result.candidates if c in types]
            result.config_type = None
            result.confidence = 0.0
        return result
    except Exception as exc:
        logger.error("config detect_type failed: %s", exc)
        # Fail-safe: proceed as before (CONFIG_ACTION) so an LLM/parse error degrades to
        # the existing disambiguation flow rather than swallowing a real config request.
        return ConfigTypeDetection(route="CONFIG_ACTION", config_type=None, confidence=0.0, candidates=[])


def extract_fields(
    config_type: str,
    query: str,
    collected: dict[str, Any],
    history: str = "",
    spec: Optional[ConfigTypeSpec] = None,
    llm=None,
) -> dict[str, Any]:
    """Extract stated field values for the given config_type. Returns {} on failure."""
    _llm = llm if llm is not None else _azure_llm
    spec = spec or config_registry.get(config_type)
    if spec is None:
        return {}

    lines = []
    for fname in spec.required_fields + spec.optional_fields:
        meta = spec.field_meta(fname)
        eg = f" (e.g. {meta.example})" if meta.example else ""
        lines.append(f"- {fname}: {meta.prompt}{eg}")
    field_descriptions = "\n".join(lines)

    prompt = CONFIG_FIELD_EXTRACT_PROMPT.format(
        config_type=config_type,
        field_descriptions=field_descriptions,
        collected=collected or "(none)",
        history=history or "(none)",
        query=query,
        format_instructions=_extract_parser.get_format_instructions(),
    )
    try:
        output = _llm.invoke(prompt)
        result = _extract_parser.parse(_llm_text(output))
        allowed = set(spec.required_fields) | set(spec.optional_fields)
        # Keep only known, non-empty fields.
        return {
            k: v for k, v in (result.collected or {}).items()
            if k in allowed and v not in (None, "", [])
        }
    except Exception as exc:
        logger.error("config extract_fields failed: %s", exc)
        return {}


def extract_connection(query: str, collected: dict[str, Any], llm=None) -> dict[str, Any]:
    """Extract standalone connection details (device_name/ansible_host/username/password)."""
    _llm = llm if llm is not None else _azure_llm
    prompt = CONFIG_CONNECTION_EXTRACT_PROMPT.format(
        collected={k: ("***" if k == "password" else v) for k, v in (collected or {}).items()},
        query=query,
        format_instructions=_conn_parser.get_format_instructions(),
    )
    try:
        output = _llm.invoke(prompt)
        result = _conn_parser.parse(_llm_text(output))
        return {k: v for k, v in result.model_dump().items() if v not in (None, "")}
    except Exception as exc:
        logger.error("config extract_connection failed: %s", exc)
        return {}


def build_form(spec: ConfigTypeSpec, query: str, history: str = "", llm=None) -> Optional[ConfigFormBuild]:
    """One combined LLM call: author the form copy AND extract any values already given.

    Constrained to the registry's field names. Returns None on failure so the caller
    falls back to static ENRICHMENT copy (and no pre-fill)."""
    _llm = llm if llm is not None else _azure_llm
    lines = []
    for fname in spec.required_fields + spec.optional_fields:
        meta = spec.field_meta(fname)
        eg = f" (e.g. {meta.example})" if meta.example else ""
        tag = "" if fname in spec.required_fields else " [optional]"
        lines.append(f"- {fname}: {meta.prompt}{eg}{tag}")
    field_specs = "\n".join(lines)

    prompt = CONFIG_FORM_BUILD_PROMPT.format(
        config_type=spec.config_type,
        field_specs=field_specs,
        history=history or "(none)",
        query=query,
        format_instructions=_form_parser.get_format_instructions(),
    )
    try:
        output = _llm.invoke(prompt)
        result = _form_parser.parse(_llm_text(output))
        # Keep only extracted values for known, non-empty fields.
        allowed = set(spec.required_fields) | set(spec.optional_fields)
        result.extracted = {
            k: v for k, v in (result.extracted or {}).items()
            if k in allowed and v not in (None, "", [])
        }
        return result
    except Exception as exc:
        logger.error("config build_form failed (fallback to static copy): %s", exc)
        return None


def preflight_validate(spec: ConfigTypeSpec, collected: dict[str, Any], playbook_text: str, llm=None) -> ConfigPreflight:
    """Validate the collected mandatory properties against the actual playbook.

    Fail-open: any LLM/parse error returns ok=True so the gate is never blocked by an
    infrastructure problem (the deterministic missing-field check already ran)."""
    _llm = llm if llm is not None else _azure_llm
    redacted = {
        k: ("***" if spec.field_meta(k).secret else v)
        for k, v in (collected or {}).items()
    }
    prompt = CONFIG_PREFLIGHT_PROMPT.format(
        config_type=spec.config_type,
        required_fields=", ".join(spec.required_fields) or "(none)",
        optional_fields=", ".join(spec.optional_fields) or "(none)",
        collected=redacted or "(none)",
        playbook=(playbook_text or "")[:4000],
        format_instructions=_preflight_parser.get_format_instructions(),
    )
    try:
        output = _llm.invoke(prompt)
        return _preflight_parser.parse(_llm_text(output))
    except Exception as exc:
        logger.error("config preflight_validate failed (fail-open): %s", exc)
        return ConfigPreflight(ok=True)


def phrase_question(message: str, llm=None) -> str:
    """Rewrite a deterministic follow-up so it reads naturally. Falls back to the
    original message on any failure (grounding stays intact either way)."""
    _llm = llm if llm is not None else _azure_llm
    try:
        output = _llm.invoke(CONFIG_QUESTION_PROMPT.format(message=message))
        text = _llm_text(output).strip()
        return text or message
    except Exception as exc:
        logger.error("config phrase_question failed: %s", exc)
        return message
