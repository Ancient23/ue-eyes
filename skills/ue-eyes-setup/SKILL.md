---
description: Interactive setup wizard for UE Eyes. Guides through connection, cameras, scoring, and config.
---

# UE Eyes: Setup Wizard

Walk the user through full UE Eyes configuration. This skill produces a working `ue-eyes.toml`, and optionally `tune_params.json` and `rubric.json` for the research loop.

## Step 1: Verify Connection

Test that the UE editor is reachable via remote execution.

```bash
cd <project-root> && uv run ue-eyes ping
```

**If ping succeeds:** proceed to Step 2.

**If ping fails**, troubleshoot:

1. Confirm UE 5.7 editor is running.
2. Confirm **Python Editor Script Plugin** is enabled (Edit → Plugins → search "Python").
3. Confirm **Remote Execution** is enabled:
   - Editor Preferences → Python → Enable Remote Execution → checked
   - Multicast Group: `239.0.0.1` (default)
   - Multicast Port: `6766` (default)
4. Check firewall — UDP port 6766 must be open for multicast. On Windows, allow inbound/outbound UDP 6766 for `UnrealEditor.exe`.
5. If using a non-default address, note the values for later config.

Re-run ping after each fix. Do not proceed until ping succeeds.

## Step 2: Discover Scene

List cameras and gather scene information.

```bash
cd <project-root> && uv run ue-eyes cameras
```

Record the output. Note:
- Names of existing CameraActor instances
- Their locations and rotations
- Any skeletal mesh actors that might be targets for tracking cameras

If no cameras exist, that is fine — we will define presets in Step 4.

## Step 3: Ask User Goal

Ask the user which mode they need:

1. **Development Mode** — Zero-config. The agent captures ad-hoc screenshots to see UE state. No further setup needed. Skip to Step 8 and write a minimal config.

2. **Research Loop** — Structured parameter tuning with scoring and comparison. Continue to Step 4.

If the user picks Development Mode, write this minimal `ue-eyes.toml`:

```toml
version = 1

[connection]
multicast_group = "239.0.0.1"
multicast_port = 6766
timeout = 30
```

Then stop — setup is complete.

## Step 4: Camera Presets (Research Loop)

Help the user define named cameras for repeatable captures. Each camera needs:

| Field | Type | Description |
|-------|------|-------------|
| `location` | `[x, y, z]` | World position in UE units (cm) |
| `rotation` | `[pitch, yaw, roll]` | Rotation in degrees |
| `tracking_mode` | `"fixed"`, `"look_at"`, or `"follow"` | How the camera behaves |
| `target_actor` | string | Actor name for look_at/follow modes |
| `target_bone` | string | Optional bone name on the target actor |
| `offset` | `[x, y, z]` | Offset from target for follow mode |

Common presets to suggest:

**Front view (fixed):**
```toml
[cameras.front]
location = [0, -200, 100]
rotation = [0, 0, 0]
tracking_mode = "fixed"
```

**Look-at camera (tracks an actor):**
```toml
[cameras.face]
location = [0, -80, 160]
rotation = [0, 0, 0]
tracking_mode = "look_at"
target_actor = "BP_Character"
target_bone = "head"
```

**Follow camera (moves with an actor):**
```toml
[cameras.orbit]
tracking_mode = "follow"
target_actor = "BP_Character"
offset = [0, -200, 50]
```

Ask the user what they want to see. Define at least one camera. Record all presets for the config file.

## Step 5: Capture Baseline (Research Loop)

Take reference screenshots from all configured cameras. These are the "before" images that all experiments compare against.

```bash
cd <project-root> && uv run ue-eyes snap --output baseline/
```

For each configured camera:
```bash
cd <project-root> && uv run ue-eyes snap --output baseline/ --camera "<camera-name>"
```

Read the captured images to verify they look correct. If any are wrong (black, wrong angle, missing content), fix the camera preset and re-capture before proceeding.

## Step 6: Define Parameters (Research Loop)

Help the user create `tune_params.json`. This file defines the parameter space for experiments.

The format is:

```json
{
  "version": 1,
  "parameters": {
    "param_name": {
      "type": "float",
      "value": 1.0,
      "min": 0.0,
      "max": 10.0,
      "description": "What this parameter controls"
    },
    "mode_select": {
      "type": "enum",
      "value": "option_a",
      "options": ["option_a", "option_b", "option_c"],
      "description": "Which mode to use"
    },
    "enabled_flag": {
      "type": "bool",
      "value": true,
      "description": "Whether feature X is active"
    }
  }
}
```

