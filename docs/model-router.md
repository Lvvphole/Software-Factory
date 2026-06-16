# Model Router

## Supported providers (v1)

| Provider | Credential | v1 behavior |
|---|---|---|
| `mock` | none | returns deterministic stub output |
| `openai_compatible` | `OPENAI_API_KEY` | adapter present; raises in dry-run (no hidden calls) |
| `anthropic_compatible` | `ANTHROPIC_API_KEY` | adapter present; raises in dry-run |
| `local_placeholder` | `LOCAL_MODEL_ENDPOINT` | adapter present; raises in dry-run |

`FACTORY_DEFAULT_PROVIDER` selects the default (`mock` if unset).

## Selection

`select_provider(task_kind, prefer)`:
1. If `prefer` is set and available → use it.
2. Else if `FACTORY_DEFAULT_PROVIDER` is available → use it.
3. Else fall back to `mock`.

## Logging

Each routing decision records:

```json
{ "timestamp", "task_kind",
  "selected_model", "selection_reason",
  "cost_estimate_usd", "latency_estimate_ms",
  "fallback_model", "final_outcome",
  "result_summary": "..." }
```

All entries for a run are aggregated into `.factory-runs/{run_id}/model-routing-log.json`.

## No hidden calls

A non-mock provider invocation in v1 raises rather than calling out. To enable live calls, replace the `invoke` body of the relevant adapter and add tests.

## Adding a provider

1. Subclass `ProviderAdapter` in `src/router/__init__.py`.
2. Implement `available()` and `invoke()`.
3. Register in `_ADAPTERS`.
4. Add to `tests/test_router.py`.
