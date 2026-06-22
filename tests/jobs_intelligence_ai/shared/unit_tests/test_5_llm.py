"""
shared/llm.py — the single OpenAI client (Stage 2.1a).

Verifies the singleton contract and that the client is constructed from the configured
key. Also demonstrates the mock seam every service test relies on: patch `llm.OpenAI`
(or `llm.get_client`) to keep the network out of unit tests.
"""
import jobs_intelligence_ai.shared.llm as llm


def test_get_client_is_a_singleton(monkeypatch):
    created = []

    class FakeOpenAI:
        def __init__(self, api_key=None):
            created.append(api_key)

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm, "_client", None)   # reset the module singleton

    c1 = llm.get_client("key-1")
    c2 = llm.get_client("key-2")   # ignored — already created

    assert c1 is c2
    assert created == ["key-1"]    # constructed exactly once, with the first key


def test_get_client_defaults_to_config_key(monkeypatch):
    seen = {}

    class FakeOpenAI:
        def __init__(self, api_key=None):
            seen["key"] = api_key

    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "from-config")

    llm.get_client()
    assert seen["key"] == "from-config"
