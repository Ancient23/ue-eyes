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

### 6. Verify results history

```bash
cd <project-root> && test -f experiments/results.tsv && echo "Results exist — resuming" || echo "Fresh start — no prior experiments"
```

If `experiments/results.tsv` exists, read it to understand what has been tried.

---

## The Loop

Repeat the following steps indefinitely. **NEVER STOP** unless the user explicitly asks you to stop or the goal score (from `rubric.json`) is reached.

### Step 1: ANALYZE

Read the current state:

```bash
# Read experiment history
cat <project-root>/experiments/results.tsv

# Read current parameters
cat <project-root>/tune_params.json

# Read rubric for goal score
cat <project-root>/rubric.json
```

If comparison images exist from the latest experiment, read them:
```bash
ls <project-root>/experiments/*/comparisons/*.png | tail -5
```

Read those comparison images to visually assess the current state.

Analyze:
- What is the current composite score?
- What is the trend? (Improving, plateauing, oscillating?)
- Which parameters have been tried? What worked, what did not?
- Which parameters have NOT been tried yet?
- Are there any patterns in what improves the score?

### Step 2: HYPOTHESIZE

Based on your analysis, form a hypothesis:

1. Pick **exactly ONE** parameter to change.
2. Decide the new value (within the defined min/max range).
3. Write down your prediction: "Changing X from A to B should improve Y because Z."

Record this hypothesis — it will be logged with the experiment.

### Step 3: EDIT

Modify `tune_params.json` — change only the ONE parameter you chose.

```bash
# Read current params
cat <project-root>/tune_params.json
```

Edit the file, changing only the `"value"` field of your chosen parameter.

Commit the change:
```bash
cd <project-root> && git add tune_params.json && git commit -m "experiment: change <param_name> from <old> to <new>

Hypothesis: <your prediction>"
```

### Step 4: RUN EXPERIMENT

Generate a unique experiment ID (use format `exp_NNN` where NNN is the next number):

```bash
# Count existing experiments
ls -d <project-root>/experiments/exp_* 2>/dev/null | wc -l
```

Apply the parameter change (project-specific — this depends on how parameters are consumed). Then capture:

```bash
cd <project-root> && uv run ue-eyes snap --output experiments/exp_<NNN>/captures/
```

Generate comparison images against the baseline:

```bash
cd <project-root> && uv run ue-eyes compare \
    --reference baseline/ \
    --capture experiments/exp_<NNN>/captures/ \
    --output experiments/exp_<NNN>/comparisons/
```

Compute quantitative scores:

```bash
cd <project-root> && uv run ue-eyes score \
    --reference baseline/ \
    --capture experiments/exp_<NNN>/captures/ \
    --metrics ssim
```

### Step 5: EVALUATE

#### Quantitative evaluation

Record the scores from the `ue-eyes score` output. Note the composite score and individual metric scores.

#### Qualitative evaluation (if rubric.json exists)

Read the comparison images (side-by-side and diff heatmaps) from `experiments/exp_<NNN>/comparisons/`.

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

Compute the weighted composite from your rubric scores.

#### Compare to previous best

Read the best score from results history:
```bash
# Find best composite score in results.tsv
cat <project-root>/experiments/results.tsv
```

Is the new composite score higher than the previous best?

### Step 6: KEEP or DISCARD

#### If IMPROVED (new score > previous best):

**Keep the change.**

```bash
# Log the result — the experiment runner handles this, but verify it was logged
cat <project-root>/experiments/results.tsv | tail -1
```

Update the baseline if the improvement is significant:
```bash
# Copy new captures as the new baseline
cp <project-root>/experiments/exp_<NNN>/captures/*.png <project-root>/baseline/
```

#### If WORSE or NO CHANGE (new score <= previous best):

**Discard the change.** Revert `tune_params.json` to its previous state:

```bash
cd <project-root> && git revert HEAD --no-edit
```

Log the result with verdict "discard" so you do not repeat this change.

#### If FAILED (capture error, scoring error, UE crash):

**Log and revert.**

```bash
cd <project-root> && git revert HEAD --no-edit
```

Record the failure in your analysis for the next iteration. Common failures:
- UE connection lost: run `ue-eyes ping`, wait for editor to respond
- Capture returned black frames: check that the level is loaded and viewport is active
- Score computation failed: check that baseline and capture have matching frame counts

### Step 7: LOOP

Go back to Step 1. **Do not stop.**

Between iterations:
- Re-read `results.tsv` to see the full history
- Re-read `tune_params.json` to see the current parameter state
- Verify UE is still connected: `uv run ue-eyes ping`

---

## Scoring Protocol

### Quantitative metrics

These are computed automatically by `ue-eyes score`:

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
cat <project-root>/experiments/results.tsv
```

Look for:
- Parameters you have not tried yet
- Parameters where small changes helped — try larger changes
- Parameters where changes hurt — try the opposite direction
- The best experiment ever — what was different about it?

### 2. Try boundary values

For each parameter, try its min and max values. Extreme values often reveal whether a parameter matters at all.

### 3. Binary search

If you know a parameter matters but have not found the optimal value:
1. Try the midpoint of the current range.
2. Based on whether it improved, narrow the range.
3. Repeat until changes are below a meaningful threshold.

### 4. Reset to best known

If recent experiments have all been discards:
```bash
cd <project-root> && git log --oneline experiments/results.tsv | head -20
```

Find the commit with the best score and reset `tune_params.json` to those values. Then explore different parameters.

### 5. Re-examine the rubric

Read the comparison images from the best experiment and the worst recent experiment. Ask:
- Is the rubric measuring the right things?
- Are the weights appropriate?
- Should a criterion be split into sub-criteria?

If the rubric needs updating, ask the user before changing it.

### 6. Ask the user

If all automated strategies are exhausted, present your findings:
- Summary of all experiments and their scores
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
