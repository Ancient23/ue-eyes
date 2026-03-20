# UE Eyes — Design Specification

**Date:** 2026-03-19
**Repository:** `Ancient23/ue-eyes` (GitHub)
**Target:** Unreal Engine 5.7
**Status:** Draft

## Purpose

UE Eyes gives AI coding agents visual access to Unreal Engine projects. It captures screenshots from the UE editor, analyzes them, and uses that information to drive iterative development and structured parameter tuning.

Users install it as a Claude Code plugin. It works with any UE 5.7 project — no domain-specific knowledge required.

## Two Workflow Modes

### Development Mode (Zero-config)

For iterative development and visual bug fixing. No setup, no config files. The agent uses captures ad-hoc to understand visual state, make changes, and verify results.

Flow: user describes problem → agent captures → agent analyzes → agent modifies code/config → agent captures again → repeat until resolved.

### Research Loop Mode (Setup required)

For structured parameter tuning with scientific methodology. User runs `/ue-eyes:setup` to configure cameras, define a parameter space, establish a baseline, and generate a scoring rubric.

Flow: analyze results → hypothesize → change ONE parameter → capture → compare against baseline → score (quantitative + qualitative) → keep or discard → log → loop indefinitely.

One variable at a time. Commit before each experiment. Revert on discard.

## Repository Structure

The repository root is itself a Claude Code plugin. Users install via GitHub marketplace.

```
ue-eyes/
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # GitHub marketplace discovery
├── skills/
│   ├── ue-eyes-setup/SKILL.md   # Interactive setup wizard
│   ├── capture/SKILL.md         # Zero-config quick capture
│   └── research-loop/SKILL.md   # Structured experiment loop
├── agents/                      # Agent definitions if needed
├── ue_eyes/                     # Python package (core library)
│   ├── __init__.py
│   ├── remote_exec.py           # UE Python remote execution (UDP/TCP)
│   ├── capture.py               # snap_frame(), render_sequence()
│   ├── cameras.py               # Presets, discovery, spawn/move, tracking
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── metrics.py           # Built-in: SSIM, pixel MSE, perceptual hash
│   │   ├── compare.py           # Side-by-side, difference maps, grids
│   │   └── rubric.py            # Agent-generated qualitative rubric system
│   ├── experiment/
│   │   ├── __init__.py
│   │   ├── runner.py            # Generic experiment loop
│   │   ├── params.py            # Parameter space definition & mutation
│   │   └── results.py           # TSV/JSON experiment tracking
│   ├── config.py                # Load/validate ue-eyes.toml
│   ├── cli.py                   # Click CLI
│   └── unreal_scripts/          # Python scripts injected into UE
│       ├── capture_frame.py
│       ├── render_sequence.py
│       ├── camera_control.py
│       └── scene_info.py        # Discover cameras, actors, properties
├── plugin/                      # Optional UE 5.7 C++ plugin
│   └── UEEyes/
│       ├── UEEyes.uplugin
│       └── Source/UEEyes/
│           ├── UEEyes.Build.cs
│           ├── Public/
│           │   ├── UEEyesCameraPresetComponent.h
│           │   └── UEEyesCaptureService.h
│           └── Private/
│               ├── UEEyesCameraPresetComponent.cpp
│               ├── UEEyesCaptureService.cpp
│               └── UEEyesModule.cpp
├── tests/
│   ├── test_remote_exec.py
│   ├── test_capture.py
│   ├── test_cameras.py
│   ├── test_scoring.py
│   └── test_experiment.py
├── pyproject.toml               # uv package definition
├── ue-eyes.example.toml         # Example config
├── README.md
└── CLAUDE.md                    # Project instructions
```

## Core Python Package: `ue_eyes/`

### Remote Execution (`remote_exec.py`)

UE 5.7's native Python remote execution protocol over UDP multicast discovery + TCP command channel.

The legacy `command_ip`/`command_port` parameters from the source are not carried forward — only the multicast protocol is used.

