# UE Eyes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone toolkit giving AI agents visual access to UE 5.7 projects, with zero-config capture and structured research loop modes.

**Architecture:** Python package (`ue_eyes/`) communicating with UE 5.7 via Python Editor Script Plugin remote execution (UDP multicast + TCP). Optional minimal C++ plugin for camera presets. Distributed as a Claude Code plugin.

**Tech Stack:** Python 3.12+, uv, Click, numpy, opencv-python, pytest. UE 5.7 C++ (optional plugin). Claude Code plugin system.

**Spec:** `docs/specs/2026-03-19-ue-eyes-design.md`

**Source reference:** `C:\Source\smplx-metahuman\automocap\` (extract and generalize, remove all domain-specific code)

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `ue_eyes/__init__.py`
- Create: `ue-eyes.example.toml`
- Create: `CLAUDE.md`
- Create: `.gitignore`
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "ue-eyes"
version = "0.1.0"
description = "Give AI agents visual access to Unreal Engine 5.7 projects"
requires-python = ">=3.12"
dependencies = [
    "click>=8.0",
    "opencv-python>=4.8",
    "numpy>=1.26",
]

[project.scripts]
ue-eyes = "ue_eyes.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=9.0",
]
```

- [ ] **Step 2: Create ue_eyes/__init__.py**

```python
"""ue-eyes: Give AI agents visual access to Unreal Engine 5.7 projects."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
experiments/
*.png
capture_manifest.json
tune_params.json
rubric.json
ue-eyes.toml
.superpowers/
```

- [ ] **Step 4: Create ue-eyes.example.toml**

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

Also create `agents/` directory with `.gitkeep` (spec includes this directory; currently deferred but placeholder needed).

- [ ] **Step 5: Create CLAUDE.md**

```markdown
# UE Eyes — Agent Visual Access for Unreal Engine 5.7

## Commands

\`\`\`bash
# Install & test
uv sync
uv run pytest tests/ -v

# CLI
uv run ue-eyes ping
uv run ue-eyes snap --output captures/
uv run ue-eyes cameras
uv run ue-eyes score --reference ref/ --capture cap/
\`\`\`

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

## Testing

Run full suite: `uv run pytest tests/ -v`
Mock UE connection for unit tests. Integration tests require running UE editor.
```

- [ ] **Step 6: Create Claude Code plugin manifest**

`.claude-plugin/plugin.json`:
```json
{
  "name": "ue-eyes",
  "version": "0.1.0",
  "description": "Give AI agents visual access to Unreal Engine 5.7 projects",
  "author": {
    "name": "Ancient23"
  },
  "repository": "https://github.com/Ancient23/ue-eyes",
  "license": "MIT",
  "skills": "./skills/"
}
```

`.claude-plugin/marketplace.json`:
```json
{
  "plugins": [
    {
      "name": "ue-eyes",
      "description": "Give AI agents visual access to Unreal Engine 5.7 projects — capture screenshots, compare frames, tune parameters",
      "path": "."
    }
  ]
}
```

- [ ] **Step 7: Run uv sync and verify**

Run: `cd C:\Source\ue-eyes && uv sync`
Expected: Dependencies installed, `.venv` created.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with pyproject.toml and Claude Code plugin"
```

---

## Task 2: Remote Execution Module

**Files:**
- Create: `ue_eyes/remote_exec.py`
- Create: `tests/test_remote_exec.py`

- [ ] **Step 1: Write failing tests for remote execution**

Create `tests/test_remote_exec.py` with tests for:
- Message encoding/decoding roundtrip
- Message construction (ping, command, open_connection)
- UERemoteExecution constructor stores params correctly
- `execute()` raises `UEConnectionError` when not connected
- `execute_file()` raises `FileNotFoundError` for missing scripts
- `execute_file()` injects `_ue_eyes_params` correctly
- Context manager calls connect/close
- `ping()` returns False when UE not reachable

Use `unittest.mock.patch` to mock socket operations for unit tests that don't need a real UE instance.

Key test structure:
```python
import pytest
from unittest.mock import patch, MagicMock
from ue_eyes.remote_exec import (
    UERemoteExecution, UEConnectionError, UEExecutionError,
    _encode_message, _decode_message, _make_message,
    PROTOCOL_VERSION, PROTOCOL_MAGIC,
)

class TestMessageEncoding:
    def test_roundtrip(self): ...
    def test_make_ping_message(self): ...
    def test_make_command_message(self): ...

class TestUERemoteExecution:
    def test_constructor_defaults(self): ...
    def test_execute_not_connected_raises(self): ...
    def test_execute_file_missing_raises(self): ...
    def test_execute_file_injects_params(self): ...
    def test_context_manager(self): ...
    def test_ping_returns_false_no_ue(self): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_remote_exec.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement remote_exec.py**

Extract from `C:\Source\smplx-metahuman\automocap\ue_eyes\remote_exec.py`. Changes:
- Remove `command_ip`/`command_port` legacy params from `__init__`
- Keep all protocol code, socket handling, message encoding/decoding identical
- Keep `UEConnectionError`, `UEExecutionError` exception classes
- Keep `_encode_message`, `_decode_message`, `_make_message` helpers
- Keep full `connect()`, `close()`, `execute()`, `execute_file()`, `ping()` methods
- Keep all UDP/TCP I/O internals (`_udp_send`, `_wait_for_pong`, `_tcp_send`, `_tcp_recv`)
- Remove any references to automocap or smplx

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_remote_exec.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/remote_exec.py tests/test_remote_exec.py
git commit -m "feat: UE remote execution module (UDP multicast + TCP)"
```

---

## Task 3: Config Module

**Files:**
- Create: `ue_eyes/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config**

