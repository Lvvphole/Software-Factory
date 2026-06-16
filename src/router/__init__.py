"""Model router with 4 provider adapters: mock, openai-compatible,
anthropic-compatible, local-placeholder. v1 ships mock as the default
to avoid hidden model calls. All other providers are stubs that REQUIRE
credentials in env and explicit selection; they raise if invoked without
credentials.

Every routing decision is logged with selected_model, reason, cost_estimate,
latency_estimate, fallback_model, and final_outcome.
"""
from __future__ import annotations
import os
from typing import Any
from utils import get_logger, utc_now_iso

log = get_logger("router")

PROVIDERS = ("mock", "openai_compatible", "anthropic_compatible", "local_placeholder")


class ProviderAdapter:
    name: str = "base"
    def available(self) -> bool: return False
    def invoke(self, prompt: str, **kw) -> dict[str, Any]:
        raise NotImplementedError


class MockAdapter(ProviderAdapter):
    name = "mock"
    def available(self) -> bool: return True
    def invoke(self, prompt: str, **kw) -> dict[str, Any]:
        return {"provider": "mock", "model": "mock-v1", "output": f"[mock] {prompt[:120]}",
                "cost_usd": 0.0, "latency_ms": 1}


class OpenAICompatAdapter(ProviderAdapter):
    name = "openai_compatible"
    def available(self) -> bool: return bool(os.environ.get("OPENAI_API_KEY"))
    def invoke(self, prompt: str, **kw) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("OPENAI_API_KEY not set; openai_compatible unavailable in v1 dry-run")
        # v1: do not perform real network calls; surface as not implemented to avoid hidden calls
        raise NotImplementedError("v1 dry-run does not perform live OpenAI-compatible calls")


class AnthropicCompatAdapter(ProviderAdapter):
    name = "anthropic_compatible"
    def available(self) -> bool: return bool(os.environ.get("ANTHROPIC_API_KEY"))
    def invoke(self, prompt: str, **kw) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("ANTHROPIC_API_KEY not set; anthropic_compatible unavailable in v1 dry-run")
        raise NotImplementedError("v1 dry-run does not perform live Anthropic-compatible calls")


class LocalPlaceholderAdapter(ProviderAdapter):
    name = "local_placeholder"
    def available(self) -> bool: return bool(os.environ.get("LOCAL_MODEL_ENDPOINT"))
    def invoke(self, prompt: str, **kw) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("LOCAL_MODEL_ENDPOINT not set; local_placeholder unavailable")
        raise NotImplementedError("v1 dry-run does not perform live local-model calls")


_ADAPTERS: dict[str, ProviderAdapter] = {
    "mock": MockAdapter(),
    "openai_compatible": OpenAICompatAdapter(),
    "anthropic_compatible": AnthropicCompatAdapter(),
    "local_placeholder": LocalPlaceholderAdapter(),
}


def supported_providers() -> list[str]:
    return list(_ADAPTERS.keys())


def select_provider(task_kind: str, prefer: str | None = None) -> tuple[str, str]:
    """Return (selected_provider, reason)."""
    if prefer and prefer in _ADAPTERS and _ADAPTERS[prefer].available():
        return prefer, f"explicit preference '{prefer}' and available"
    default = os.environ.get("FACTORY_DEFAULT_PROVIDER", "mock")
    if default in _ADAPTERS and _ADAPTERS[default].available():
        return default, f"env default '{default}' and available"
    return "mock", "fallback: no other provider available, using mock"


def route_and_invoke(prompt: str, task_kind: str, prefer: str | None = None) -> dict[str, Any]:
    selected, reason = select_provider(task_kind, prefer)
    fallback = "mock"
    entry: dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "task_kind": task_kind,
        "selected_model": _ADAPTERS[selected].name,
        "selection_reason": reason,
        "cost_estimate_usd": 0.0,
        "latency_estimate_ms": 1,
        "fallback_model": fallback,
        "final_outcome": None,
    }
    try:
        result = _ADAPTERS[selected].invoke(prompt)
        entry["final_outcome"] = "ok"
        entry["cost_estimate_usd"] = result.get("cost_usd", 0.0)
        entry["latency_estimate_ms"] = result.get("latency_ms", 1)
        entry["result_summary"] = result.get("output", "")[:200]
    except Exception as e:
        entry["final_outcome"] = f"error_fell_back_to_{fallback}"
        entry["error"] = str(e)
        result = _ADAPTERS[fallback].invoke(prompt)
        entry["result_summary"] = result.get("output", "")[:200]
    log.info("router decision: %s reason=%s outcome=%s",
             entry["selected_model"], reason, entry["final_outcome"])
    return entry