```python
class UERemoteExecution:
    """Context manager for UE Python remote execution."""
    def __init__(self, multicast_group="239.0.0.1", multicast_port=6766, timeout=30.0) -> None
    def connect() -> None
    def execute(python_code: str) -> dict
    def execute_file(script_path: str, **params) -> dict
    def ping() -> bool
    def close() -> None
```

Connection flow:
1. Client joins UDP multicast group (default `239.0.0.1:6766`)
2. Client sends ping → UE replies with pong
3. Client starts local TCP server on random port
4. Client sends `open_connection` with TCP address
5. UE connects back to client's TCP server
6. Commands flow as JSON over TCP

Requirements: UE 5.7 with Python Editor Script Plugin enabled, Remote Execution enabled in editor preferences.

### Capture (`capture.py`)

Two capture modes. Capture auto-detects whether the UE Eyes plugin is installed. When present, `snap_frame()` delegates to `AUEEyesCaptureService` (which manages SceneCapture2D lifecycle). When absent, `snap_frame()` spawns a transient SceneCapture2D, captures, and destroys it.

**`snap_frame(output_dir, camera=None, width=1920, height=1080) -> dict`**
- Single frame from PIE viewport or named CameraActor
- Returns capture manifest dict with file paths

**`render_sequence(output_dir, sequence_path, map_path, frames=None, frame_range=None, frame_step=1, width=1920, height=1080) -> dict`**
- Batch render via Movie Render Graph (MoviePipelinePIEExecutor)
- Frame selection via explicit list or range with step
- Returns capture manifest with all output file paths

Both write `capture_manifest.json` to output directory.

### Cameras (`cameras.py`)

Camera management with three capabilities:

**Discovery:**
```python
def discover_cameras() -> list[CameraInfo]
```
Queries UE scene for all CameraActor instances. Returns names and transforms.

**Presets:**
```python
def apply_preset(preset_name: str, config: UEEyesConfig) -> None
```
Loads named camera position/rotation/tracking from `ue-eyes.toml` or UEEyesCameraPresetComponent (if plugin installed). Spawns or moves camera to preset position before capture.

**Ad-hoc:**
```python
def spawn_camera(location, rotation, name="ue_eyes_adhoc") -> str
def move_camera(name: str, location, rotation) -> None
def destroy_camera(name: str) -> None
```
Agent creates transient cameras for investigation.

**Tracking modes** (applies to presets and ad-hoc):
- `fixed` — Static position and rotation (default)
- `look_at` — Camera stays at position, rotates to face target actor/bone
- `follow` — Camera maintains offset relative to target actor/bone, moves with it

Tracking config per camera:
- `target_actor` — Name of actor to track
- `target_bone` — Optional bone/socket name on target's skeletal mesh
- `tracking_mode` — `fixed`, `look_at`, or `follow`
- `offset` — Position offset from target (for follow mode)

Before each capture, the system queries the target's world transform (or bone component-space transform), computes final camera position/rotation, and applies it.

### Config (`config.py`)

Loads `ue-eyes.toml`. Config discovery order: current working directory first, then walks up to the git root. Zero-config mode uses built-in defaults when no config file exists. All fields optional.

```toml
version = 1

[connection]
multicast_group = "239.0.0.1"      # UE remote execution multicast address
multicast_port = 6766               # UE remote execution multicast port
timeout = 30

[capture]
mode = "snap"                        # or "render"
default_resolution = [1920, 1080]
sequence_path = ""                   # for render mode
map_path = ""                        # for render mode

[cameras.front]
location = [0, -200, 100]
rotation = [0, 0, 0]
tracking_mode = "look_at"
target_actor = "BP_Character_01"
target_bone = "head"

[cameras.orbit]
tracking_mode = "follow"
target_actor = "BP_Character_01"
offset = [0, -200, 50]

[scoring]
metrics = ["ssim"]                   # built-in metrics to compute
composite_weights = { ssim = 1.0 }
# Custom: metrics = ["ssim", "my_module:my_scorer"]

[parameters]
file = "tune_params.json"            # only for research loop mode
```

