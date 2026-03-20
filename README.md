# UE Eyes

Give AI coding agents visual access to Unreal Engine 5.7 projects.

UE Eyes captures screenshots from the UE editor, analyzes them, and uses that information to drive iterative development and structured parameter tuning. Install it as a Claude Code plugin and use it with any UE 5.7 project.

## Quick Start

### Install as Claude Code Plugin

```bash
/plugin marketplace add Ancient23/ue-eyes
/plugin install ue-eyes
```

### Or install manually

```bash
git clone https://github.com/Ancient23/ue-eyes.git
cd ue-eyes
uv sync
```

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Unreal Engine 5.7 with:
  - Python Editor Script Plugin enabled
  - Remote Execution enabled (Editor Preferences > Python > Enable Remote Execution)

### Capture a screenshot

```bash
# Check UE is reachable
ue-eyes ping

# Capture from viewport
ue-eyes snap --output captures/

# Capture from a named camera
ue-eyes snap --output captures/ --camera "MyCameraActor"

# Discover cameras in your scene
ue-eyes cameras
```

## Two Modes

### Development Mode (Zero-config)

For iterative development and visual bug fixing. No setup needed — just capture and inspect.

```
User: "The shadows look wrong on this mesh"
Agent: captures viewport → analyzes → modifies light settings → captures again → "Fixed"
```

Use the `/ue-eyes:capture` skill for quick captures.

### Research Loop Mode (Setup required)

For structured parameter tuning with scientific methodology. Run `/ue-eyes:setup` to configure cameras, define parameters, and establish a baseline.

```
analyze → hypothesize → change ONE parameter → capture → compare → score → keep/discard → loop
```

Use the `/ue-eyes:research-loop` skill to run the experiment loop.

## CLI Commands

| Command | Description |
|---|---|
| `ue-eyes ping` | Check UE reachability |
| `ue-eyes snap` | Capture single frame |
| `ue-eyes render` | Batch render from Level Sequence |
| `ue-eyes cameras` | List cameras in the scene |
| `ue-eyes compare` | Generate side-by-side comparison images |
| `ue-eyes score` | Compute similarity metrics |

## Camera Tracking

Cameras can track actors or bones in the scene:

```toml
[cameras.closeup_face]
location = [0, -80, 170]
tracking_mode = "look_at"
target_actor = "BP_Character_01"
target_bone = "head"

[cameras.orbit_body]
tracking_mode = "follow"
target_actor = "BP_Character_01"
offset = [0, -200, 50]
```

Tracking modes: `fixed` (static), `look_at` (rotate toward target), `follow` (move with target).

## Optional UE Plugin

For persistent camera presets in the editor, copy `plugin/UEEyes/` into your project's `Plugins/` folder. The plugin adds:

- `UEEyesCameraPresetComponent` — Attach to actors to define reusable camera presets
- `UEEyesCaptureService` — Managed capture service (Blueprint-callable)

The plugin is optional — everything works via Python remote execution without it.

## Scoring

Built-in metrics: SSIM, Pixel MSE, Perceptual Hash. Add custom scorers:

```toml
[scoring]
metrics = ["ssim", "pixel_mse", "my_project.scoring:custom_scorer"]
composite_weights = { ssim = 0.6, pixel_mse = 0.4 }
```

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_scoring.py -v
```

## License

MIT
