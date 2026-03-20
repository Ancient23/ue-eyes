---
description: Quick capture from UE viewport or named camera. Zero-config — no setup needed.
---

# UE Eyes: Quick Capture

Capture a screenshot from the running Unreal Engine editor for visual inspection.

## Prerequisites

- UE 5.7 editor running
- Python Editor Script Plugin enabled
- Remote Execution enabled (Editor Preferences → Python → Enable Remote Execution)

## Quick Capture

### 1. Verify UE connection

```bash
cd <project-root> && uv run ue-eyes ping
```

If ping fails: check that UE is running and Remote Execution is enabled. The default multicast address is 239.0.0.1:6766.

### 2. Capture from viewport

```bash
cd <project-root> && uv run ue-eyes snap --output captures/
```

Or capture from a named camera:
```bash
cd <project-root> && uv run ue-eyes snap --output captures/ --camera "MyCameraActor"
```

### 3. View the captured image

Read the PNG files in the `captures/` directory. The `capture_manifest.json` file lists all captured frames.

## Options

- `--camera NAME` — Capture from a named CameraActor instead of the viewport
- `--width W` — Width in pixels (default: 1920)
- `--height H` — Height in pixels (default: 1080)

## Tips

- The capture works from the editor viewport even without PIE running
- For PIE captures, start PIE first, then capture
- Use `ue-eyes cameras` to discover available camera actors in the scene
- Captures are saved as PNG with a timestamped filename