## Scoring System (`ue_eyes/scoring/`)

### Built-in Metrics (`metrics.py`)

All metrics follow the same interface:

```python
def score(reference: Path, capture: Path) -> float:
    """Return 0.0-1.0 where 1.0 = perfect match."""
```

Built-in metrics:
- **SSIM** — Structural similarity index. Good for "does this match the reference?"
- **Pixel MSE** — Mean squared error, normalized to 0-1. Simple, fast, detects any change.
- **Perceptual hash distance** — Resistant to minor compression/aliasing. "Roughly the same image?"

### Pluggable Custom Metrics

Users register custom scorers via dotted Python paths in config:

```toml
metrics = ["ssim", "pixel_mse", "my_project.scoring:particle_count_scorer"]
```

Custom scorers are imported and called with the same `(reference, capture) -> float` interface.

### Comparison Visualization (`compare.py`)

- `create_comparison(ref, capture)` — Side-by-side PNG with labels
- `create_difference_map(ref, capture)` — JET colormap heatmap of pixel differences
- `create_comparison_grid(pairs, max=12)` — Grid of multiple frame pairs

### Agent Rubric System (`rubric.py`)

During setup, the agent collaborates with the user to define a qualitative scoring rubric stored as JSON:

```json
{
  "name": "Lighting Quality",
  "criteria": [
    {
      "name": "shadow_direction",
      "weight": 0.3,
      "description": "Shadows should fall consistently from the key light at 45 degrees"
    },
    {
      "name": "ambient_balance",
      "weight": 0.3,
      "description": "Dark areas should have subtle fill, not pure black"
    },
    {
      "name": "highlight_rolloff",
      "weight": 0.4,
      "description": "Bright areas should have smooth gradients, no harsh clipping"
    }
  ],
  "goal_score": 8.0,
  "scale": "0-10"
}
```

The rubric module provides functions for the agent to score captures:

```python
def format_rubric_prompt(rubric: dict, capture_paths: list[Path], reference_paths: list[Path] | None = None) -> str:
    """Build a structured prompt for the agent to score each criterion.
    Includes the rubric criteria, descriptions, and paths to the images
    the agent should examine."""

def parse_rubric_scores(agent_response: str, rubric: dict) -> RubricResult:
    """Parse the agent's scoring response into structured scores.
    Returns per-criterion scores and weighted composite."""
```

`RubricResult` is a dataclass:
```python
@dataclass
class RubricResult:
    per_criterion: dict[str, float]    # criterion name -> score (0-10)
    composite: float                    # weighted composite
    reasoning: dict[str, str]          # criterion name -> agent's reasoning
```

The rubric is generated once during setup and reused across experiments. The agent can propose refinements if criteria aren't capturing what matters.

## Experiment System (`ue_eyes/experiment/`)

### Parameter Space (`params.py`)

Generic parameter definitions with type, range, and constraints:

```json
{
  "version": 1,
  "parameters": {
    "light_intensity": {"value": 5000, "type": "float", "min": 0, "max": 50000},
    "shadow_bias": {"value": 0.5, "type": "float", "min": 0, "max": 2.0},
    "enable_ao": {"value": true, "type": "bool"},
    "post_process_preset": {
      "value": "cinematic",
      "type": "enum",
      "options": ["default", "cinematic", "filmic"]
    }
  }
}
```

Capabilities: load/save, diff two parameter sets, validate changes (type, range).

The agent decides which parameter to change and what value. The user can also define parameters, or the agent can help generate the parameter space during setup.

### Experiment Runner (`runner.py`)

Generic 6-step loop:

1. **APPLY** — Execute user's action script, or agent modifies code/config directly
2. **CAPTURE** — Snap/render from configured cameras
3. **COMPARE** — Side-by-side + diff maps against reference/baseline
4. **SCORE** — Quantitative metrics + agent qualitative rubric
5. **DECIDE** — Keep (score improved) or discard (revert)
6. **LOG** — Append to results tracker

