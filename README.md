# UE Eyes

Give AI coding agents visual access to Unreal Engine 5.7 projects.

UE Eyes captures screenshots from the UE editor, analyzes them, and uses that information to drive iterative development and structured parameter tuning. Install it as a Claude Code plugin and use it with any UE 5.7 project.

## Inspiration

This project was inspired by Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch), which gives an AI agent a training script and lets it autonomously run ML experiments — editing code, training, measuring val_bpb, keeping improvements, reverting failures, and looping indefinitely. The core insight is powerful: give an agent a measurable objective, a single file to edit, and a fixed evaluation budget, then let it iterate with full creative reasoning.

UE Eyes applies that same autonomous experiment loop to Unreal Engine development. Where autoresearch optimizes a loss metric on a GPU, UE Eyes optimizes visual quality in a 3D scene. The agent captures screenshots instead of reading loss values, compares frames instead of checking val_bpb, and tunes scene parameters instead of model hyperparameters — but the methodology is identical: hypothesize, change one thing, measure, keep or revert, repeat.

The key difference is that UE Eyes also works outside the research loop. Not every problem needs structured optimization — sometimes an agent just needs to *see* what's happening in the editor. UE Eyes provides zero-config screenshot capture for iterative development alongside the full autoresearch-style experiment loop for parameter tuning.

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

### Building the C++ Plugin from Source

Pre-built binaries are not distributed because UE C++ plugins are tied to a specific engine `BuildId` — a binary built against one UE 5.7 installation will not load in another. You must compile the plugin against your own engine.

**Prerequisites**

- Unreal Engine 5.7 (source or installed build)
- Visual Studio 2022 (with "Game Development with C++" workload) or JetBrains Rider

**Steps**

1. Copy or symlink `plugin/UEEyes/` into your project's `Plugins/` folder:

   ```bash
   cp -r plugin/UEEyes /path/to/YourProject/Plugins/UEEyes
   # or on Windows (symlink, run as Administrator):
   # mklink /D "C:\YourProject\Plugins\UEEyes" "C:\Source\ue-eyes\plugin\UEEyes"
   ```

2. Right-click your `.uproject` file and select **Generate Visual Studio project files** (or run `UnrealBuildTool` manually).

3. Open the generated `.sln` (or `.uproject` in Rider) and build the **Development Editor** configuration for your project.

4. Launch the UE editor. The plugin will load automatically; enable it in **Edit > Plugins > UEEyes** if it is not already active.

> **Note:** If you see a "missing or incompatible module" dialog on editor start, the binary was built against a different engine version or BuildId. Rebuild as described above to resolve it.

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