Tests for:
- `load_config()` returns defaults when no file exists
- `load_config()` reads and parses a toml file
- `load_config()` walks up to git root to find config
- `load_config()` validates version field
- `UEEyesConfig` dataclass has correct default values
- Camera presets are parsed from `[cameras.*]` sections
- Scoring config parsed correctly
- Parameter file path resolved

```python
class TestUEEyesConfig:
    def test_defaults(self): ...
    def test_from_toml(self, tmp_path): ...
    def test_discovery_walks_up(self, tmp_path): ...
    def test_version_validation(self, tmp_path): ...
    def test_camera_presets_parsed(self, tmp_path): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config.py**

```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
import subprocess

@dataclass
class CameraPreset:
    name: str
    location: list[float] = field(default_factory=lambda: [0, 0, 0])
    rotation: list[float] = field(default_factory=lambda: [0, 0, 0])
    tracking_mode: str = "fixed"  # fixed, look_at, follow
    target_actor: str = ""
    target_bone: str = ""
    offset: list[float] = field(default_factory=lambda: [0, 0, 0])

@dataclass
class UEEyesConfig:
    # Connection
    multicast_group: str = "239.0.0.1"
    multicast_port: int = 6766
    timeout: float = 30.0
    # Capture
    capture_mode: str = "snap"
    default_resolution: list[int] = field(default_factory=lambda: [1920, 1080])
    sequence_path: str = ""
    map_path: str = ""
    # Cameras
    cameras: dict[str, CameraPreset] = field(default_factory=dict)
    # Scoring
    metrics: list[str] = field(default_factory=lambda: ["ssim"])
    composite_weights: dict[str, float] = field(default_factory=lambda: {"ssim": 1.0})
    # Parameters
    params_file: str = "tune_params.json"

def _find_config_file(start: Path) -> Path | None:
    """Walk from start up to git root looking for ue-eyes.toml."""
    current = start.resolve()
    while True:
        candidate = current / "ue-eyes.toml"
        if candidate.is_file():
            return candidate
        if (current / ".git").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None

def load_config(start_dir: Path | None = None) -> UEEyesConfig:
    """Load config from ue-eyes.toml, walking up to git root. Returns defaults if not found."""
    ...  # parse toml, construct UEEyesConfig
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/config.py tests/test_config.py
git commit -m "feat: config module with toml discovery and camera presets"
```

---

## Task 4: Unreal Scripts (UE-side)

**Files:**
- Create: `ue_eyes/unreal_scripts/__init__.py` (empty)
- Create: `ue_eyes/unreal_scripts/capture_frame.py`
- Create: `ue_eyes/unreal_scripts/render_sequence.py`
- Create: `ue_eyes/unreal_scripts/camera_control.py`
- Create: `ue_eyes/unreal_scripts/scene_info.py`

- [ ] **Step 1: Create capture_frame.py**

Extract from `C:\Source\smplx-metahuman\automocap\ue_eyes\unreal_scripts\ue_eyes_capture.py`. Changes:
- Rename file to `capture_frame.py`
- Keep `_get_editor_world()`, `_find_camera_actor()`, `_get_viewport_transform()`, `_capture_frame()` functions
- Keep SceneCapture2D spawn, render target config (PF_B8G8R8A8, gamma 2.2), `capture_scene()`, export via `KismetRenderingLibrary`
- Keep manifest JSON writing and actor cleanup
- Keep `_ue_eyes_params` injection entry point pattern
- No domain-specific code exists in this file — it's a clean copy with rename

- [ ] **Step 2: Create render_sequence.py**

Extract from `C:\Source\smplx-metahuman\automocap\ue_eyes\unreal_scripts\ue_eyes_render_sequence.py`. Changes:
- Rename file to `render_sequence.py`
- Keep full Movie Render Graph pipeline: `MoviePipelineQueueSubsystem`, job allocation, `MoviePipelineOutputSetting` config, `MoviePipelinePIEExecutor`, completion callback, frame filtering
- Keep `_ue_eyes_params` injection entry point
- No domain-specific code exists — clean copy with rename

- [ ] **Step 3: Create camera_control.py**

New file. UE-side script for camera management:
```python
"""UE-side camera control -- runs INSIDE Unreal Engine 5.7.

Injected params via _ue_eyes_params:
    action (str) -- "spawn", "move", "destroy", "apply_tracking"
    name (str) -- camera actor label
    location (list[float], optional) -- [x, y, z]
    rotation (list[float], optional) -- [pitch, yaw, roll]
    tracking_mode (str, optional) -- "fixed", "look_at", "follow"
    target_actor (str, optional) -- actor label to track
    target_bone (str, optional) -- bone name on target
    offset (list[float], optional) -- offset from target
"""
import unreal  # type: ignore

def _find_actor(label):
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    return None

def _spawn_camera(params): ...
def _move_camera(params): ...
def _destroy_camera(params): ...
def _apply_tracking(params): ...
    # look_at: compute rotation from camera pos to target pos
    # follow: compute camera pos = target pos + offset, rotation toward target

# Entry point
_actions = {"spawn": _spawn_camera, "move": _move_camera,
            "destroy": _destroy_camera, "apply_tracking": _apply_tracking}
_actions[_ue_eyes_params["action"]](_ue_eyes_params)
```

- [ ] **Step 4: Create scene_info.py**

New file. UE-side script for scene discovery. Must support all spec-required capabilities:
- Discover all CameraActors (names + transforms)
- Find actors by class or tag
- List skeletal mesh bone names for a given actor
- Read actor property values (for target tracking queries)
- Get actor/bone world transform (needed by camera tracking at capture time)

```python
"""UE-side scene info -- runs INSIDE Unreal Engine 5.7.

Injected params via _ue_eyes_params:
    action (str) -- "discover_cameras", "find_actors", "get_bones",
                    "get_actor_transform", "get_bone_transform", "get_property"
    class_name (str, optional) -- for find_actors
    tag (str, optional) -- for find_actors
    actor_name (str, optional) -- for get_bones, get_actor_transform, get_property
    bone_name (str, optional) -- for get_bone_transform
    property_name (str, optional) -- for get_property
"""
import json
import unreal  # type: ignore

