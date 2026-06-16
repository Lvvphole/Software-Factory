# Autonomy Levels

| Level | Behavior | Allowed in v1 |
|---|---|---|
| 0 | Plan-only. No agent execution. | yes |
| 1 | Dry-run agents; no writes anywhere. | yes |
| 2 | Dry-run agents + memory writes + run-artifact writes. **Default.** | yes |
| 3 | Real file edits + outbound integration calls. | **no** (blocked) |

Governance enforces `autonomy_level <= 2` in v1. Requests above 2 are blocked with `reason="autonomy_level N > max v1 (2)"`.

The CLI default is `--autonomy 2`. Production deploys require explicit human approval regardless of level.