**Apply modes** determined by argument combination:

| `apply_fn` | `params` | Mode | Behavior |
|---|---|---|---|
| provided | provided | **Hybrid** | Runner calls `apply_fn(params)` with agent-chosen parameter values |
| provided | `None` | **Script** | Runner calls `apply_fn()` with no arguments; script handles its own logic |
| `None` | any | **Agent** | Step 1 is a no-op — the agent has already made changes before calling `run_experiment()` |

```python
@dataclass
class ExperimentResult:
    experiment_id: str
    timestamp: str                          # ISO 8601
    params_before: dict | None              # parameter snapshot before change
    params_after: dict | None               # parameter snapshot after change
    parameter_changed: str | None           # name of the single parameter changed
    hypothesis: str                         # agent's hypothesis for this experiment
    scores: dict[str, float]                # metric name -> score (0.0-1.0)
    composite_score: float                  # weighted composite of all metrics
    rubric_result: RubricResult | None      # qualitative rubric scores, if configured
    verdict: str                            # "baseline", "keep", "discard", "failed"
    error: str | None                       # error message if verdict == "failed"
    notes: str                              # free-text notes
    capture_dir: Path                       # path to captured frames
    comparison_dir: Path                    # path to comparison images

class ExperimentRunner:
    def __init__(self, config: UEEyesConfig) -> None
    def set_baseline(self, reference_dir: Path) -> None
    def run_experiment(self,
        experiment_id: str,
        apply_fn: Callable | None = None,
        params: dict | None = None,
    ) -> ExperimentResult
```

**Error handling:** If capture fails (UE connection lost, timeout, script error), the experiment is logged as failed with `verdict="failed"` and the error message in the `error` field. The runner does NOT retry automatically. The loop continues to the next iteration after logging.

### Results Tracking (`results.py`)

TSV log with columns:

```
experiment | timestamp | parameter | old_value | new_value | hypothesis | composite_score | metric_scores_json | verdict | notes
```

The `metric_scores_json` column contains a JSON-encoded dict of metric name to score (e.g., `{"ssim": 0.82, "pixel_mse": 0.91}`).

Per-experiment directory structure:

```
experiments/
├── 000/              # baseline
│   ├── captures/
│   ├── comparisons/
│   └── result.json
├── 001/
└── ...
```

## CLI (`cli.py`)

Click-based CLI exposing core functionality:

| Command | Description |
|---|---|
| `ue-eyes ping [--host HOST] [--port PORT]` | Check UE reachability via multicast ping |
| `ue-eyes snap --output DIR [--camera NAME] [--width W] [--height H]` | Capture single frame from viewport or named camera |
| `ue-eyes render --output DIR --sequence PATH --map PATH [--frames 0,29,59] [--range 0-100] [--step 5] [--width W] [--height H]` | Batch render from Level Sequence |
| `ue-eyes cameras` | Discover and list all cameras in the current UE scene |
| `ue-eyes compare --reference DIR --capture DIR --output DIR` | Generate comparison images (side-by-side + diff maps) |
| `ue-eyes score --reference DIR --capture DIR [--metrics ssim,pixel_mse]` | Compute quantitative scores between reference and capture |

The `setup` and `run` operations are skill-driven (interactive, require agent context) and are not exposed as CLI commands. The CLI provides the non-interactive building blocks that skills and agents compose.

## UE Plugin (Optional)

### `UEEyes` — Minimal UE 5.7 Plugin

Users drop into `Plugins/` only if they want persistent camera presets and a capture service actor. The system works without the plugin via pure Python remote execution.

**Dependencies:** Runtime module only (Core, CoreUObject, Engine). No UnrealEd dependency. The plugin uses runtime APIs (SceneCapture2D) that work during PIE sessions. It does not depend on editor-only modules.