def _find_actor(label):
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == label:
            return actor
    return None

def _discover_cameras(params):
    cameras = []
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.CameraActor):
            loc = actor.get_actor_location()
            rot = actor.get_actor_rotation()
            cameras.append({
                "name": actor.get_actor_label(),
                "location": [loc.x, loc.y, loc.z],
                "rotation": [rot.pitch, rot.yaw, rot.roll],
            })
    unreal.log(json.dumps({"cameras": cameras}))

def _find_actors(params):
    """Find actors by class name or tag."""
    results = []
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        class_match = not params.get("class_name") or actor.get_class().get_name() == params["class_name"]
        tag_match = not params.get("tag") or params["tag"] in [str(t) for t in actor.tags]
        if class_match and tag_match:
            loc = actor.get_actor_location()
            results.append({"name": actor.get_actor_label(), "class": actor.get_class().get_name(),
                           "location": [loc.x, loc.y, loc.z]})
    unreal.log(json.dumps({"actors": results}))

def _get_bones(params):
    """List bone names for a skeletal mesh actor."""
    actor = _find_actor(params["actor_name"])
    if not actor: return unreal.log(json.dumps({"bones": [], "error": "actor not found"}))
    skel_comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if not skel_comp: return unreal.log(json.dumps({"bones": [], "error": "no skeletal mesh"}))
    bone_names = [str(skel_comp.get_bone_name(i)) for i in range(skel_comp.get_num_bones())]
    unreal.log(json.dumps({"bones": bone_names}))

def _get_actor_transform(params):
    """Get world transform of an actor."""
    actor = _find_actor(params["actor_name"])
    if not actor: return unreal.log(json.dumps({"error": "actor not found"}))
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    unreal.log(json.dumps({"location": [loc.x, loc.y, loc.z],
                           "rotation": [rot.pitch, rot.yaw, rot.roll]}))

def _get_bone_transform(params):
    """Get world transform of a bone on a skeletal mesh actor."""
    actor = _find_actor(params["actor_name"])
    if not actor: return unreal.log(json.dumps({"error": "actor not found"}))
    skel_comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if not skel_comp: return unreal.log(json.dumps({"error": "no skeletal mesh"}))
    bone_name = unreal.Name(params["bone_name"])
    transform = skel_comp.get_bone_transform(bone_name, unreal.BoneSpaceOption.WORLD_SPACE)
    loc = transform.translation
    rot = transform.rotation.rotator()
    unreal.log(json.dumps({"location": [loc.x, loc.y, loc.z],
                           "rotation": [rot.pitch, rot.yaw, rot.roll]}))

def _get_property(params):
    """Read a property value from an actor."""
    actor = _find_actor(params["actor_name"])
    if not actor: return unreal.log(json.dumps({"error": "actor not found"}))
    prop_name = params["property_name"]
    try:
        value = getattr(actor, prop_name, None)
        if value is None:
            value = actor.get_editor_property(prop_name)
        unreal.log(json.dumps({"property": prop_name, "value": str(value)}))
    except Exception as e:
        unreal.log(json.dumps({"property": prop_name, "error": str(e)}))

_actions = {
    "discover_cameras": _discover_cameras, "find_actors": _find_actors,
    "get_bones": _get_bones, "get_actor_transform": _get_actor_transform,
    "get_bone_transform": _get_bone_transform, "get_property": _get_property,
}
_actions[_ue_eyes_params["action"]](_ue_eyes_params)
```

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/unreal_scripts/
git commit -m "feat: UE-side scripts for capture, render, camera control, scene discovery"
```

---

## Task 5: Capture Module

**Files:**
- Create: `ue_eyes/capture.py`
- Create: `tests/test_capture.py`

- [ ] **Step 1: Write failing tests for capture**

Tests for:
- `snap_frame()` calls `execute_file` with correct script and params
- `snap_frame()` creates output directory
- `snap_frame()` returns manifest dict with required keys
- `snap_frame()` without plugin uses transient SceneCapture2D script
- `snap_frame()` with plugin detected delegates to CaptureService
- `_detect_plugin(ue)` returns True/False based on UE query
- `render_sequence()` calls `execute_file` with correct params
- `render_sequence()` passes frame_step and resolution
- Manifest includes timestamp, type, camera, frame_count
- Mock `UERemoteExecution` to avoid needing a real UE instance

```python
class TestSnapFrame:
    def test_calls_execute_file(self, tmp_path): ...
    def test_creates_output_dir(self, tmp_path): ...
    def test_manifest_keys(self, tmp_path): ...
    def test_no_plugin_uses_transient_capture(self, tmp_path): ...
    def test_plugin_detected_delegates_to_service(self, tmp_path): ...

class TestPluginDetection:
    def test_returns_false_when_no_service(self): ...
    def test_returns_true_when_service_found(self): ...

class TestRenderSequence:
    def test_calls_execute_file(self, tmp_path): ...
    def test_passes_frame_params(self, tmp_path): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_capture.py -v`
Expected: FAIL

- [ ] **Step 3: Implement capture.py**

