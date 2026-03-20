---
description: Structured experiment loop — tune UE parameters one at a time with visual scoring. Never stops.
---

# UE Eyes: Research Loop

A structured, never-ending experiment loop for tuning parameters in Unreal Engine. Each iteration changes ONE parameter, captures the result, scores it, and decides whether to keep or discard the change.

**CRITICAL RULE: Change only ONE parameter per experiment. No exceptions.**

## Prerequisites Check

Before starting, verify all required files and connections exist.

### 1. Verify config

```bash
cd <project-root> && test -f ue-eyes.toml && echo "Config exists" || echo "MISSING: run /ue-eyes:setup first"
```

### 2. Verify UE connection

```bash
cd <project-root> && uv run ue-eyes ping
```

If ping fails, do NOT proceed. Ask the user to check UE and remote execution settings.

### 3. Verify baseline captures

```bash
ls <project-root>/baseline/*.png 2>/dev/null | head -5
```

If no baseline exists, capture one now:
```bash
cd <project-root> && uv run ue-eyes snap --output baseline/
```

Read the baseline images to confirm they look correct.

### 4. Verify parameter file

```bash
cd <project-root> && test -f tune_params.json && echo "Params exist" || echo "MISSING: run /ue-eyes:setup first"
```

### 5. Verify rubric (optional but recommended)

```bash
cd <project-root> && test -f rubric.json && echo "Rubric exists" || echo "No rubric — will use quantitative scoring only"
```

### 6. Check loop state

```bash
cd <project-root> && uv run ue-eyes loop-status
```

This shows experiment count, best score so far, score trend, and which parameters have and have not been tested. Use this to understand whether you are resuming or starting fresh.

---

## The Loop

Repeat the following steps indefinitely. **NEVER STOP** unless the user explicitly asks you to stop or the goal score (from `rubric.json`) is reached.

### Step 1: ANALYZE

Get the current loop state in one command:

```bash
cd <project-root> && uv run ue-eyes loop-status
```

The output JSON tells you:
- `experiment_count` — how many experiments have been run
- `best_score` — highest composite score seen
- `best_experiment` — ID of the best run
- `score_trend` — last 10 scores (improving, plateauing, oscillating?)
- `parameters` — all parameters with their current values and types
- `tested_parameters` — parameters already tried
- `untested_parameters` — parameters not yet tried

If comparison images exist from the latest experiment, read them:
```bash
ls <project-root>/experiments/*/comparisons/*.png | tail -5
```

Read those comparison images to visually assess the current state.

Analyze:
- What is the current composite score?
- What is the trend?
- Which parameters have been tried? What worked, what did not?
- Which parameters have NOT been tried yet?
- Are there any patterns in what improves the score?

If a rubric exists, read it:
```bash
cat <project-root>/rubric.json
```

### Step 2: HYPOTHESIZE

Based on your analysis, form a hypothesis:

1. Pick **exactly ONE** parameter to change (prefer untested parameters first).
2. Decide the new value (within the defined min/max/options constraints shown in `loop-status`).
3. Write down your prediction: "Changing X from A to B should improve Y because Z."

Record this hypothesis — it will be logged with the experiment.

### Step 3: RUN EXPERIMENT

Run the iteration with a single command. The `iterate` command handles parameter mutation, capture, scoring, verdict, and revert automatically:

```bash
cd <project-root> && uv run ue-eyes iterate \
    --param <parameter_name> \
    --value <new_value> \
    --hypothesis "<your prediction>" \
    --baseline baseline/
```

The command outputs a JSON result:
```json
{
  "verdict": "keep",
  "parameter_name": "light_intensity",
  "old_value": 5000.0,
  "new_value": 8000.0,
  "best_previous_score": 0.75,
  "experiment_id": "exp_002",
  "composite_score": 0.88,
  "scores": {"ssim": 0.88}
}
```

Possible verdicts:
- `baseline` — first experiment, no prior results to compare against
- `keep` — new score beat the previous best; params file updated
- `discard` — new score did not improve; params file automatically reverted
- `failed` — capture or scoring error; params file automatically reverted

**No manual file editing or git operations needed** — `iterate` handles everything.

### Step 4: EVALUATE

#### Quantitative evaluation

Read the JSON output from `iterate`:
- `composite_score` — the score for this experiment
- `best_previous_score` — what was beaten (or not)
- `scores` — individual metric scores

#### Qualitative evaluation (if rubric.json exists)

Read the comparison images that were generated:
```bash
ls <project-root>/experiments/<experiment_id>/comparisons/*.png
```

For each criterion in `rubric.json`, score on a 0-10 scale:

```
criterion_name: <score> — <reasoning>
```

Example:
```
pose_accuracy: 7.5 — Upper body matches well, slight drift in left shoulder
joint_smoothness: 8.0 — No hyperextension visible, natural joint angles
hand_quality: 4.0 — Fingers still clipping through each other on left hand
```

