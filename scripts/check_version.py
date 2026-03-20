"""Check that version strings are consistent across pyproject.toml, ue_eyes/__init__.py,
and .claude-plugin/plugin.json."""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def read_version_from_text(label: str, path: Path, pattern: re.Pattern) -> str:
    text = path.read_text(encoding="utf-8")
    match = pattern.search(text)
    if not match:
        print(f"ERROR: Could not find version in {label} ({path})", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def read_version_from_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if not version:
        print(f"ERROR: No 'version' field in {path}", file=sys.stderr)
        sys.exit(1)
    return version


def get_pyproject_version() -> str:
    pattern = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
    return read_version_from_text(
        "pyproject.toml",
        REPO_ROOT / "pyproject.toml",
        pattern,
    )


def get_init_version() -> str:
    import importlib
    mod = importlib.import_module("ue_eyes")
    return mod.__version__


def main() -> None:
    versions: dict[str, str] = {}

    versions["pyproject.toml"] = get_pyproject_version()
    versions["ue_eyes/__init__.py"] = get_init_version()
    versions[".claude-plugin/plugin.json"] = read_version_from_json(
        REPO_ROOT / ".claude-plugin" / "plugin.json"
    )

    unique = set(versions.values())
    if len(unique) == 1:
        (version,) = unique
        print(f"All versions match: {version}")
        sys.exit(0)

    print("ERROR: Version mismatch detected:", file=sys.stderr)
    for label, version in versions.items():
        print(f"  {label}: {version}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