Extract from `C:\Source\smplx-metahuman\automocap\ue_eyes\capture.py`. Changes:
- Update script paths to point to new `unreal_scripts/capture_frame.py` and `render_sequence.py`
- Remove `ue_host`/`ue_port` params — use config or default multicast
- Accept optional `UERemoteExecution` instance or create one from config
- Keep `_write_manifest()` helper
- Keep `snap_frame()` and `render_sequence()` signatures per spec
- Add `_detect_plugin(ue)` function that queries UE for `UEEyesCaptureService` actors; returns bool
- In `snap_frame()`: if plugin detected, execute UE command to call `CaptureService.CaptureFromPreset(camera)` or `CaptureFromViewport()`. If not detected, use transient SceneCapture2D via `capture_frame.py` script (existing behavior)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_capture.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/capture.py tests/test_capture.py
git commit -m "feat: capture module with snap_frame and render_sequence"
```

---

## Task 6: Cameras Module

**Files:**
- Create: `ue_eyes/cameras.py`
- Create: `tests/test_cameras.py`

- [ ] **Step 1: Write failing tests for cameras**

Tests for:
- `CameraInfo` dataclass construction
- `discover_cameras()` parses UE response JSON
- `apply_preset()` with fixed tracking (spawns camera at position)
- `apply_preset()` with look_at tracking (queries target transform from UE, computes rotation)
- `apply_preset()` with follow tracking (queries target transform from UE, computes position)
- `spawn_camera()` calls camera_control script with spawn action
- `move_camera()` calls camera_control script with move action
- `destroy_camera()` calls camera_control script with destroy action
- Tracking math: look_at rotation computation from two 3D points
- Tracking math: follow position computation with offset

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_cameras.py -v`
Expected: FAIL

- [ ] **Step 3: Implement cameras.py**

New module (no direct source to extract from — the existing code only has basic camera selection in capture.py). Implement:
- `CameraInfo` dataclass (name, location, rotation)
- `discover_cameras(ue)` — executes `scene_info.py` with `action="discover_cameras"`, parses JSON response
- `_query_target_transform(ue, target_actor, target_bone=None)` — executes `scene_info.py` with `action="get_actor_transform"` or `"get_bone_transform"` to get live target position. Required before applying look_at or follow tracking.
- `apply_preset(preset_name, config, ue)` — loads preset from config, queries live target transform via `_query_target_transform()`, computes tracking rotation/position, spawns/moves camera
- `spawn_camera(ue, location, rotation, name)` — executes `camera_control.py` with spawn action
- `move_camera(ue, name, location, rotation)` — executes with move action
- `destroy_camera(ue, name)` — executes with destroy action
- `_compute_look_at_rotation(camera_pos, target_pos)` — returns [pitch, yaw, roll]
- `_compute_follow_position(target_pos, offset)` — returns [x, y, z]

Tracking implementation:
```python
def _compute_look_at_rotation(camera_pos: list[float], target_pos: list[float]) -> list[float]:
    """Compute pitch/yaw/roll to look from camera_pos toward target_pos."""
    dx = target_pos[0] - camera_pos[0]
    dy = target_pos[1] - camera_pos[1]
    dz = target_pos[2] - camera_pos[2]
    dist_xy = np.sqrt(dx * dx + dy * dy)
    pitch = np.degrees(np.arctan2(dz, dist_xy))
    yaw = np.degrees(np.arctan2(dy, dx))
    return [pitch, yaw, 0.0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_cameras.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/cameras.py tests/test_cameras.py
git commit -m "feat: cameras module with discovery, presets, tracking, ad-hoc spawn"
```

---

## Task 7: Scoring — Metrics

**Files:**
- Create: `ue_eyes/scoring/__init__.py` (re-export: `ssim_score`, `pixel_mse_score`, `phash_score`, `compute_scores`, `load_scorer`, `match_frames`)
- Create: `ue_eyes/scoring/metrics.py`
- Create: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests for scoring metrics**

Tests for:
- `ssim_score(ref, capture)` returns 1.0 for identical images
- `ssim_score(ref, capture)` returns < 1.0 for different images
- `ssim_score()` handles different image sizes
- `pixel_mse_score(ref, capture)` returns 1.0 for identical images
- `pixel_mse_score(ref, capture)` returns 0.0 for maximally different images
- `phash_score(ref, capture)` returns 1.0 for identical images
- `load_scorer("ssim")` returns the ssim_score function
- `load_scorer("my_module:my_func")` imports custom scorer
- `compute_scores(ref, capture, metrics, weights)` returns composite + per-metric dict
- `match_frames(dir_a, dir_b)` pairs files by extracted frame number
- `match_frames()` handles varied naming (frame_0001.png, 001.png, etc.)
- `match_frames()` returns empty list for non-matching directories

Use `tmp_path` with synthetic test images (numpy arrays saved as PNG via cv2.imwrite).

```python
class TestMatchFrames:
    def test_pairs_by_number(self, tmp_path): ...
    def test_varied_naming(self, tmp_path): ...
    def test_no_matches_returns_empty(self, tmp_path): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v`
Expected: FAIL

- [ ] **Step 3: Implement scoring/metrics.py**

Extract SSIM from `C:\Source\smplx-metahuman\automocap\metrics.py`. Add new metrics:

```python
"""Built-in scoring metrics and pluggable scorer loading."""
from __future__ import annotations
import importlib
import re
from pathlib import Path
import cv2
import numpy as np

# --- SSIM (extracted from automocap/metrics.py, using Gaussian window) ---
def ssim_score(reference: Path, capture: Path) -> float: ...

# --- Pixel MSE (new) ---
def pixel_mse_score(reference: Path, capture: Path) -> float:
    """1.0 - normalized MSE. Returns 1.0 for identical, 0.0 for max difference."""
    ...

# --- Perceptual Hash (new) ---
def phash_score(reference: Path, capture: Path) -> float:
    """1.0 - normalized hamming distance of perceptual hashes."""
    ...

# --- Scorer registry ---
BUILTIN_SCORERS = {"ssim": ssim_score, "pixel_mse": pixel_mse_score, "phash": phash_score}

def load_scorer(name: str) -> callable:
    """Load a scorer by name. Built-in names or 'module:function' for custom."""
    if name in BUILTIN_SCORERS:
        return BUILTIN_SCORERS[name]
    module_path, func_name = name.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)

def compute_scores(reference: Path, capture: Path, metrics: list[str],
                   weights: dict[str, float]) -> dict:
    """Compute all metrics and weighted composite."""
    scores = {}
    for name in metrics:
        scorer = load_scorer(name)
        scores[name] = scorer(reference, capture)
    total_weight = sum(weights.get(m, 1.0) for m in metrics)
    composite = sum(scores[m] * weights.get(m, 1.0) for m in metrics) / total_weight
    return {"scores": scores, "composite": composite}

# --- Frame matching (extracted from automocap/metrics.py) ---
def match_frames(dir_a: str, dir_b: str) -> list[tuple[str, str]]: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/scoring/ tests/test_scoring.py
git commit -m "feat: scoring metrics (SSIM, pixel MSE, perceptual hash, pluggable custom)"
```