Supported types:
- **float** — requires `min`, `max`, `value`
- **int** — requires `min`, `max`, `value`
- **bool** — requires `value` (true/false)
- **enum** — requires `options` (list of strings), `value` (one of the options)
- **str** — requires `value`

Ask the user:
1. What parameters control the thing they are tuning?
2. What are reasonable ranges for each?
3. What is the current (starting) value?

Write the file:
```bash
# Write tune_params.json in the project root
```

Validate it loads correctly:
```python
# Quick validation — run via Python
import json
from pathlib import Path
data = json.loads(Path("tune_params.json").read_text())
assert "version" in data
assert "parameters" in data
for name, defn in data["parameters"].items():
    assert "type" in defn, f"{name} missing type"
    assert "value" in defn, f"{name} missing value"
print(f"Valid: {len(data['parameters'])} parameters defined")
```

## Step 7: Generate Scoring Rubric (Research Loop)

Collaborate with the user to define qualitative evaluation criteria. Write `rubric.json`.

The format is:

```json
{
  "name": "Descriptive Rubric Name",
  "scale": [0, 10],
  "goal_score": 8.0,
  "criteria": [
    {
      "name": "criterion_name",
      "weight": 1.0,
      "description": "Detailed description of what score 0 vs 10 means for this criterion."
    }
  ]
}
```

Guidelines for good criteria:
- Use snake_case names (these appear in scoring output)
- Weights should sum to a meaningful total (they are normalized)
- Descriptions should define what 0, 5, and 10 mean concretely
- 3-6 criteria is typical; avoid more than 8

Ask the user:
1. What does "good" look like? What does "bad" look like?
2. Are there specific aspects to evaluate separately (e.g., position accuracy, visual quality, timing)?
3. How important is each aspect relative to the others?

Example rubric for a character animation project:

```json
{
  "name": "Animation Quality",
  "scale": [0, 10],
  "goal_score": 7.5,
  "criteria": [
    {
      "name": "pose_accuracy",
      "weight": 2.0,
      "description": "How well the pose matches the reference. 0=completely wrong, 5=roughly correct but visibly off, 10=pixel-perfect match."
    },
    {
      "name": "joint_smoothness",
      "weight": 1.0,
      "description": "Whether joints look natural. 0=severe hyperextension or clipping, 5=minor artifacts, 10=perfectly natural."
    },
    {
      "name": "hand_quality",
      "weight": 1.5,
      "description": "Finger and hand pose quality. 0=mangled/clipping, 5=roughly shaped but stiff, 10=natural hand poses."
    }
  ]
}
```

Write `rubric.json` to the project root.

## Step 8: Write Config

Generate the final `ue-eyes.toml` incorporating all settings from previous steps.

Full config template:

```toml
version = 1

[connection]
multicast_group = "239.0.0.1"
multicast_port = 6766
timeout = 30

[capture]
mode = "snap"
default_resolution = [1920, 1080]

[cameras.front]
location = [0, -200, 100]
rotation = [0, 0, 0]
tracking_mode = "fixed"

[cameras.face]
location = [0, -80, 160]
rotation = [0, 0, 0]
tracking_mode = "look_at"
target_actor = "BP_Character"
target_bone = "head"

[scoring]
metrics = ["ssim"]
composite_weights = { ssim = 1.0 }

[parameters]
file = "tune_params.json"
```

Write the file to `<project-root>/ue-eyes.toml`.

Verify the config loads:
```bash
cd <project-root> && uv run ue-eyes ping
```

## Setup Complete Checklist

Confirm all artifacts exist:

| File | Required for | Created |
|------|-------------|---------|
| `ue-eyes.toml` | All modes | Yes |
| `baseline/` | Research loop | If applicable |
| `tune_params.json` | Research loop | If applicable |
| `rubric.json` | Research loop | If applicable |

Tell the user:
- **Development mode:** Use `/ue-eyes:capture` for ad-hoc screenshots.
- **Research loop:** Use `/ue-eyes:research-loop` to start the experiment cycle.

## Error Recovery

| Problem | Solution |
|---------|----------|
| Ping fails after config write | Re-check connection settings in `ue-eyes.toml`. Ensure UE is still running. |
| Baseline captures are black | The viewport may not be rendering. Open a viewport in UE, ensure the level is loaded, try again. |
| Camera not found | Run `ue-eyes cameras` to list available cameras. Check spelling. Camera actors must exist in the level. |
| Parameter validation fails | Check types and ranges in `tune_params.json`. Run the validation snippet from Step 6. |
| Rubric parse error | Ensure valid JSON. Check that all criteria have `name`, `weight`, and `description` fields. |
