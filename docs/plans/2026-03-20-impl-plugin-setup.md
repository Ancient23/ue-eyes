# Plugin Setup Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An interactive `ue-eyes setup <project-path>` CLI command that walks users through complete UE project configuration.

**Architecture:** `ue_eyes/project_setup.py` holds pure-logic functions (no I/O prompts). `cli.py` adds the `setup` command that orchestrates the interactive flow using Click prompts. All functions are testable without user interaction.

**Tech Stack:** Python stdlib (json, pathlib), Click

**Spec:** `docs/plans/2026-03-20-plugin-setup-installer.md`

**Execution order:** Can be implemented after Plans 1-2, in parallel with Plan 4. Both this plan and Plan 4 add imports and commands to `cli.py` — if implemented concurrently, resolve merge conflicts in `cli.py`.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `ue_eyes/project_setup.py` | Pure logic: find .uproject, edit .uproject JSON, edit .ini, detect OS symlink command, verify symlink |
| `ue_eyes/cli.py` | Interactive `setup` command using Click prompts |
| `tests/test_project_setup.py` | Unit tests for all project_setup functions |

---

### Task 1: Find .uproject

**Files:**
- Create: `ue_eyes/project_setup.py`
- Create: `tests/test_project_setup.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ue_eyes.project_setup."""

import json
from pathlib import Path

from ue_eyes.project_setup import find_uproject


def test_find_uproject_finds_file(tmp_path):
    uproject = tmp_path / "MyGame.uproject"
    uproject.write_text('{"FileVersion": 3}')
    result = find_uproject(tmp_path)
    assert result == uproject


def test_find_uproject_returns_none_when_missing(tmp_path):
    result = find_uproject(tmp_path)
    assert result is None


def test_find_uproject_finds_first_when_multiple(tmp_path):
    (tmp_path / "A.uproject").write_text("{}")
    (tmp_path / "B.uproject").write_text("{}")
    result = find_uproject(tmp_path)
    assert result is not None
    assert result.suffix == ".uproject"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_project_setup.py -v`
Expected: FAIL — `find_uproject` not found

- [ ] **Step 3: Write minimal implementation**

```python
"""Project setup utilities for configuring UE projects to use ue-eyes.

Pure-logic functions with no interactive I/O — the CLI layer handles prompts.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

# ---------------------------------------------------------------------------
# .uproject discovery
# ---------------------------------------------------------------------------


def find_uproject(project_path: Path) -> Path | None:
    """Find the first .uproject file in *project_path*. Returns None if missing."""
    matches = sorted(project_path.glob("*.uproject"))
    return matches[0] if matches else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_project_setup.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/project_setup.py tests/test_project_setup.py
git commit -m "feat(setup): add .uproject file discovery"
```

---

### Task 2: Edit .uproject to Add Plugins

**Files:**
- Modify: `ue_eyes/project_setup.py`
- Modify: `tests/test_project_setup.py`

- [ ] **Step 1: Write the failing tests**

```python
from ue_eyes.project_setup import add_plugins_to_uproject


def test_add_plugins_creates_plugins_array(tmp_path):
    uproject = tmp_path / "Test.uproject"
    uproject.write_text(json.dumps({"FileVersion": 3}))
    added = add_plugins_to_uproject(uproject, ["PythonScriptPlugin", "UEEyes"])
    assert added == ["PythonScriptPlugin", "UEEyes"]
    data = json.loads(uproject.read_text())
    names = [p["Name"] for p in data["Plugins"]]
    assert "PythonScriptPlugin" in names
    assert "UEEyes" in names


def test_add_plugins_skips_existing(tmp_path):
    uproject = tmp_path / "Test.uproject"
    uproject.write_text(json.dumps({
        "FileVersion": 3,
        "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}],
    }))
    added = add_plugins_to_uproject(uproject, ["PythonScriptPlugin", "UEEyes"])
    assert added == ["UEEyes"]


def test_add_plugins_returns_empty_when_all_present(tmp_path):
    uproject = tmp_path / "Test.uproject"
    uproject.write_text(json.dumps({
        "FileVersion": 3,
        "Plugins": [
            {"Name": "PythonScriptPlugin", "Enabled": True},
            {"Name": "UEEyes", "Enabled": True},
        ],
    }))
    added = add_plugins_to_uproject(uproject, ["PythonScriptPlugin", "UEEyes"])
    assert added == []


def test_add_plugins_creates_backup(tmp_path):
    uproject = tmp_path / "Test.uproject"
    uproject.write_text(json.dumps({"FileVersion": 3}))
    add_plugins_to_uproject(uproject, ["UEEyes"])
    assert (tmp_path / "Test.uproject.bak").exists()
```

Add `import json` to the top of the test file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_project_setup.py::test_add_plugins_creates_plugins_array -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

Add to `ue_eyes/project_setup.py`:

```python
def add_plugins_to_uproject(
    uproject_path: Path, plugins: list[str]
) -> list[str]:
    """Add plugin entries to a .uproject file. Returns names of plugins added.

    Creates a .bak backup before modifying. Skips plugins already present.
    """
    text = uproject_path.read_text(encoding="utf-8")
    data = json.loads(text)

    existing = data.get("Plugins", [])
    existing_names = {p["Name"] for p in existing}

    added: list[str] = []
    for name in plugins:
        if name not in existing_names:
            existing.append({"Name": name, "Enabled": True})
            added.append(name)

    if not added:
        return added

    data["Plugins"] = existing

    # Backup original
    backup_path = uproject_path.with_suffix(".uproject.bak")
    backup_path.write_text(text, encoding="utf-8")

    # Write updated
    uproject_path.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    return added
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_project_setup.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/project_setup.py tests/test_project_setup.py
git commit -m "feat(setup): add .uproject plugin editing"
```

---

### Task 3: Configure Remote Execution (.ini Editing)

**Files:**
- Modify: `ue_eyes/project_setup.py`
- Modify: `tests/test_project_setup.py`

- [ ] **Step 1: Write the failing tests**

```python
from ue_eyes.project_setup import configure_remote_exec

EXPECTED_SECTION = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"


def test_configure_creates_ini_when_missing(tmp_path):
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    changed = configure_remote_exec(config_dir)
    assert changed is True
    ini = (config_dir / "DefaultEditor.ini").read_text()
    assert "bRemoteExecution=True" in ini
    assert "239.0.0.1" in ini


def test_configure_appends_to_existing_ini(tmp_path):
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    ini_path.write_text("[SomeOtherSection]\nKey=Value\n")
    changed = configure_remote_exec(config_dir)
    assert changed is True
    ini = ini_path.read_text()
    assert "[SomeOtherSection]" in ini
    assert "bRemoteExecution=True" in ini


def test_configure_skips_when_already_configured(tmp_path):
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    ini_path.write_text(
        f"{EXPECTED_SECTION}\nbRemoteExecution=True\n"
        'RemoteExecutionMulticastGroupEndpoint=(Address="239.0.0.1",Port=6766)\n'
    )
    changed = configure_remote_exec(config_dir)
    assert changed is False


def test_configure_creates_backup(tmp_path):
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    ini_path.write_text("[Existing]\nFoo=Bar\n")
    configure_remote_exec(config_dir)
    assert (config_dir / "DefaultEditor.ini.bak").exists()
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_project_setup.py::test_configure_creates_ini_when_missing -v`

- [ ] **Step 3: Write implementation**

Add to `ue_eyes/project_setup.py`:

```python
# ---------------------------------------------------------------------------
# Remote execution .ini configuration
# ---------------------------------------------------------------------------

_REMOTE_EXEC_SECTION = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"
_REMOTE_EXEC_BLOCK = (
    f"{_REMOTE_EXEC_SECTION}\n"
    "bRemoteExecution=True\n"
    'RemoteExecutionMulticastGroupEndpoint=(Address="239.0.0.1",Port=6766)\n'
)


def configure_remote_exec(config_dir: Path) -> bool:
    """Enable Python remote execution in DefaultEditor.ini. Returns True if changes made."""
    ini_path = config_dir / "DefaultEditor.ini"

    if ini_path.exists():
        text = ini_path.read_text(encoding="utf-8")
        if _REMOTE_EXEC_SECTION in text and "bRemoteExecution=True" in text:
            return False

        # Backup
        backup = config_dir / "DefaultEditor.ini.bak"
        backup.write_text(text, encoding="utf-8")

        # Append
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + _REMOTE_EXEC_BLOCK
        ini_path.write_text(text, encoding="utf-8")
    else:
        ini_path.write_text(_REMOTE_EXEC_BLOCK, encoding="utf-8")

    return True
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_project_setup.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/project_setup.py tests/test_project_setup.py
git commit -m "feat(setup): add DefaultEditor.ini remote exec configuration"
```

---

### Task 4: Symlink Command Generation and Verification

**Files:**
- Modify: `ue_eyes/project_setup.py`
- Modify: `tests/test_project_setup.py`

- [ ] **Step 1: Write the failing tests**

```python
from ue_eyes.project_setup import get_symlink_command, verify_symlink


def test_get_symlink_command_windows():
    cmd = get_symlink_command(
        Path("C:/Projects/MyGame"),
        Path("C:/Source/ue-eyes/plugin/UEEyes"),
        os_name="Windows",
    )
    assert "mklink /J" in cmd
    assert "Plugins\\UEEyes" in cmd or "Plugins/UEEyes" in cmd


def test_get_symlink_command_linux():
    cmd = get_symlink_command(
        Path("/home/user/MyGame"),
        Path("/home/user/ue-eyes/plugin/UEEyes"),
        os_name="Linux",
    )
    assert "ln -s" in cmd


def test_verify_symlink_true(tmp_path):
    plugins = tmp_path / "Plugins" / "UEEyes"
    plugins.mkdir(parents=True)
    (plugins / "UEEyes.uplugin").write_text("{}")
    assert verify_symlink(tmp_path) is True


def test_verify_symlink_false(tmp_path):
    assert verify_symlink(tmp_path) is False
```

- [ ] **Step 2: Run to verify fail**

