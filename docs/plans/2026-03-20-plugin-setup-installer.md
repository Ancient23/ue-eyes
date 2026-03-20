# Plan: Plugin Setup Installer (`ue-eyes setup`)

**Date:** 2026-03-20
**Status:** Planned
**Goal:** A single interactive CLI command that walks users through complete UE project setup.

---

## Problem

Setting up UE Eyes in a new Unreal Engine project requires three manual steps across different file formats (.uproject JSON, .ini config, OS-level symlinks). Users must know where each file lives, what to add, and in what format. This friction slows adoption and is error-prone.

## Solution

An interactive `ue-eyes setup <project-path>` command that acts as an installer — detecting the project, guiding the user through each step, editing files automatically where possible, and verifying the result. The command name matches the existing `/ue-eyes:setup` skill, which can invoke this command programmatically.

---

## Command Flow

### Step 1: Detect Project

- Accept a `<project-path>` argument (default: current directory)
- Scan for a `.uproject` file in the given path
- Parse it, display the project name and engine version
- If no `.uproject` found: clear error with suggestions ("Are you in the right directory?")

### Step 2: Symlink Guidance

- Detect the user's OS (Windows/macOS/Linux)
- Compute the correct symlink command:
  - **Windows:** `mklink /J <project>\Plugins\UEEyes <ue-eyes-repo>\plugin\UEEyes`
  - **Linux/macOS:** `ln -s <ue-eyes-repo>/plugin/UEEyes <project>/Plugins/UEEyes`
- Print the command with the actual resolved paths
- Prompt user: "Run this command in another terminal, then press Enter to continue"
- After confirmation, verify the symlink/junction exists at `<project>/Plugins/UEEyes/UEEyes.uplugin`
- If not found: warn and ask if they want to retry or skip (plugin is optional)

### Step 3: Edit .uproject

- Back up the original to `<name>.uproject.bak`
- Parse the JSON, find or create the `Plugins` array
- Add `PythonScriptPlugin` (if not already present)
- Add `UEEyes` (if not already present, and only if symlink was confirmed)
- Write the file back with the same formatting style (indented JSON)
- Report what was added (or "already configured, skipping")

### Step 4: Edit DefaultEditor.ini

- Target: `<project>/Config/DefaultEditor.ini`
- If file doesn't exist, create it
- If it exists, back up to `DefaultEditor.ini.bak`
- Check if `[/Script/PythonScriptPlugin.PythonScriptPluginSettings]` section exists
- If not, append the full section:
  ```ini
  [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
  bRemoteExecution=True
  RemoteExecutionMulticastGroupEndpoint=(Address="239.0.0.1",Port=6766)
  ```
- If the section exists but `bRemoteExecution` is False, update it to True
- Report what was changed (or "already configured, skipping")

### Step 5: Prompt Rebuild

- Print instructions:
  - "Right-click your .uproject file → Generate Visual Studio project files"
  - "Then open the editor (or restart if it's already running)"
- Wait for user confirmation: "Press Enter once the editor is running"

### Step 6: Verify Connection

- Run `ue-eyes ping` programmatically
- On success: "Connection verified! UE Eyes is ready."
- On failure: "Could not connect. Check that the editor is running and remote execution is enabled."
- Offer to retry or exit

---

## Implementation

### New files

- **`ue_eyes/project_setup.py`** — Core logic: project detection, .uproject editing, .ini editing
  - `find_uproject(path: Path) -> Path | None`
  - `add_plugins_to_uproject(uproject_path: Path, plugins: list[str]) -> list[str]` (returns list of what was added)
  - `configure_remote_exec(config_dir: Path) -> bool` (returns whether changes were made)
  - `get_symlink_command(project_path: Path, plugin_source: Path) -> str`
  - `verify_symlink(project_path: Path) -> bool`

- **`tests/test_project_setup.py`** — Unit tests for all setup functions
  - Test .uproject parsing with various existing plugin configurations
  - Test .ini creation and modification
  - Test idempotency (running twice doesn't duplicate entries)
  - Test backup file creation
  - Test edge cases (missing files, malformed JSON, read-only files)

### Modified files

- **`ue_eyes/cli.py`** — Add `setup` command with Click's interactive prompts

### Idempotency

Every step checks current state before making changes. Running `ue-eyes setup` on an already-configured project reports "already set up" for each step and does nothing destructive.

### Edge Cases

| Scenario | Behavior |
|----------|----------|
| No .uproject found | Error with suggestion |
| Plugin already in .uproject | Skip, inform user |
| Remote exec already enabled | Skip, inform user |
| Symlink already exists | Skip, inform user |
| .uproject is read-only | Error with instructions to fix permissions |
| User skips symlink step | Continue without adding UEEyes to .uproject (PythonScriptPlugin still added) |
| Editor not running at verify step | Offer retry or exit gracefully |

---

## Dependencies

- None. Uses only stdlib (`json`, `pathlib`, string manipulation for .ini parsing)
- Click (already a dependency) for interactive prompts

Note: Python's `configparser` is NOT used — UE .ini files use a non-standard format (duplicate keys, section inheritance with +/- prefixes) that `configparser` cannot handle. The .ini editing uses simple string-based parsing instead.
