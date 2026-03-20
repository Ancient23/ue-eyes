"""Tests for ue_eyes.project_setup — Plugin Setup Installer."""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from ue_eyes.project_setup import (
    find_uproject,
    add_plugins_to_uproject,
    configure_remote_exec,
    get_symlink_command,
    verify_symlink,
)


# ------------------------------------------------------------------
# Task 1: find_uproject
# ------------------------------------------------------------------


def test_find_uproject_finds_file(tmp_path: Path) -> None:
    """find_uproject returns the .uproject file when present."""
    uproject = tmp_path / "MyGame.uproject"
    uproject.write_text('{"FileVersion": 3}')
    result = find_uproject(tmp_path)
    assert result == uproject


def test_find_uproject_returns_none_when_missing(tmp_path: Path) -> None:
    """find_uproject returns None when no .uproject file exists."""
    result = find_uproject(tmp_path)
    assert result is None


def test_find_uproject_finds_first_when_multiple(tmp_path: Path) -> None:
    """find_uproject returns the first (alphabetically sorted) .uproject file."""
    (tmp_path / "Alpha.uproject").write_text('{"FileVersion": 3}')
    (tmp_path / "Zebra.uproject").write_text('{"FileVersion": 3}')
    result = find_uproject(tmp_path)
    assert result is not None
    assert result.name == "Alpha.uproject"


# ------------------------------------------------------------------
# Task 2: add_plugins_to_uproject
# ------------------------------------------------------------------


def test_add_plugins_creates_plugins_array(tmp_path: Path) -> None:
    """add_plugins_to_uproject creates Plugins array when not present."""
    uproject_path = tmp_path / "MyGame.uproject"
    uproject_path.write_text(json.dumps({"FileVersion": 3}))

    added = add_plugins_to_uproject(uproject_path, ["PythonScriptPlugin"])

    assert "PythonScriptPlugin" in added
    data = json.loads(uproject_path.read_text())
    plugin_names = [p["Name"] for p in data["Plugins"]]
    assert "PythonScriptPlugin" in plugin_names


def test_add_plugins_skips_existing(tmp_path: Path) -> None:
    """add_plugins_to_uproject skips plugins that are already listed."""
    initial = {
        "FileVersion": 3,
        "Plugins": [
            {"Name": "PythonScriptPlugin", "Enabled": True},
        ],
    }
    uproject_path = tmp_path / "MyGame.uproject"
    uproject_path.write_text(json.dumps(initial))

    added = add_plugins_to_uproject(
        uproject_path, ["PythonScriptPlugin", "UEEyes"]
    )

    assert "PythonScriptPlugin" not in added
    assert "UEEyes" in added


def test_add_plugins_returns_empty_when_all_present(tmp_path: Path) -> None:
    """add_plugins_to_uproject returns empty list when all plugins are already present."""
    initial = {
        "FileVersion": 3,
        "Plugins": [
            {"Name": "PythonScriptPlugin", "Enabled": True},
            {"Name": "UEEyes", "Enabled": True},
        ],
    }
    uproject_path = tmp_path / "MyGame.uproject"
    uproject_path.write_text(json.dumps(initial))

    added = add_plugins_to_uproject(
        uproject_path, ["PythonScriptPlugin", "UEEyes"]
    )

    assert added == []


def test_add_plugins_creates_backup(tmp_path: Path) -> None:
    """add_plugins_to_uproject creates a .bak backup of the original file."""
    uproject_path = tmp_path / "MyGame.uproject"
    original_content = json.dumps({"FileVersion": 3})
    uproject_path.write_text(original_content)

    add_plugins_to_uproject(uproject_path, ["PythonScriptPlugin"])

    bak_path = uproject_path.with_suffix(".uproject.bak")
    assert bak_path.exists()
    assert bak_path.read_text() == original_content


# ------------------------------------------------------------------
# Task 3: configure_remote_exec
# ------------------------------------------------------------------

_REMOTE_EXEC_SECTION = "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]"
_REMOTE_EXEC_KEY = "bRemoteExecution=True"


def test_configure_remote_exec_creates_ini_when_missing(tmp_path: Path) -> None:
    """configure_remote_exec creates DefaultEditor.ini with the remote exec block."""
    config_dir = tmp_path / "Config"
    config_dir.mkdir()

    result = configure_remote_exec(config_dir)

    assert result is True
    ini_path = config_dir / "DefaultEditor.ini"
    assert ini_path.exists()
    content = ini_path.read_text()
    assert _REMOTE_EXEC_SECTION in content
    assert _REMOTE_EXEC_KEY in content


def test_configure_remote_exec_appends_to_existing(tmp_path: Path) -> None:
    """configure_remote_exec appends the block to an existing ini file."""
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    ini_path.write_text("[Core.System]\nPaths=../../../Engine/Content\n")

    result = configure_remote_exec(config_dir)

    assert result is True
    content = ini_path.read_text()
    assert "[Core.System]" in content
    assert _REMOTE_EXEC_SECTION in content
    assert _REMOTE_EXEC_KEY in content


def test_configure_remote_exec_skips_when_already_configured(tmp_path: Path) -> None:
    """configure_remote_exec returns False and makes no changes when already configured."""
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    ini_content = (
        "[/Script/PythonScriptPlugin.PythonScriptPluginSettings]\n"
        "bRemoteExecution=True\n"
        'RemoteExecutionMulticastGroupEndpoint=(Address="239.0.0.1",Port=6766)\n'
    )
    ini_path.write_text(ini_content)

    result = configure_remote_exec(config_dir)

    assert result is False
    # File content should not have changed
    assert ini_path.read_text() == ini_content


def test_configure_remote_exec_creates_backup(tmp_path: Path) -> None:
    """configure_remote_exec creates a .bak backup of an existing ini file."""
    config_dir = tmp_path / "Config"
    config_dir.mkdir()
    ini_path = config_dir / "DefaultEditor.ini"
    original_content = "[Core.System]\nPaths=../../../Engine/Content\n"
    ini_path.write_text(original_content)

    configure_remote_exec(config_dir)

    bak_path = ini_path.with_suffix(".ini.bak")
    assert bak_path.exists()
    assert bak_path.read_text() == original_content


# ------------------------------------------------------------------
# Task 4: get_symlink_command / verify_symlink
# ------------------------------------------------------------------


def test_get_symlink_command_windows(tmp_path: Path) -> None:
    """get_symlink_command returns a mklink /D command on Windows."""
    plugin_source = tmp_path / "plugin" / "UEEyes"
    cmd = get_symlink_command(tmp_path, plugin_source=plugin_source, os_name="Windows")
    assert "mklink" in cmd
    assert "/D" in cmd
    assert "UEEyes" in cmd


def test_get_symlink_command_linux(tmp_path: Path) -> None:
    """get_symlink_command returns an ln -s command on Linux."""
    plugin_source = tmp_path / "plugin" / "UEEyes"
    cmd = get_symlink_command(tmp_path, plugin_source=plugin_source, os_name="Linux")
    assert "ln" in cmd
    assert "-s" in cmd
    assert "UEEyes" in cmd


def test_verify_symlink_true(tmp_path: Path) -> None:
    """verify_symlink returns True when the UEEyes plugin directory exists."""
    plugins_dir = tmp_path / "Plugins"
    plugins_dir.mkdir()
    (plugins_dir / "UEEyes").mkdir()

    assert verify_symlink(tmp_path) is True


def test_verify_symlink_false(tmp_path: Path) -> None:
    """verify_symlink returns False when the UEEyes plugin directory is absent."""
    assert verify_symlink(tmp_path) is False