- [ ] **Step 3: Write implementation**

Add to `ue_eyes/project_setup.py`:

```python
# ---------------------------------------------------------------------------
# Symlink helpers
# ---------------------------------------------------------------------------

_PLUGIN_SOURCE_DIR = Path(__file__).resolve().parent.parent / "plugin" / "UEEyes"


def get_symlink_command(
    project_path: Path,
    plugin_source: Path | None = None,
    os_name: str | None = None,
) -> str:
    """Return the OS-appropriate symlink command string."""
    if plugin_source is None:
        plugin_source = _PLUGIN_SOURCE_DIR
    if os_name is None:
        os_name = platform.system()

    target = project_path / "Plugins" / "UEEyes"

    if os_name == "Windows":
        return f'mklink /J "{target}" "{plugin_source}"'
    return f'ln -s "{plugin_source}" "{target}"'


def verify_symlink(project_path: Path) -> bool:
    """Check if the UEEyes plugin exists at the expected location."""
    uplugin = project_path / "Plugins" / "UEEyes" / "UEEyes.uplugin"
    return uplugin.exists()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_project_setup.py -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add ue_eyes/project_setup.py tests/test_project_setup.py
git commit -m "feat(setup): add symlink command generation and verification"
```

---

### Task 5: CLI `setup` Command

**Files:**
- Modify: `ue_eyes/cli.py`
- Existing tests in `tests/test_cli.py` — add minimal test

- [ ] **Step 1: Write a test for the command existence**

Add to `tests/test_cli.py`:

```python
def test_setup_command_exists(runner):
    result = runner.invoke(main, ["setup", "--help"])
    assert result.exit_code == 0
    assert "project-path" in result.output.lower() or "PROJECT_PATH" in result.output
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_cli.py::test_setup_command_exists -v`

- [ ] **Step 3: Write the CLI command**

Add to `ue_eyes/cli.py`, after the existing imports add:

```python
from ue_eyes.project_setup import (
    find_uproject,
    add_plugins_to_uproject,
    configure_remote_exec,
    get_symlink_command,
    verify_symlink,
)
```

Then add the command:

```python
@main.command()
@click.argument("project_path", type=click.Path(exists=True), default=".")
def setup(project_path: str) -> None:
    """Set up a UE project to work with ue-eyes."""
    project = Path(project_path).resolve()

    # Step 1: Find .uproject
    click.secho("Step 1: Detecting project...", fg="cyan")
    uproject = find_uproject(project)
    if uproject is None:
        click.secho(f"No .uproject file found in {project}", fg="red")
        click.echo("Are you in the right directory?")
        sys.exit(1)
    click.secho(f"  Found: {uproject.name}", fg="green")

    # Step 2: Symlink guidance
    click.secho("\nStep 2: Plugin symlink", fg="cyan")
    if verify_symlink(project):
        click.secho("  UEEyes plugin already linked, skipping.", fg="green")
        plugin_linked = True
    else:
        cmd = get_symlink_command(project)
        click.echo(f"  Run this command in another terminal (may need admin):\n")
        click.secho(f"    {cmd}\n", fg="yellow")
        click.confirm("  Done? Press Enter to continue", default=True)
        plugin_linked = verify_symlink(project)
        if not plugin_linked:
            click.secho("  Plugin not found — skipping UEEyes (it's optional).", fg="yellow")

    # Step 3: Edit .uproject
    click.secho("\nStep 3: Configuring .uproject...", fg="cyan")
    plugins_to_add = ["PythonScriptPlugin"]
    if plugin_linked:
        plugins_to_add.append("UEEyes")
    added = add_plugins_to_uproject(uproject, plugins_to_add)
    if added:
        click.secho(f"  Added: {', '.join(added)}", fg="green")
    else:
        click.secho("  Already configured, skipping.", fg="green")

    # Step 4: Edit DefaultEditor.ini
    click.secho("\nStep 4: Enabling remote execution...", fg="cyan")
    config_dir = project / "Config"
    config_dir.mkdir(exist_ok=True)
    changed = configure_remote_exec(config_dir)
    if changed:
        click.secho("  Remote execution enabled in DefaultEditor.ini", fg="green")
    else:
        click.secho("  Already configured, skipping.", fg="green")

    # Step 5: Rebuild prompt
    click.secho("\nStep 5: Rebuild required", fg="cyan")
    click.echo("  1. Right-click your .uproject → Generate Visual Studio project files")
    click.echo("  2. Open the editor (or restart if already running)")
    click.confirm("  Press Enter once the editor is running", default=True)

    # Step 6: Verify
    click.secho("\nStep 6: Verifying connection...", fg="cyan")
    ue = UERemoteExecution()
    if ue.ping():
        click.secho("  Connection verified! UE Eyes is ready.", fg="green")
    else:
        click.secho("  Could not connect. Check that the editor is running.", fg="yellow")
        click.echo("  You can retry later with: ue-eyes ping")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: All passed (including new test)

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add ue_eyes/cli.py tests/test_cli.py
git commit -m "feat: add ue-eyes setup interactive installer command"
```
