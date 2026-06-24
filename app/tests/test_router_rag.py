"""
Tests for the RAG-only intent safeguard in app/router.py.

Verifies that an explicit reference to user-provided/ingested context upgrades a
web-SEARCH fallback to RAG, while every other classifier verdict is untouched.
The LLM is stubbed, so these run offline.
"""
import pytest

from app import router
from app.router import classify_intent, _references_provided_context


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, content):
        self._content = content

    def invoke(self, prompt):
        return _FakeResp(self._content)


def _stub_llm(monkeypatch, verdict):
    # Replace the module-level `llm` reference (the real one is a Pydantic model
    # whose methods can't be monkeypatched directly).
    monkeypatch.setattr(router, "llm", _FakeLLM(verdict))


@pytest.mark.parametrize(
    "q",
    [
        "Key features of the C9610 from the context which I have provided",
        "summarize the document I uploaded",
        "what does the page I added say about licensing",
        "answer from the knowledge base only",
    ],
)
def test_context_cue_detected(q):
    assert _references_provided_context(q) is True


def test_no_cue_for_generic_question():
    assert _references_provided_context("what is the latest Cisco switch") is False


def test_search_upgraded_to_rag_when_context_referenced(monkeypatch):
    _stub_llm(monkeypatch, "SEARCH")
    intent = classify_intent("Key features of C9610 from the context which I have provided")
    assert intent == "RAG"


def test_search_stays_search_without_cue(monkeypatch):
    _stub_llm(monkeypatch, "SEARCH")
    assert classify_intent("what are the latest networking trends") == "SEARCH"


def test_other_verdicts_untouched(monkeypatch):
    # Even with a context cue present, a non-SEARCH verdict is never overridden.
    _stub_llm(monkeypatch, "SQL")
    assert classify_intent("list my devices from the document") == "SQL"

    _stub_llm(monkeypatch, "CONFIG")
    assert classify_intent("set hostname from the context") == "CONFIG"

    _stub_llm(monkeypatch, "RAG")
    assert classify_intent("explain the migration policy") == "RAG"
