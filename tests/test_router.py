from router import supported_providers, route_and_invoke, PROVIDERS


def test_supports_four_providers():
    p = supported_providers()
    assert "mock" in p
    assert "openai_compatible" in p
    assert "anthropic_compatible" in p
    assert "local_placeholder" in p
    assert set(PROVIDERS) == set(p)


def test_routing_log_fields():
    entry = route_and_invoke("hello", task_kind="test")
    for field in ("selected_model", "selection_reason", "cost_estimate_usd",
                  "latency_estimate_ms", "fallback_model", "final_outcome"):
        assert field in entry, f"missing {field}"
    assert entry["final_outcome"] == "ok"


def test_fallback_to_mock_when_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("FACTORY_DEFAULT_PROVIDER", "mock")
    entry = route_and_invoke("hi", task_kind="x", prefer="openai_compatible")
    # preferred unavailable -> selected falls back to default
    assert entry["selected_model"] in ("mock",)