---

## Task 8: Scoring — Comparison Visualization

**Files:**
- Create: `ue_eyes/scoring/compare.py`
- Add tests to: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests for comparison**

Note: The spec lists `create_comparison(ref, capture)` with 2 args, but the implementation needs an `output_path` parameter (3rd arg) to write the result. This is a necessary addition — the spec describes the conceptual interface, not the exact signature.

Tests for:
- `create_comparison(ref, capture, output)` creates a PNG file
- `create_comparison()` output image is wider than either input (side-by-side)
- `create_difference_map(ref, capture, output)` creates a PNG file
- `create_comparison_grid(ref_dir, render_dir, output, max=12)` creates a grid image
- `create_comparison_grid()` respects max_frames limit

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v -k compare`
Expected: FAIL

- [ ] **Step 3: Implement compare.py**

Extract from `C:\Source\smplx-metahuman\automocap\compare_frames.py`. Changes:
- Replace `from automocap.metrics import match_frames` with `from ue_eyes.scoring.metrics import match_frames`
- Keep `create_comparison()`, `create_difference_map()`, `create_comparison_grid()` and `_resize_to_height()` helper
- No other changes needed — this code has no domain coupling

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/scoring/compare.py tests/test_scoring.py
git commit -m "feat: comparison visualization (side-by-side, diff heatmap, grid)"
```

---

## Task 9: Scoring — Rubric System

**Files:**
- Create: `ue_eyes/scoring/rubric.py`
- Add tests to: `tests/test_scoring.py`

- [ ] **Step 1: Write failing tests for rubric**

Tests for:
- `RubricResult` dataclass construction and composite calculation
- `format_rubric_prompt()` includes all criteria names and descriptions
- `format_rubric_prompt()` includes image paths
- `parse_rubric_scores()` parses well-formed agent response
- `parse_rubric_scores()` handles missing criteria gracefully
- `load_rubric(path)` reads rubric JSON
- `save_rubric(rubric, path)` writes rubric JSON

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v -k rubric`
Expected: FAIL

- [ ] **Step 3: Implement rubric.py**

New module (no source to extract from):

```python
"""Agent-generated qualitative scoring rubric system."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class RubricResult:
    per_criterion: dict[str, float]   # criterion name -> score (0-10)
    composite: float                   # weighted composite
    reasoning: dict[str, str]         # criterion name -> agent's reasoning

def load_rubric(path: Path) -> dict:
    """Load rubric definition from JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))

def save_rubric(rubric: dict, path: Path) -> None:
    """Save rubric definition to JSON file."""
    Path(path).write_text(json.dumps(rubric, indent=2), encoding="utf-8")

def format_rubric_prompt(
    rubric: dict,
    capture_paths: list[Path],
    reference_paths: list[Path] | None = None,
) -> str:
    """Build a structured prompt for the agent to score each criterion."""
    lines = [f"## Scoring Rubric: {rubric['name']}", "",
             f"Score each criterion on a {rubric['scale']} scale.", ""]
    for c in rubric["criteria"]:
        lines.append(f"### {c['name']} (weight: {c['weight']})")
        lines.append(c["description"])
        lines.append("")
    lines.append("## Images to evaluate")
    for p in capture_paths:
        lines.append(f"- Capture: {p}")
    if reference_paths:
        for p in reference_paths:
            lines.append(f"- Reference: {p}")
    lines.append("")
    lines.append("For each criterion, respond with:")
    lines.append("criterion_name: <score> — <reasoning>")
    return "\n".join(lines)

def parse_rubric_scores(agent_response: str, rubric: dict) -> RubricResult:
    """Parse agent scoring response into structured RubricResult."""
    criteria_names = {c["name"] for c in rubric["criteria"]}
    weights = {c["name"]: c["weight"] for c in rubric["criteria"]}
    per_criterion = {}
    reasoning = {}
    for line in agent_response.strip().splitlines():
        for name in criteria_names:
            if line.lower().startswith(name.lower()):
                match = re.search(r"(\d+(?:\.\d+)?)", line.split(":", 1)[-1])
                if match:
                    per_criterion[name] = float(match.group(1))
                    parts = line.split("—", 1)
                    reasoning[name] = parts[1].strip() if len(parts) > 1 else ""
    # Compute weighted composite
    total_weight = sum(weights.get(n, 1.0) for n in per_criterion)
    composite = sum(per_criterion[n] * weights.get(n, 1.0) for n in per_criterion)
    composite = composite / total_weight if total_weight > 0 else 0.0
    return RubricResult(per_criterion=per_criterion, composite=composite, reasoning=reasoning)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_scoring.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/scoring/rubric.py tests/test_scoring.py
