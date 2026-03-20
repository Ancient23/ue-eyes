"""Project setup utilities for configuring UE projects to use ue-eyes."""

from __future__ import annotations

import json
import platform
import shutil
from pathlib import Path

# Path to the UEEyes plugin source bundled with this package.
_PLUGIN_SOURCE_DIR: Path = Path(__file__).resolve().parent.parent / "plugin" / "UEEyes"

# Remote execution block inserted into DefaultEditor.ini.
_REMOTE_EXEC_SECTION = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"
_REMOTE_EXEC_BLOCK = (
    "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\n"
    "bRemoteExecution=True\n"
    'RemoteExecutionMulticastGroupEndpoint=(Address="239.0.0.1",Port=6766)\n'
)

# Expected plugin location relative to project root.
_PLUGIN_SUBDIR = Path("Plugins") / "UEEyes"


# ------------------------------------------------------------------
# Task 1: Find .uproject
# ------------------------------------------------------------------


def find_uproject(project_path: Path) -> Path | None:
    """Find the first .uproject file in project_path.

    Returns the alphabetically-first match, or None if no file is found.
    """
    matches = sorted(project_path.glob("*.uproject"))
    return matches[0] if matches else None


# ------------------------------------------------------------------
# Task 2: Edit .uproject to add plugins
# ------------------------------------------------------------------


def add_plugins_to_uproject(uproject_path: Path, plugins: list[str]) -> list[str]:
    """Add plugin entries to a .uproject file.

    Creates a ``.bak`` backup before modifying. Skips plugins that are already
    present in the file.

    Parameters
    ----------
    uproject_path:
        Absolute path to the ``.uproject`` file.
    plugins:
        List of plugin names to add (e.g. ``["PythonScriptPlugin", "UEEyes"]``).

    Returns
    -------
    list[str]
        Names of plugins that were actually added (excludes already-present ones).
    """
    original_text = uproject_path.read_text(encoding="utf-8")
    data: dict = json.loads(original_text)

    existing_names: set[str] = {
        p["Name"] for p in data.get("Plugins", [])
    }

    to_add = [name for name in plugins if name not in existing_names]
    if not to_add:
        return []

    # Create backup before modifying.
    bak_path = uproject_path.with_suffix(".uproject.bak")
    bak_path.write_text(original_text, encoding="utf-8")

    if "Plugins" not in data:
        data["Plugins"] = []

    for name in to_add:
        data["Plugins"].append({"Name": name, "Enabled": True})

    uproject_path.write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    return to_add


# ------------------------------------------------------------------
# Task 3: Configure remote execution (.ini)
# ------------------------------------------------------------------


def configure_remote_exec(config_dir: Path) -> bool:
    """Enable Python remote execution in DefaultEditor.ini.

    Uses string-based parsing (not configparser) because UE .ini files use a
    non-standard format with duplicate keys and custom value syntax.

    Creates a ``.bak`` backup of an existing file before modifying it.

    Parameters
    ----------
    config_dir:
        Path to the project's ``Config/`` directory.

    Returns
    -------
    bool
        ``True`` if changes were made, ``False`` if already configured.
    """
    ini_path = config_dir / "DefaultEditor.ini"

    if ini_path.exists():
        existing_text = ini_path.read_text(encoding="utf-8")
        if _REMOTE_EXEC_SECTION in existing_text and "bRemoteExecution=True" in existing_text:
            return False

        # Create backup before modifying.
        bak_path = ini_path.with_suffix(".ini.bak")
        bak_path.write_text(existing_text, encoding="utf-8")

        # Append the block separated by a blank line.
        separator = "" if existing_text.endswith("\n") else "\n"
        updated_text = existing_text + separator + "\n" + _REMOTE_EXEC_BLOCK
        ini_path.write_text(updated_text, encoding="utf-8")
    else:
        # Create the ini file from scratch.
        ini_path.write_text(_REMOTE_EXEC_BLOCK, encoding="utf-8")

    return True


# ------------------------------------------------------------------
# Task 4: Symlink command generation and verification
# ------------------------------------------------------------------


def get_symlink_command(
    project_path: Path,
    plugin_source: Path | None = None,
    os_name: str | None = None,
) -> str:
    """Return the OS-appropriate symlink command string.

    Parameters
    ----------
    project_path:
        Root directory of the UE project.
    plugin_source:
        Source directory of the UEEyes plugin. Defaults to the bundled plugin.
    os_name:
        Operating system name (``"Windows"`` or ``"Linux"``). Defaults to the
        current OS via :func:`platform.system`.

    Returns
    -------
    str
        A shell command string that creates the plugin symlink.
    """
    if plugin_source is None:
        plugin_source = _PLUGIN_SOURCE_DIR

    if os_name is None:
        os_name = platform.system()

    link_target = project_path / _PLUGIN_SUBDIR

    if os_name == "Windows":
        return f'mklink /D "{link_target}" "{plugin_source}"'
    else:
        return f'ln -s "{plugin_source}" "{link_target}"'


def verify_symlink(project_path: Path) -> bool:
    """Check whether the UEEyes plugin exists at the expected location.

    Parameters
    ----------
    project_path:
        Root directory of the UE project.

    Returns
    -------
    bool
        ``True`` if the ``Plugins/UEEyes`` directory exists under *project_path*.
    """
    plugin_path = project_path / _PLUGIN_SUBDIR
    return plugin_path.exists()
