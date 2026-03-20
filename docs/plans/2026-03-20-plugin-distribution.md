# Plan: Claude Code Plugin Distribution

**Date:** 2026-03-20
**Status:** Planned
**Goal:** Make ue-eyes properly distributable as a Claude Code plugin with clear install paths, correct metadata, and versioning.

---

## Problem

The plugin manifests and skills exist but the distribution story is incomplete:
- `pyproject.toml` is missing standard metadata (author, URLs, keywords)
- No changelog exists
- Version is declared in three places with no enforcement of consistency
- C++ plugin build instructions don't exist
- Two distinct audiences (Claude Code users vs UE developers) aren't clearly addressed

## Solution

Polish metadata, document both distribution paths, establish versioning, and tie it all to the CI/CD pipeline.

---

## Two Distribution Paths

### Path 1: Claude Code Plugin (primary)

**Audience:** AI agent users who want visual access to UE from Claude Code.

**What they get:**
- 3 skills: `/ue-eyes:capture`, `/ue-eyes:setup`, `/ue-eyes:research-loop`
- Python CLI (`ue-eyes` command) for capture, scoring, and experiment orchestration
- Zero-config development mode (just `ue-eyes ping` + `ue-eyes snap`)

**Install methods:**
1. **Marketplace** (when registered): details TBD based on Claude Code marketplace availability
2. **Manual:**
   ```bash
   git clone https://github.com/Ancient23/ue-eyes.git
   cd ue-eyes
   uv sync
   ```

**No C++ compilation required.** Everything works via Python remote execution.

### Path 2: UE C++ Plugin (optional add-on)

**Audience:** UE developers who want persistent camera presets and Blueprint-callable capture.

**What they get:**
- `UEEyesCameraPresetComponent` — Attach to actors for named camera presets
- `AUEEyesCaptureService` — Blueprint-callable capture API
- Tracking modes: Fixed, LookAt, Follow

**Install method:**
- Symlink or copy `plugin/UEEyes/` into project's `Plugins/` directory
- Or use `ue-eyes setup` (see Plugin Setup Installer plan)
- Must compile from source against their UE 5.7 installation

**Pre-built binaries:**
- Win64 binaries are NOT committed to git (gitignored — they are large, platform-specific, and tied to a specific UE `BuildId`)
- Users must build from source against their own UE 5.7 installation
- Pre-built binaries may be attached to GitHub Releases in the future as a convenience

---

## Metadata Fixes

### `pyproject.toml`

Add missing fields:

```toml
[project]
name = "ue-eyes"
version = "0.1.0"
description = "Give AI agents visual access to Unreal Engine 5.7"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
authors = [
    { name = "Ancient23" }
]
keywords = ["unreal-engine", "ai-agent", "visual", "capture", "claude"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Testing",
    "Topic :: Multimedia :: Graphics",
]

[project.urls]
Homepage = "https://github.com/Ancient23/ue-eyes"
Repository = "https://github.com/Ancient23/ue-eyes"
Issues = "https://github.com/Ancient23/ue-eyes/issues"
```

### `.claude-plugin/plugin.json`

Verify fields match `pyproject.toml`:
- `version` must match
- `description` must match
- `repository` URL must match

### `ue_eyes/__init__.py`

Currently declares `__version__` independently. Should be updated to read from `importlib.metadata` so `pyproject.toml` remains the single source of truth:

```python
from importlib.metadata import version
__version__ = version("ue-eyes")
```

---

## Versioning Strategy

### Scheme: Semver

- `0.x.y` — Pre-1.0, breaking changes allowed between minor versions
- `1.0.0` — First stable release (when autonomous loop and init command are solid)
- Patch (`0.1.1`): bug fixes
- Minor (`0.2.0`): new features (init command, autonomous loop, etc.)
- Major (`1.0.0`): stable API commitment

### Version Source of Truth

**Single source:** `pyproject.toml` `version` field.

Three files must stay in sync:
1. `pyproject.toml` → `version = "X.Y.Z"`
2. `ue_eyes/__init__.py` → `__version__ = "X.Y.Z"`
3. `.claude-plugin/plugin.json` → `"version": "X.Y.Z"`

The release process (documented in CI/CD plan) updates all three before tagging.

### Changelog

New file: `CHANGELOG.md` at repo root.

Format: [Keep a Changelog](https://keepachangelog.com/)

```markdown
# Changelog

## [0.2.0] — YYYY-MM-DD
### Added
- `ue-eyes setup` interactive project setup command
- `ue-eyes iterate` for autonomous research loop
- CI/CD with GitHub Actions

## [0.1.0] — 2026-03-19
### Added
- Initial release
- Frame capture (snap + render) via Python remote execution
- Camera discovery and preset management
- SSIM, pixel MSE, and perceptual hash scoring
- Side-by-side comparison and difference heatmap generation
- Qualitative rubric scoring system
- Experiment runner with parameter tuning pipeline
- Results tracking (TSV format)
- Optional UE 5.7 C++ plugin with camera presets
- Three Claude Code skills: capture, setup, research-loop
- CLI with ping, snap, render, cameras, compare, score commands
```

---

## C++ Plugin Build Documentation

A new section added to README.md (or a standalone `docs/building-ue-plugin.md`):

### Prerequisites
- Unreal Engine 5.7 installed
- Visual Studio 2022 or Rider with UE support
- Windows (for Win64 target) — cross-platform builds follow standard UE cross-compilation

### Building from Source

1. Symlink or copy `plugin/UEEyes/` to your project's `Plugins/` directory
2. Right-click `.uproject` → "Generate Visual Studio project files"
3. Open the `.sln` in Visual Studio/Rider
4. Build the `Development Editor` configuration
5. The compiled binaries land in `Plugins/UEEyes/Binaries/Win64/`

### BuildId Compatibility

UE embeds a `BuildId` in `UnrealEditor.modules` that must match your editor's build. Pre-built binaries in this repo were compiled against a specific UE 5.7 installation. If the editor refuses to load the plugin with a "module was not built for this engine version" error, build from source.

### Plugin Dependencies

Minimal — only standard UE modules:
- `Core`
- `CoreUObject`
- `Engine`

No third-party dependencies, no special plugins required.

---

## Files to Create / Modify

| File | Action | Description |
|------|--------|-------------|
| `CHANGELOG.md` | Create | Changelog starting from v0.1.0 |
| `pyproject.toml` | Modify | Add metadata fields (version is source of truth) |
| `ue_eyes/__init__.py` | Modify | Read version from `importlib.metadata` instead of hardcoding |
| `.claude-plugin/plugin.json` | Modify | Verify version consistency |
| `.gitignore` | Modify | Add `plugin/UEEyes/Binaries/` and `plugin/UEEyes/Intermediate/` |
| `README.md` | Modify | Add C++ build instructions section |

---

## Future Considerations

### Fab / UE Marketplace (Not Now)

The current C++ plugin is small and free — camera presets and capture service. A future premium version with advanced features could be distributed through Fab/UE Marketplace as a separate product in a private repository. The free open-source version serves as the foundation and funnel. This separation is intentional: don't over-invest in the free plugin's C++ features.

### What's NOT Included

| Item | Reason |
|------|--------|
| Automated C++ builds in CI | Requires UE engine, not practical in GitHub Actions |
| UE Marketplace submission | Separate ecosystem, future consideration |
| npm/pip auto-publish of skills | Skills are files distributed with the repo |
| Multi-platform C++ binaries | Users build against their own UE installation |
