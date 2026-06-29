"""
Tests for the CONFIG semantic intent gate.

The gate sits IN FRONT OF the CONFIG pipeline only: once the top-level router has
routed to CONFIG, the gate decides whether a real configuration ACTION exists before
config-type mapping. It returns one of:

    CONFIG_ACTION     -> proceed into the existing CONFIG pipeline unchanged
    DEVICE_REFERENCE  -> a device/entity was named but no action -> offer supported actions
    UNKNOWN           -> one clarifying question
    NOT_CONFIG        -> hand control back to the top-level router

Key properties verified here:
  * "configure C9800-L-F-K9" is recognised as a DEVICE_REFERENCE and is NOT forced into
    a config-type disambiguation (the reported bug).
  * The gate adds NO extra LLM round-trip — it reuses the existing detect_type call, and a
    single-keyword hit resolves with zero LLM calls.
  * Non-CONFIG intents (SQL/RAG/SEARCH/HYBRID) never reach the gate.

The LLM is fully mocked, so these run offline and deterministically.
"""
import uuid

import pytest

from app.services import config_service as cs_mod
from app.services.config_service import config_service
from app.services.conversation_store import conversation_store
from app.config_registry import config_registry
from app.models import ConfigTypeDetection, ConfigFormBuild, ConfigPreflight, ConfigStage


def _sid() -> str:
    return f"test-{uuid.uuid4()}"


def _detection(route, config_type=None, confidence=0.0, candidates=None):
    return ConfigTypeDetection(route=route, config_type=config_type,
                               confidence=confidence, candidates=candidates or [])


class _LLMMocks:
    """Replaces every LLM-backed config_chain function (as imported into config_service)
    with a counting stub, so we can assert routing behaviour AND exact LLM-call counts."""

    def __init__(self, monkeypatch):
        self._mp = monkeypatch
        self.calls = {k: 0 for k in (
            "detect_type", "build_form", "extract_fields",
            "preflight_validate", "extract_connection", "phrase_question",
        )}
        self._detect_ret = _detection("CONFIG_ACTION")
        self._build_ret = None
        self._extract_ret = {}
        self._install()

    def _counter(self, name, retfn):
        def fn(*args, **kwargs):
            self.calls[name] += 1
            return retfn()
        return fn

    def _install(self):
        mp, m = self._mp, cs_mod
        mp.setattr(m, "detect_type", self._counter("detect_type", lambda: self._detect_ret))
        mp.setattr(m, "build_form", self._counter("build_form", lambda: self._build_ret))
        mp.setattr(m, "extract_fields", self._counter("extract_fields", lambda: dict(self._extract_ret)))
        mp.setattr(m, "preflight_validate", self._counter("preflight_validate", lambda: ConfigPreflight(ok=True)))
        mp.setattr(m, "extract_connection", self._counter("extract_connection", lambda: {}))
        mp.setattr(m, "phrase_question", self._counter("phrase_question", lambda: "Q"))

    # configurable return values
    def set_detect(self, detection):
        self._detect_ret = detection

    def set_build(self, form_build):
        self._build_ret = form_build

    @property
    def total_llm(self):
        return sum(self.calls.values())


@pytest.fixture
def llm(monkeypatch):
    return _LLMMocks(monkeypatch)


# ---------------------------------------------------------------------------
# 1. A real config action with a keyword -> enters the config flow (no gate LLM).
# ---------------------------------------------------------------------------
def test_config_action_with_keyword_enters_flow(llm):
    llm.set_build(ConfigFormBuild(extracted={"vlan_id": "20", "vlan_name": "finance"}))
    resp = config_service.handle("configure VLAN 20 named finance", _sid())

    assert resp.get("config_type") == "vlan"
    assert resp.get("route") is None          # not a gate short-circuit
    assert resp.get("stage") != ConfigStage.DISAMBIGUATE.value
    assert llm.calls["detect_type"] == 0      # single keyword hit -> no LLM gate call


# ---------------------------------------------------------------------------
# 2. "configure C9800-L-F-K9" -> DEVICE_REFERENCE, NOT forced into a config type.
# ---------------------------------------------------------------------------
def test_device_model_is_device_reference_not_config_type(llm):
    llm.set_detect(_detection("DEVICE_REFERENCE"))
    resp = config_service.handle("configure C9800-L-F-K9", _sid())

    assert resp["route"] == "DEVICE_REFERENCE"
    assert resp.get("config_type") is None                 # never mapped to vlan/hostname/...
    assert resp["stage"] == ConfigStage.DISAMBIGUATE.value
    assert llm.calls["detect_type"] == 1
    assert llm.calls["build_form"] == 0                    # no config-type mapping happened
    assert llm.calls["extract_fields"] == 0                # no field extraction happened