#### Update baseline if significantly improved

If `verdict` is `keep` and the improvement is significant, update the baseline:
```bash
cp <project-root>/experiments/<experiment_id>/captures/*.png <project-root>/baseline/
```

### Step 5: LOOP

Go back to Step 1. **Do not stop.**

Between iterations:
- Run `uv run ue-eyes loop-status` to see the full updated state
- Verify UE is still connected: `uv run ue-eyes ping`

---

## Scoring Protocol

### Quantitative metrics

These are computed automatically by `ue-eyes iterate`:

| Metric | Range | What it measures |
|--------|-------|------------------|
| `ssim` | 0.0-1.0 | Structural similarity (higher = more similar) |
| `pixel_mse` | 0.0-1.0 | Inverse pixel mean squared error (higher = more similar) |
| `phash` | 0.0-1.0 | Perceptual hash similarity (higher = more similar) |

### Qualitative rubric

Score each criterion from `rubric.json` on a 0-10 scale by reading the comparison images. Be consistent across experiments — anchor your scores to the baseline (which is a 5 for all criteria by definition).

### Composite score

The final score for each experiment is a weighted combination of quantitative metrics (from `ue-eyes.toml` → `[scoring].composite_weights`) and qualitative rubric scores. Use this composite to make keep/discard decisions.

---

## One Parameter at a Time

This rule is non-negotiable. Here is why:

- If you change two parameters and the score improves, you do not know which change helped.
- If you change two parameters and the score gets worse, you do not know which change hurt.
- Single-variable experiments build a clear causal map of parameter effects.

If you believe two parameters interact, test them in sequence:
1. Change parameter A, measure.
2. Change parameter B, measure.
3. Now you know the individual effects and can reason about interactions.

---

## When Stuck

If the score plateaus or you run out of obvious parameter changes, use these escalation strategies:

### 1. Review the full history

```bash
cd <project-root> && uv run ue-eyes loop-status
```

The `tested_parameters` and `untested_parameters` fields show what remains. Also inspect `score_trend` for direction.

For full raw history:
```bash
cat <project-root>/experiments/results.tsv
```

Look for:
- Parameters you have not tried yet
- Parameters where small changes helped — try larger changes
- Parameters where changes hurt — try the opposite direction
- The best experiment ever — what was different about it?

### 2. Try boundary values

For each parameter, try its min and max values (visible in `loop-status` output under `parameters`). Extreme values often reveal whether a parameter matters at all.

### 3. Binary search

If you know a parameter matters but have not found the optimal value:
1. Try the midpoint of the current range.
2. Based on whether it improved, narrow the range.
3. Repeat until changes are below a meaningful threshold.

### 4. Re-examine the rubric

Read the comparison images from the best experiment and the worst recent experiment. Ask:
- Is the rubric measuring the right things?
- Are the weights appropriate?
- Should a criterion be split into sub-criteria?

If the rubric needs updating, ask the user before changing it.

### 5. Ask the user

If all automated strategies are exhausted, present your findings:
- Summary from `ue-eyes loop-status`
- Which parameters had the most impact
- What you think the bottleneck is
- Specific questions about what to try next

---

## File Reference

| File | Purpose |
|------|---------|
| `ue-eyes.toml` | Project configuration (connection, cameras, scoring) |
| `tune_params.json` | Parameter definitions and current values |
| `rubric.json` | Qualitative scoring criteria and weights |
| `baseline/*.png` | Reference captures for comparison |
| `experiments/results.tsv` | Tab-separated experiment log |
| `experiments/exp_NNN/captures/` | Captured frames for experiment NNN |
| `experiments/exp_NNN/comparisons/` | Side-by-side and diff images for experiment NNN |
| `experiments/exp_NNN/result.json` | Full result data for experiment NNN |

## CLI Commands

| Command | What it does |
|---------|-------------|
| `ue-eyes iterate --param P --value V --hypothesis H --baseline B/` | Run one full experiment iteration (mutate, capture, score, decide, revert if needed) |
| `ue-eyes loop-status` | Show experiment count, best score, score trend, parameter coverage |
| `ue-eyes ping` | Check UE connection |
| `ue-eyes snap --output DIR/` | Capture a single frame |
| `ue-eyes score --reference R/ --capture C/` | Score a capture against a reference |

## Results TSV Format

The `results.tsv` file has these columns:

| Column | Description |
|--------|-------------|
| `experiment` | Experiment ID (e.g., `exp_001`) |
| `timestamp` | ISO 8601 timestamp |
| `parameter` | Name of the changed parameter |
| `old_value` | Previous value |
| `new_value` | New value |
| `hypothesis` | What you predicted would happen |
| `composite_score` | Weighted composite score |
| `metric_scores_json` | JSON object of individual metric scores |
| `verdict` | `baseline`, `keep`, `discard`, or `failed` |
| `notes` | Additional observations |
