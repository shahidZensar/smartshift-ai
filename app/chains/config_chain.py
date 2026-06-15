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
from ..decision import llm
from ..models import ConfigTypeDetection, ConfigFieldExtraction, ConfigConnectionExtraction
from ..config_registry import config_registry, ConfigTypeSpec
from ..prompts import (
    CONFIG_TYPE_DETECT_PROMPT,
    CONFIG_FIELD_EXTRACT_PROMPT,
    CONFIG_QUESTION_PROMPT,
    CONFIG_CONNECTION_EXTRACT_PROMPT,
)

_detect_parser = PydanticOutputParser(pydantic_object=ConfigTypeDetection)
_extract_parser = PydanticOutputParser(pydantic_object=ConfigFieldExtraction)
_conn_parser = PydanticOutputParser(pydantic_object=ConfigConnectionExtraction)


def _llm_text(output: Any) -> str:
    return output.content if hasattr(output, "content") else str(output)


def detect_type(query: str, history: str = "") -> ConfigTypeDetection:
    """LLM fallback: map a request to one config_type with confidence + candidates."""
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
        output = llm.invoke(prompt)
        result = _detect_parser.parse(_llm_text(output))
        # Guard: reject hallucinated types not in the registry.
        if result.config_type and result.config_type not in types:
            logger.warning("detect_type returned unknown type %r; discarding", result.config_type)
            result.candidates = [c for c in result.candidates if c in types]
            result.config_type = None
            result.confidence = 0.0
        return result
    except Exception as exc:
        logger.error("config detect_type failed: %s", exc)
        return ConfigTypeDetection(config_type=None, confidence=0.0, candidates=[])


def extract_fields(
    config_type: str,
    query: str,
    collected: dict[str, Any],
    history: str = "",
    spec: Optional[ConfigTypeSpec] = None,
) -> dict[str, Any]:
    """Extract stated field values for the given config_type. Returns {} on failure."""
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
        output = llm.invoke(prompt)
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


def extract_connection(query: str, collected: dict[str, Any]) -> dict[str, Any]:
    """Extract standalone connection details (device_name/ansible_host/username/password)."""
    prompt = CONFIG_CONNECTION_EXTRACT_PROMPT.format(
        collected={k: ("***" if k == "password" else v) for k, v in (collected or {}).items()},
        query=query,
        format_instructions=_conn_parser.get_format_instructions(),
    )
    try:
        output = llm.invoke(prompt)
        result = _conn_parser.parse(_llm_text(output))
        return {k: v for k, v in result.model_dump().items() if v not in (None, "")}
    except Exception as exc:
        logger.error("config extract_connection failed: %s", exc)
        return {}


def phrase_question(message: str) -> str:
    """Rewrite a deterministic follow-up so it reads naturally. Falls back to the
    original message on any failure (grounding stays intact either way)."""
    try:
        output = llm.invoke(CONFIG_QUESTION_PROMPT.format(message=message))
        text = _llm_text(output).strip()
        return text or message
    except Exception as exc:
        logger.error("config phrase_question failed: %s", exc)
        return message
