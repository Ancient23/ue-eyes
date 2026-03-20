# Plugin Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the distribution story: proper metadata, version source-of-truth, .gitignore for binaries, and C++ build docs.

**Architecture:** Single source of truth for version in `pyproject.toml`. `__init__.py` reads it via `importlib.metadata`. `.gitignore` excludes C++ binaries. README gets a build-from-source section.

**Tech Stack:** Python importlib.metadata, pyproject.toml, git

**Spec:** `docs/plans/2026-03-20-plugin-distribution.md`

**Execution order:** Implement after Plan 1 (CI/CD) — Task 2 Step 3 references `scripts/check_version.py` from Plan 1.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Add metadata fields (source of truth for version) |
| `ue_eyes/__init__.py` | Read version from importlib.metadata |
| `.gitignore` | Add C++ binary exclusions |
| `README.md` | Add C++ build instructions section |

---

### Task 1: Update pyproject.toml Metadata

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add metadata fields**

**IMPORTANT:** Merge these fields into the *existing* `[project]` section. Preserve the existing `[build-system]`, `[project.scripts]`, `[tool.pytest.ini_options]`, and `[dependency-groups]` sections — do NOT overwrite them. Add only the missing fields:

```toml
# Add these fields to the existing [project] section:
readme = "README.md"
license = {text = "MIT"}
authors = [
    {name = "Ancient23"},
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

# Add this new section after [project.scripts]:
[project.urls]
Homepage = "https://github.com/Ancient23/ue-eyes"
Repository = "https://github.com/Ancient23/ue-eyes"
Issues = "https://github.com/Ancient23/ue-eyes/issues"
```

Keep the existing `description = "Give AI agents visual access to Unreal Engine 5.7 projects"` — do not change it.

- [ ] **Step 2: Run tests to verify nothing broke**

Run: `uv sync && uv run pytest tests/ -v`
Expected: 204 passed

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add package metadata to pyproject.toml"
```

---

### Task 2: Version Source of Truth

**Files:**
- Modify: `ue_eyes/__init__.py`

- [ ] **Step 1: Update __init__.py to read version from metadata**

Replace the contents of `ue_eyes/__init__.py` with:

```python
"""ue-eyes: Give AI agents visual access to Unreal Engine 5.7 projects."""

from importlib.metadata import version

__version__ = version("ue-eyes")
```

- [ ] **Step 2: Run tests to verify version still resolves**

Run: `uv run python -c "from ue_eyes import __version__; print(__version__)"`
Expected: `0.1.0`

Run: `uv run pytest tests/ -v`
Expected: 204 passed

- [ ] **Step 3: Run version check script**

Run: `uv run python scripts/check_version.py`

Note: The check script reads `__version__` from the file via regex. Since the file no longer has a hardcoded string, update the script's `get_init_version()` to also handle the `importlib.metadata` pattern — or simpler: have it import the package:

```python
def get_init_version() -> str:
    """Get version by importing the package."""
    import importlib
    mod = importlib.import_module("ue_eyes")
    return mod.__version__
```

Update `scripts/check_version.py` with this change if the regex approach no longer works.

- [ ] **Step 4: Commit**

```bash
git add ue_eyes/__init__.py scripts/check_version.py
git commit -m "chore: use importlib.metadata as version source of truth"
```

---

### Task 3: Gitignore C++ Binaries

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add C++ binary exclusions**

Append to `.gitignore`:

```
# UE C++ plugin build artifacts
plugin/UEEyes/Binaries/
plugin/UEEyes/Intermediate/
```

- [ ] **Step 2: Remove tracked binaries from git (if any)**

Run: `git status` to check if any binaries are tracked. If the binaries are untracked (shown as `??` in the earlier status), no removal needed. If tracked, run:

```bash
git rm --cached plugin/UEEyes/Binaries/Win64/UnrealEditor-UEEyes.dll
git rm --cached plugin/UEEyes/Binaries/Win64/UnrealEditor-UEEyes.pdb
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore C++ plugin binaries and intermediates"
```

---

### Task 4: C++ Build Instructions in README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the current README to find the right insertion point**

Look for the existing "Optional C++ Plugin" section or the end of the installation section.

- [ ] **Step 2: Add the build instructions section**

Insert after the existing plugin mention:

```markdown
### Building the C++ Plugin from Source

The C++ plugin is optional — everything works via Python remote execution without it.

**Prerequisites:**
- Unreal Engine 5.7
- Visual Studio 2022 or Rider

**Steps:**
1. Copy or symlink `plugin/UEEyes/` into your project's `Plugins/` directory
2. Right-click your `.uproject` → **Generate Visual Studio project files**
3. Open the `.sln` and build the **Development Editor** configuration
4. Restart the UE editor

**Note:** Pre-built binaries are not included in the repository. UE embeds a `BuildId` that must match your editor installation, so building from source is the reliable path.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add C++ plugin build instructions to README"
```
