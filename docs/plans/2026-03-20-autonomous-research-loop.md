# Plan: Autonomous Research Loop

**Date:** 2026-03-20
**Status:** Planned
**Goal:** Claude Code drives experiment iterations programmatically through a thin Python orchestration layer and an enhanced skill.

---

## Problem

The current `/ue-eyes:research-loop` skill instructs Claude Code to manually edit `tune_params.json`, run CLI commands, read output files, and manage git state. Each iteration involves 5+ manual steps. This is slow, error-prone, and breaks flow — the agent spends more time on mechanics than on reasoning about what to try next.

## Solution

A new `ue_eyes/experiment/loop.py` module that wraps the entire iteration into a single function call, plus a CLI command to expose it. The skill shifts from "here's how to manually do each step" to "reason about what to try, then call one command."

---

## Architecture

```
Claude Code (the agent)
  │
  │  Reads: results.tsv, comparison images, current params
  │  Decides: which parameter, what value, why
  │
  ▼
ue-eyes iterate --param X --value Y --hypothesis "..."
  │
  │  loop.py orchestrates:
  │    1. Snapshot current params
  │    2. Mutate parameter
  │    3. ExperimentRunner.run_experiment()
  │       └── capture → compare → score
  │    4. Compare to best score → verdict
  │    5. If discard → revert params
  │    6. Log to results.tsv
  │
  ▼
JSON result to stdout → agent reads scores + verdict + image paths
```

**Separation of concerns:**
- **Claude Code** owns the intelligence: hypothesis formation, visual evaluation, strategy
- **Python** owns the mechanics: capture, score, revert, log

---

## New Module: `ue_eyes/experiment/loop.py`

### `IterationResult` dataclass

Wraps the existing `ExperimentResult` (from `runner.py`) with the additional iteration-level fields that `run_iteration()` computes (parameter change tracking, best score comparison, verdict). Avoids duplicating fields — delegates to `ExperimentResult` for capture/scoring data.

```python
@dataclass
class IterationResult:
    experiment: ExperimentResult     # from runner.run_experiment()
    parameter_name: str
    old_value: Any
    new_value: Any
    best_previous_score: float
    verdict: str                    # "keep" | "discard"
```

The `ExperimentResult` already contains: `experiment_id`, `hypothesis`, `scores`, `composite_score`, `capture_dir`, `comparison_paths`, `difference_map_paths`.

### `run_iteration()` function

```python
def run_iteration(
    config: UEEyesConfig,
    parameter_name: str,
    new_value: Any,
    hypothesis: str,
    baseline_dir: str | None = None,
) -> IterationResult
```

**Steps:**

1. **Load state** — Read `tune_params.json`, take a snapshot of current values
2. **Validate** — Call `validate_param_change()` to catch bad values early
3. **Mutate** — `set_param_value()` + `save_params()` to write the new value
4. **Generate experiment ID** — Sequential: `exp_001`, `exp_002`, etc. (based on results.tsv row count)
5. **Build apply function** — Create a no-op `apply_fn` since the parameter file has already been mutated in step 3. The actual parameter application in UE depends on the user's workflow: either they apply params via a UE Blueprint that reads `tune_params.json`, or the agent applies them via remote exec before calling `iterate`. The runner's `apply_fn` is set to `None` (agent mode).
6. **Run experiment** — Call `ExperimentRunner.run_experiment(experiment_id, apply_fn=None, params=current_params, hypothesis=hypothesis, parameter_changed=parameter_name)` which handles:
   - Capture frames (snap or render, based on config)
   - Generate comparison images (side-by-side + difference heatmap)
   - Compute quantitative scores
7. **Decide** — Load best score from `results.tsv` via `get_best_score()`. If `composite_score > best_previous_score`, verdict is "keep"; otherwise "discard"
8. **Revert on discard** — If verdict is "discard", restore params from the snapshot
9. **Log** — Append to `results.tsv` via `log_result()`
10. **Return** — `IterationResult` wrapping the `ExperimentResult` plus iteration metadata

Note: `run_iteration()` does NOT accept a `UERemoteExecution` parameter. Connection management is handled internally by `ExperimentRunner` → `snap_frame()`/`render_sequence()`, which create and close their own connections.

### `get_loop_status()` function

```python
def get_loop_status(config: UEEyesConfig) -> dict
```

Returns a summary for the agent:
- Current parameter values
- Number of experiments run
- Best score and which experiment achieved it
- Score trend (last N)
- Parameters not yet tested

Useful for the ANALYZE step of the skill.

---

## New CLI Command: `ue-eyes iterate`

