"""Check that version strings are consistent across pyproject.toml, ue_eyes/__init__.py,
and .claude-plugin/plugin.json."""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

VERSION_SOURCES = {
    "pyproject.toml": {
        "path": REPO_ROOT / "pyproject.toml",
        "pattern": re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE),
    },
    "ue_eyes/__init__.py": {
        "path": REPO_ROOT / "ue_eyes" / "__init__.py",
        "pattern": re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE),
    },
}

PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"


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


def main() -> None:
    versions: dict[str, str] = {}

    for label, spec in VERSION_SOURCES.items():
        versions[label] = read_version_from_text(label, spec["path"], spec["pattern"])

    versions[".claude-plugin/plugin.json"] = read_version_from_json(PLUGIN_JSON)

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
