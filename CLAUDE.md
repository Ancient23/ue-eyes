# UE Eyes — Agent Visual Access for Unreal Engine 5.7

## Commands

```bash
# Install & test
uv sync
uv run pytest tests/ -v

# CLI
uv run ue-eyes ping
uv run ue-eyes snap --output captures/
uv run ue-eyes cameras
uv run ue-eyes score --reference ref/ --capture cap/
```

## Architecture

Python package communicating with UE 5.7 via Python Editor Script Plugin remote execution (UDP multicast discovery + TCP command channel).

Key directories:
- `ue_eyes/` — Python package (core library)
- `ue_eyes/unreal_scripts/` — Scripts injected into UE via remote exec
- `ue_eyes/scoring/` — Metrics, comparison, rubric system
- `ue_eyes/experiment/` — Research loop, params, results tracking
- `plugin/UEEyes/` — Optional UE 5.7 C++ plugin
- `skills/` — Claude Code skills
- `tests/` — pytest test suite

## Two Modes

1. **Development Mode** — Zero-config. Agent captures ad-hoc to see UE state.
2. **Research Loop** — Structured parameter tuning. Setup via `/ue-eyes:setup`.

## Code Style

- Python: snake_case, type hints on public functions, numpy for math (no scipy)
- C++: UE conventions (F-prefix structs, U-prefix UObjects, PascalCase)
- Package management: `uv` (not pip)
- CLI: Click
- No magic numbers — use named constants
- DRY/KISS — self-documenting, concise, robust

## Testing

Run full suite: `uv run pytest tests/ -v`
Mock UE connection for unit tests. Integration tests require running UE editor.