```
ue-eyes iterate --param <name> --value <value> --hypothesis "<text>"
```

**Options:**
- `--param` (required) — Parameter name from `tune_params.json`
- `--value` (required) — New value to test (passed as string, auto-coerced to the parameter's declared type from `tune_params.json` — e.g., `"5000"` → `int`, `"true"` → `bool`, `"0.75"` → `float`)
- `--hypothesis` (required) — Why this change should improve the score
- `--baseline` (optional) — Override baseline directory

**Type coercion:** The CLI looks up the parameter's `type` field in `tune_params.json` and coerces the string value accordingly: `"float"` → `float()`, `"int"` → `int()`, `"bool"` → case-insensitive `"true"/"false"`, `"enum"` → validated against `options` list, `"str"` → used as-is. Invalid coercion raises a clear error before the experiment runs.

**Output:** JSON to stdout:
```json
{
  "experiment_id": "exp_003",
  "parameter": "light_intensity",
  "old_value": 5000,
  "new_value": 7500,
  "hypothesis": "Increase brightness to reduce shadow artifacts",
  "composite_score": 0.87,
  "best_previous_score": 0.82,
  "verdict": "keep",
  "scores": {"ssim": 0.87, "pixel_mse": 0.91},
  "comparison_images": ["experiments/exp_003/comparison.png"],
  "difference_maps": ["experiments/exp_003/diff.png"]
}
```

Also add `ue-eyes loop-status` to expose `get_loop_status()`:
```
ue-eyes loop-status
```

The name `loop-status` (rather than `status`) avoids confusion with connection/system status (`ue-eyes ping`) and makes the scope clear.

---

## Enhanced Skill: `/ue-eyes:research-loop`

The skill is rewritten to use the new commands. Core loop:

### 1. ANALYZE
```
Read results.tsv (or run `ue-eyes loop-status`)
Read current tune_params.json
Inspect best capture images visually
Review rubric criteria
```

### 2. HYPOTHESIZE
```
Based on analysis:
- Pick ONE parameter to change
- Choose a new value
- Write a hypothesis explaining expected improvement
```

### 3. RUN
```
ue-eyes iterate --param <name> --value <value> --hypothesis "<text>"
```
One command. Everything automated.

### 4. EVALUATE
```
Read the JSON output (scores + verdict)
Inspect comparison images visually (Read tool on the PNG paths)
If rubric exists: score qualitatively against criteria
```

### 5. DECIDE
```
Verdict is already computed, but agent can override:
- If quantitative says "discard" but visual inspection shows clear improvement,
  agent can re-run with adjusted metrics/weights
- If "keep" but visual regression noticed, agent flags it
```

### 6. LOOP
```
Return to ANALYZE. Do not stop unless:
- Goal score reached (from rubric.json)
- User interrupts
- Agent is stuck (escalation strategies documented in skill)
```

### Escalation Strategies (unchanged from current skill)
- Review full history for untested parameters
- Try boundary values (min/max of parameter range)
- Binary search the parameter space
- Reset to best known state
- Re-examine rubric criteria
- Ask the user for guidance

---

## Files to Create

- **`ue_eyes/experiment/loop.py`** — `run_iteration()`, `get_loop_status()`, `IterationResult`
- **`tests/test_loop.py`** — Unit tests for the orchestration layer
  - Test iteration with mock ExperimentRunner
  - Test keep/discard logic
  - Test param revert on discard
  - Test experiment ID generation
  - Test status summary
- **Updated `ue_eyes/cli.py`** — Add `iterate` and `loop-status` commands
- **Updated `skills/research-loop/SKILL.md`** — Rewritten to use `ue-eyes iterate`

## Files NOT Modified

- `ue_eyes/experiment/runner.py` — Called as-is
- `ue_eyes/experiment/params.py` — Called as-is
- `ue_eyes/experiment/results.py` — Called as-is
- `ue_eyes/scoring/` — All scoring code untouched

---

## Dependencies

- No new Python dependencies
- No agent SDK / Anthropic SDK required
- Claude Code IS the agent — it already has vision, tools, and memory

---

## Future Considerations

- **Rubric scoring integration:** Currently the agent scores qualitatively by reading the skill instructions. A future version could add `--rubric-scores '{"pose_accuracy": 7.5}'` to `ue-eyes iterate` so rubric results are logged alongside quantitative scores in the same TSV row.
- **Batch mode:** Run N iterations with a strategy file (e.g., grid search) without agent involvement. Not needed now — the agent's judgment is the point.
- **Convergence detection:** Auto-detect when scores plateau and suggest the agent try a different strategy. Could be a simple heuristic in `get_loop_status()`.