git commit -m "feat: agent rubric system for qualitative scoring"
```

---

## Task 10: Experiment — Parameters

**Files:**
- Create: `ue_eyes/experiment/__init__.py` (re-export: `ExperimentRunner`, `ExperimentResult`, `load_params`, `save_params`, `diff_params`)
- Create: `ue_eyes/experiment/params.py`
- Create: `tests/test_experiment.py`

- [ ] **Step 1: Write failing tests for params**

Tests for:
- `load_params(path)` reads JSON, validates version
- `save_params(params, path)` writes JSON
- `diff_params(before, after)` returns dict of changed parameters
- `validate_param_change(params, name, value)` checks type and range
- `validate_param_change()` rejects out-of-range float
- `validate_param_change()` rejects invalid enum option

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v -k params`
Expected: FAIL

- [ ] **Step 3: Implement params.py**

```python
"""Parameter space definition, loading, diffing, and validation."""
from __future__ import annotations
import json
from pathlib import Path

def load_params(path: Path) -> dict:
    """Load parameter file. Validates version field."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "version" not in data:
        raise ValueError("Parameter file missing 'version' field")
    return data

def save_params(params: dict, path: Path) -> None:
    """Save parameter file."""
    Path(path).write_text(json.dumps(params, indent=2), encoding="utf-8")

def diff_params(before: dict, after: dict) -> dict:
    """Return dict of {param_name: {"old": old_val, "new": new_val}} for changed params."""
    ...

def validate_param_change(params: dict, name: str, value) -> None:
    """Validate that setting name=value is valid per the param definition.
    Raises ValueError if type mismatch, out of range, or invalid enum."""
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/ tests/test_experiment.py
git commit -m "feat: parameter space loading, diffing, and validation"
```

---

## Task 11: Experiment — Results Tracking

**Files:**
- Create: `ue_eyes/experiment/results.py`
- Add tests to: `tests/test_experiment.py`

- [ ] **Step 1: Write failing tests for results tracking**