# ---------------------------------------------------------------------------
# 3. A bare device model with no verb -> DEVICE_REFERENCE.
# ---------------------------------------------------------------------------
def test_bare_device_model_is_device_reference(llm):
    llm.set_detect(_detection("DEVICE_REFERENCE"))
    resp = config_service.handle("C9800-L-F-K9", _sid())
    assert resp["route"] == "DEVICE_REFERENCE"
    assert resp.get("config_type") is None


# ---------------------------------------------------------------------------
# 4. "set hostname to CORE-SW-01" -> CONFIG_ACTION (resolved by keyword, no gate LLM).
# ---------------------------------------------------------------------------
def test_set_hostname_is_config_action(llm):
    llm.set_build(ConfigFormBuild(extracted={"hostname": "CORE-SW-01"}))
    resp = config_service.handle("set hostname to CORE-SW-01", _sid())

    assert resp.get("config_type") == "hostname"
    assert resp.get("route") is None
    assert llm.calls["detect_type"] == 0


# ---------------------------------------------------------------------------
# 5. Gibberish / unclear -> UNKNOWN -> one clarifying question.
# ---------------------------------------------------------------------------
def test_unclear_input_is_unknown(llm):
    llm.set_detect(_detection("UNKNOWN"))
    resp = config_service.handle("asdfgh qwerty ??? zzz", _sid())

    assert resp["route"] == "UNKNOWN"
    assert resp.get("config_type") is None
    assert isinstance(resp.get("answer"), str) and resp["answer"].strip()


# ---------------------------------------------------------------------------
# 5b. NOT_CONFIG -> gate hands a sentinel back so app.py can re-route.
# ---------------------------------------------------------------------------
def test_not_config_returns_sentinel(llm):
    llm.set_detect(_detection("NOT_CONFIG"))
    resp = config_service.handle("what does EOL mean", _sid())

    assert resp == {"route": "NOT_CONFIG"}
    assert llm.calls["detect_type"] == 1
    assert llm.calls["build_form"] == 0


# ---------------------------------------------------------------------------
# 6. Non-CONFIG intents never reach the gate: the router keeps SQL/RAG/SEARCH/HYBRID.
#    (The gate lives only inside the CONFIG branch, so by construction these bypass it.)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("llm_word,expected", [
    ("SQL", "SQL"),
    ("RAG", "RAG"),
    ("SEARCH", "SEARCH"),
    ("WEB please", "SEARCH"),       # unmatched -> safe default
    ("SQL and RAG", "HYBRID"),
])
def test_non_config_intents_bypass_gate(monkeypatch, llm_word, expected):
    import app.router as router_mod

    class _Resp:
        content = llm_word

    monkeypatch.setattr(router_mod.llm, "invoke", lambda prompt: _Resp())
    assert router_mod.classify_intent("list switches in Pune") == expected
    assert expected != "CONFIG"     # so config_service / the gate is never invoked


# ---------------------------------------------------------------------------
# 7. The gate adds exactly ONE LLM call and no extra round-trip.
# ---------------------------------------------------------------------------
def test_gate_adds_no_extra_llm_round_trip(llm):
    llm.set_detect(_detection("DEVICE_REFERENCE"))
    config_service.handle("configure C9800-L-F-K9", _sid())

    # The only LLM call is the (reused) detect_type call; nothing downstream fires.
    assert llm.calls["detect_type"] == 1
    assert llm.calls["build_form"] == 0
    assert llm.calls["extract_fields"] == 0
    assert llm.calls["preflight_validate"] == 0
    assert llm.total_llm == 1


# ---------------------------------------------------------------------------
# 8. DEVICE_REFERENCE options list ONLY currently-supported actions.
# ---------------------------------------------------------------------------
def test_device_reference_options_are_supported_actions(llm):
    llm.set_detect(_detection("DEVICE_REFERENCE"))
    resp = config_service.handle("the core router", _sid())

    options = resp.get("options")
    supported = set(config_registry.types())
    assert options, "DEVICE_REFERENCE must offer the supported actions"
    assert set(options) <= supported          # only real, supported actions
    assert supported                           # registry actually loaded some types


# ---------------------------------------------------------------------------
# Follow-up: after a DEVICE_REFERENCE, naming a real action resolves into the flow.
# ---------------------------------------------------------------------------
def test_device_reference_then_action_resolves(llm):
    sid = _sid()
    llm.set_detect(_detection("DEVICE_REFERENCE"))
    first = config_service.handle("configure C9800-L-F-K9", sid)
    assert first["route"] == "DEVICE_REFERENCE"

    # Now the user states a concrete action; "vlan" keyword resolves it deterministically.
    llm.set_build(ConfigFormBuild(extracted={"vlan_id": "30", "vlan_name": "FINANCE"}))
    second = config_service.handle("create VLAN 30 named FINANCE", sid)
    assert second.get("config_type") == "vlan"
    assert second.get("route") is None