### Components

**`UUEEyesCameraPresetComponent`**

Attach to any actor to mark it as a camera preset. Properties:
- `PresetName` (FString) — Unique identifier
- `Resolution` (FIntPoint) — Optional resolution override
- `TrackingMode` (enum) — Fixed, LookAt, Follow
- `TargetActor` (TSoftObjectPtr<AActor>) — Actor to track
- `TargetBone` (FName) — Optional bone/socket on target
- `Offset` (FVector) — Position offset from target (for Follow mode)
- `Notes` (FString) — Description of what this camera shows

Python tools discover these via remote exec querying for actors with this component.

**`AUEEyesCaptureService`**

Optional persistent actor. Manages SceneCapture2D lifecycle so transient captures don't leak. Blueprint-callable: `CaptureFromPreset(Name)`, `CaptureFromViewport()`.

### Pure Python Fallback

When the plugin is not installed:
- `snap_frame()` spawns temporary SceneCapture2D, captures, destroys it
- Camera discovery finds all CameraActor instances in the level
- Camera presets come from `ue-eyes.toml`
- Python code auto-detects plugin presence (queries for `UEEyesCaptureService` actors) and uses the richer API if available, falls back to transient actors if not

## Claude Code Integration

### Skills

**`/ue-eyes:setup`** — Interactive setup wizard:
1. Ping UE to verify connection
2. Discover cameras and actors in the scene
3. Ask user what they want to accomplish
4. Help define camera presets (or use discovered cameras)
5. Capture a baseline
6. For research loop: help define parameter space + generate scoring rubric
7. Write `ue-eyes.toml`, `tune_params.json`, `rubric.json`

**`/ue-eyes:capture`** — Zero-config quick capture. Snaps PIE viewport or specified camera. No setup required.

**`/ue-eyes:research-loop`** — Start structured experiment loop. Requires prior setup. Runs indefinitely: analyze → hypothesize → change one param → capture → score → keep/discard → loop.

### Distribution

GitHub marketplace via `Ancient23/ue-eyes`. Users install with:

```
/plugin marketplace add Ancient23/ue-eyes
/plugin install ue-eyes
```

The `/ue-eyes:setup` skill handles first-run environment setup (verifying Python/uv, running `uv sync`, checking UE connection).

## Unreal Scripts (`ue_eyes/unreal_scripts/`)

Python scripts that execute inside UE via remote execution. Injected with parameters via `_ue_eyes_params` dict.

- **`capture_frame.py`** — Spawns SceneCapture2D, configures render target, exports PNG, writes manifest
- **`render_sequence.py`** — Configures Movie Render Graph pipeline, renders frame list/range
- **`camera_control.py`** — Spawn, move, destroy cameras. Apply tracking (look-at/follow) by querying target transforms
- **`scene_info.py`** — Discover all CameraActors, find actors by class/tag, list skeletal mesh bones, read actor properties

## Testing

All tests use pytest. Mock UE connection for unit tests; integration tests require running UE editor.

- `test_remote_exec.py` — Connection, execute, ping, error handling
- `test_capture.py` — Snap frame, render sequence, manifest format
- `test_cameras.py` — Discovery, presets, tracking math, spawn/destroy
- `test_scoring.py` — SSIM, pixel MSE, perceptual hash, custom scorer loading, rubric scoring
- `test_experiment.py` — Parameter loading/diffing, experiment runner, results logging

## Code Style

- Python: snake_case, type hints on public functions, numpy for math (no scipy)
- C++: UE conventions (F-prefix structs, U-prefix UObjects, PascalCase)
- Package management: `uv` (not pip)
- CLI: Click

## Key Constraints

- Domain-agnostic — no assumptions about what the UE project contains
- UE 5.7 only (Python Editor Script Plugin remote execution protocol)
- One parameter at a time in research loop (scientific methodology)
- Pure Python fallback must always work without the UE plugin
- Zero-config capture must work with no setup files