Tests for:
- `init_results(path)` creates TSV with header
- `init_results()` is idempotent (doesn't overwrite existing)
- `log_result(path, result)` appends row
- `load_results(path)` reads all rows as dicts
- `load_results()` converts numeric fields
- `get_best_score(path)` returns highest composite
- `get_score_trend(path, n)` returns last n scores
- TSV `metric_scores_json` column stores JSON-encoded dict

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v -k results`
Expected: FAIL

- [ ] **Step 3: Implement results.py**

Extract from `C:\Source\smplx-metahuman\automocap\results_logger.py`. Changes:
- Update `RESULTS_HEADER` to match spec: `experiment | timestamp | parameter | old_value | new_value | hypothesis | composite_score | metric_scores_json | verdict | notes`
- `log_result()` accepts `ExperimentResult` dataclass or dict
- `metric_scores_json` column stores `json.dumps(scores_dict)`
- Keep `init_results()`, `load_results()`, `get_best_score()`, `get_score_trend()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/results.py tests/test_experiment.py
git commit -m "feat: TSV experiment results tracking"
```

---

## Task 12: Experiment — Runner

**Files:**
- Create: `ue_eyes/experiment/runner.py`
- Add tests to: `tests/test_experiment.py`

- [ ] **Step 1: Write failing tests for experiment runner**

Tests for:
- `ExperimentResult` dataclass construction
- `ExperimentRunner.__init__` stores config
- `set_baseline()` stores reference directory
- `run_experiment()` in agent mode (apply_fn=None) skips apply step
- `run_experiment()` in script mode calls apply_fn with no args
- `run_experiment()` in hybrid mode calls apply_fn(params)
- `run_experiment()` captures from configured cameras (mocked)
- `run_experiment()` computes scores (mocked)
- `run_experiment()` returns ExperimentResult with all fields populated
- `run_experiment()` handles capture failure: verdict="failed", error field populated, no retry

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v -k runner`
Expected: FAIL

- [ ] **Step 3: Implement runner.py**

```python
"""Generic experiment runner for the research loop."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from ue_eyes.config import UEEyesConfig
from ue_eyes.scoring.rubric import RubricResult

@dataclass
class ExperimentResult:
    experiment_id: str
    timestamp: str
    params_before: dict | None
    params_after: dict | None
    parameter_changed: str | None
    hypothesis: str
    scores: dict[str, float]
    composite_score: float
    rubric_result: RubricResult | None
    verdict: str  # "baseline", "keep", "discard", "failed"
    error: str | None
    notes: str
    capture_dir: Path
    comparison_dir: Path

class ExperimentRunner:
    def __init__(self, config: UEEyesConfig) -> None: ...
    def set_baseline(self, reference_dir: Path) -> None: ...
    def run_experiment(self,
        experiment_id: str,
        apply_fn: Callable | None = None,
        params: dict | None = None,
        hypothesis: str = "",
        parameter_changed: str | None = None,
    ) -> ExperimentResult: ...
```

Note: The `run_experiment()` signature extends the spec by adding `hypothesis` and `parameter_changed` args — these are needed to populate `ExperimentResult` fields. The spec signature has 3 params; we add 2 for completeness.

The `run_experiment()` method implements the full 6-step loop:
1. APPLY — call apply_fn if provided (per mode table in spec)
2. CAPTURE — call snap_frame/render_sequence from configured cameras
3. COMPARE — generate comparison images against baseline
4. SCORE — compute quantitative metrics + composite
5. DECIDE — compare composite_score against baseline best score. If improved or equal, verdict="keep". If worse, verdict="discard". First experiment gets verdict="baseline".
6. LOG — call `log_result()` from `results.py` to append to TSV, write `result.json` to experiment dir

On capture failure: set verdict="failed", populate `error` field, skip COMPARE/SCORE/DECIDE, still LOG.

Creates per-experiment directory structure: `experiments/{id}/captures/`, `experiments/{id}/comparisons/`, `experiments/{id}/result.json`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_experiment.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/experiment/runner.py tests/test_experiment.py
git commit -m "feat: experiment runner with apply/capture/compare/score pipeline"
```

---

## Task 13: CLI

**Files:**
- Create: `ue_eyes/cli.py`

- [ ] **Step 1: Write failing tests for CLI**

Add `tests/test_cli.py`:
- Test `ping` command output format
- Test `snap` requires --output
- Test `render` requires --output, --sequence, --map
- Test `cameras` command exists
- Test `compare` requires --reference, --capture, --output
- Test `score` requires --reference, --capture
- Use Click's `CliRunner` for testing

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement cli.py**

Extract from `C:\Source\smplx-metahuman\automocap\ue_eyes\cli.py`. Changes:
- Remove `--host`/`--port` from snap/render (use config-based multicast defaults)
- Add `--host`/`--port` to `ping` command only (for quick connectivity check)
- Replace `analyze` command with `cameras`, `compare`, `score` commands per spec
- Remove `--analyze` flag from snap/render
- Use `load_config()` for defaults where appropriate

Add `@click.version_option(version=__version__, prog_name="ue-eyes")` to main group.

Commands per spec:
```
ue-eyes --version
ue-eyes ping [--host HOST] [--port PORT]
ue-eyes snap --output DIR [--camera NAME] [--width W] [--height H]
ue-eyes render --output DIR --sequence PATH --map PATH [--frames] [--range] [--step] [--width] [--height]
ue-eyes cameras
ue-eyes compare --reference DIR --capture DIR --output DIR
ue-eyes score --reference DIR --capture DIR [--metrics ssim,pixel_mse]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 5: Verify CLI entry point works**

Run: `cd C:\Source\ue-eyes && uv run ue-eyes --version`
Expected: `ue-eyes, version 0.1.0`

- [ ] **Step 6: Commit**

```bash
git add ue_eyes/cli.py tests/test_cli.py
git commit -m "feat: Click CLI with ping, snap, render, cameras, compare, score commands"
```

---

## Task 14: UE C++ Plugin (Optional)

**Files:**
- Create: `plugin/UEEyes/UEEyes.uplugin`
- Create: `plugin/UEEyes/Source/UEEyes/UEEyes.Build.cs`
- Create: `plugin/UEEyes/Source/UEEyes/Private/UEEyesModule.cpp`
- Create: `plugin/UEEyes/Source/UEEyes/Public/UEEyesCameraPresetComponent.h`
- Create: `plugin/UEEyes/Source/UEEyes/Private/UEEyesCameraPresetComponent.cpp`
- Create: `plugin/UEEyes/Source/UEEyes/Public/UEEyesCaptureService.h`
- Create: `plugin/UEEyes/Source/UEEyes/Private/UEEyesCaptureService.cpp`

- [ ] **Step 1: Create .uplugin manifest**

```json
{
  "FileVersion": 3,
  "Version": 1,
  "VersionName": "0.1.0",
  "FriendlyName": "UE Eyes",
  "Description": "Minimal capture service and camera preset components for UE Eyes agent toolkit",
  "Category": "AI",
  "CreatedBy": "Ancient23",
  "Installed": true,
  "Modules": [
    {
      "Name": "UEEyes",
      "Type": "Runtime",
      "LoadingPhase": "Default"
    }
  ]
}
```

- [ ] **Step 2: Create Build.cs**

```csharp
using UnrealBuildTool;

public class UEEyes : ModuleRules
{
    public UEEyes(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[] {
            "Core",
            "CoreUObject",
            "Engine",
        });
    }
}
```

- [ ] **Step 3: Create module boilerplate**

`UEEyesModule.cpp`:
```cpp
#include "Modules/ModuleManager.h"

class FUEEyesModule : public IModuleInterface
{
public:
    virtual void StartupModule() override {}
    virtual void ShutdownModule() override {}
};

IMPLEMENT_MODULE(FUEEyesModule, UEEyes)
```

- [ ] **Step 4: Create UEEyesCameraPresetComponent**

Header with UPROPERTY fields per spec:
- PresetName (FString)
- Resolution (FIntPoint)
- TrackingMode (EUEEyesTrackingMode enum: Fixed, LookAt, Follow)
- TargetActor (TSoftObjectPtr<AActor>)
- TargetBone (FName)
- Offset (FVector)
- Notes (FString)

Implementation: minimal — just a data component, no tick logic.

- [ ] **Step 5: Create UEEyesCaptureService**

Actor with:
- `CaptureFromPreset(FString PresetName)` — finds preset component, spawns/configures SceneCapture2D
- `CaptureFromViewport()` — captures from current viewport
- Private `USceneCaptureComponent2D*` managed lifecycle

- [ ] **Step 6: Verify compiles against UE 5.7 headers**

Check includes against `C:\Source\UnrealEngine\Engine\Source\Runtime\Engine\Classes\Components\SceneCaptureComponent2D.h` for correct API.

- [ ] **Step 7: Commit**

```bash
git add plugin/
git commit -m "feat: optional UE 5.7 plugin with camera presets and capture service"
```

---

## Task 15: Claude Code Skills

**Files:**
- Create: `skills/capture/SKILL.md`
- Create: `skills/ue-eyes-setup/SKILL.md`
- Create: `skills/research-loop/SKILL.md`

- [ ] **Step 1: Create /ue-eyes:capture skill**

```markdown
---
description: Quick capture from UE viewport or named camera. Zero-config.
---

# UE Eyes: Quick Capture

Capture a screenshot from Unreal Engine for visual inspection.

## Steps

1. Check if UE is reachable:
\`\`\`bash
cd <ue-eyes-repo> && uv run ue-eyes ping
\`\`\`

2. Capture from viewport (or specify --camera):
\`\`\`bash
cd <ue-eyes-repo> && uv run ue-eyes snap --output <output-dir>
\`\`\`

3. Read and display the captured PNG files.

## Notes
- UE must be running with Python Editor Script Plugin + Remote Execution enabled
- Uses UDP multicast discovery (239.0.0.1:6766) — no manual host/port needed
- For named cameras: `--camera "MyCameraActor"`
```

- [ ] **Step 2: Create /ue-eyes:setup skill**

```markdown
---
description: Interactive setup wizard for UE Eyes. Configures cameras, baselines, parameters, and scoring.
---

# UE Eyes: Setup Wizard

Walk the user through setting up UE Eyes for their project.

## Prerequisites
- UE 5.7 editor running with Python Editor Script Plugin + Remote Execution enabled

## Steps

### 1. Verify Connection
```bash
cd <ue-eyes-repo> && uv run ue-eyes ping
```
If ping fails, guide user to enable Remote Execution in UE editor preferences.

### 2. Discover Scene
```bash
cd <ue-eyes-repo> && uv run ue-eyes cameras
```
Show the user what cameras exist in their scene. Ask if they want to use existing cameras or define new presets.

### 3. Define Goal
Ask the user: "What do you want to accomplish?"
- **Visual bug fix** → Development mode (no further setup needed)
- **Match a reference** → Research loop (continue setup)
- **Tune parameters** → Research loop (continue setup)

### 4. Camera Presets (if research loop)
For each camera the user wants:
- Name, position, tracking mode (fixed/look_at/follow)
- Target actor and bone (if tracking)
Write entries to `ue-eyes.toml` under `[cameras.<name>]`.

### 5. Capture Baseline
```bash
cd <ue-eyes-repo> && uv run ue-eyes snap --output baseline/
```
Capture from all configured cameras. These become the reference frames.

### 6. Define Parameters (if research loop)
Ask the user what they want to tune. For each parameter:
- Name, type (float/bool/enum), current value, min/max/options
Write to `tune_params.json`.

### 7. Generate Scoring Rubric (if research loop)
Collaborate with user to define qualitative criteria:
- What does "good" look like? What are you optimizing for?
- Define 3-5 criteria with weights and descriptions
Write to `rubric.json`.

### 8. Write Config
Write `ue-eyes.toml` with all settings. Confirm with user.

## Output Files
- `ue-eyes.toml` — Project config
- `tune_params.json` — Parameter definitions (research loop only)
- `rubric.json` — Scoring rubric (research loop only)
- `baseline/` — Reference captures
```

- [ ] **Step 3: Create /ue-eyes:research-loop skill**

```markdown
---
description: Start a structured experiment loop. Requires prior /ue-eyes:setup.
---

# UE Eyes: Research Loop

Run a structured parameter tuning loop with scientific methodology.

## Prerequisites
- `/ue-eyes:setup` completed (ue-eyes.toml, tune_params.json, rubric.json, baseline/ exist)
- UE editor running with Remote Execution enabled

## Before Starting
1. Read `ue-eyes.toml` for camera and scoring config
2. Read `tune_params.json` for current parameter values
3. Read `rubric.json` for qualitative scoring criteria
4. Check `experiments/` for prior results (load `results.tsv` if exists)

## The Loop (runs indefinitely)

### 1. Analyze
- Read results.tsv trajectory (scores over time)
- Look at latest comparison images in `experiments/<latest>/comparisons/`
- Identify the biggest visual discrepancy from the baseline

### 2. Hypothesize
- Pick ONE parameter to change
- Predict the outcome: "Changing X from A to B should improve Y because Z"
- Document the hypothesis

### 3. Edit Parameters
- Modify `tune_params.json` — change EXACTLY ONE parameter
- Commit: `git add tune_params.json && git commit -m "experiment: <description>"`

### 4. Run Experiment
- Apply the parameter change (execute apply script if configured, or agent applies directly)
- Capture from all configured cameras
- Generate comparison images against baseline
- Compute quantitative scores (SSIM, etc.)
- Self-score using the qualitative rubric

### 5. Evaluate
- Review composite score vs previous best
- Visually inspect comparison images
- Apply rubric scoring protocol

### 6. Keep or Discard
- **KEEP**: composite_score > previous best → log verdict="keep"
- **DISCARD**: composite_score <= previous best → log verdict="discard", `git reset --hard HEAD~1`
- **FAILED**: error during capture/scoring → log verdict="failed", `git reset --hard HEAD~1`

### 7. Loop
Go back to Step 1. NEVER STOP until manually interrupted.

## Rules
- ONE parameter at a time (non-negotiable)
- Always commit before each experiment
- Always log to results.tsv
- Metrics can be misleading — always do visual inspection
- Small increments (10-20% changes)
```

- [ ] **Step 4: Commit**

```bash
git add skills/
git commit -m "feat: Claude Code skills for capture, setup wizard, and research loop"
```

---

## Task 16: Integration Test & Final Verification

- [ ] **Step 1: Run full test suite**

Run: `cd C:\Source\ue-eyes && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify CLI works end-to-end**

Run: `cd C:\Source\ue-eyes && uv run ue-eyes --help`
Expected: Shows all commands (ping, snap, render, cameras, compare, score)

- [ ] **Step 3: Verify plugin manifest is valid**

Check `.claude-plugin/plugin.json` is valid JSON and references correct skill paths.

- [ ] **Step 4: Verify no domain-specific references**

Search entire codebase for smplx, metahuman, mocap, skeletal, animation:
```bash
cd C:\Source\ue-eyes && grep -ri "smplx\|metahuman\|mocap\|skeletal" --include="*.py" --include="*.md" --include="*.toml" --include="*.json" .
```
Expected: No matches

- [ ] **Step 5: Final commit with README**

Create a minimal `README.md` with install instructions and quick start.

```bash
git add -A
git commit -m "docs: README with install and quick start"
```

- [ ] **Step 6: Create GitHub repo and push**

```bash
cd C:\Source\ue-eyes
gh repo create Ancient23/ue-eyes --public --source=. --push
```
