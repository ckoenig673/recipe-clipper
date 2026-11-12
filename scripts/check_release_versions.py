from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "1.0.0"


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require_match(relative_path: str, pattern: str, expected: str) -> None:
    match = re.search(pattern, read_text(relative_path), flags=re.MULTILINE)
    if match is None:
        raise SystemExit(f"{relative_path}: version pattern was not found")
    actual = match.group(1)
    if actual != expected:
        raise SystemExit(f"{relative_path}: expected {expected}, found {actual}")


def require_json_version(relative_path: str, expected: str) -> None:
    payload = json.loads(read_text(relative_path))
    actual = str(payload.get("version") or "")
    if actual != expected:
        raise SystemExit(f"{relative_path}: expected {expected}, found {actual or '<missing>'}")


def main() -> int:
    require_match(
        "backend/app/main.py",
        r'return\s+\{\s*"version"\s*:\s*"([^"]+)"\s*\}',
        EXPECTED_VERSION,
    )
    require_match(
        "frontend/app.js",
        r"APP_BUILD_VERSION\s*=\s*`([^\s`]+)\s+\(\$\{CACHE_BUST_VERSION\}\)`",
        EXPECTED_VERSION,
    )
    require_json_version("package.json", EXPECTED_VERSION)
    require_json_version("package-lock.json", EXPECTED_VERSION)
    require_match(
        ".env.example",
        r"^CACHE_BUST_VERSION=([^\s]+)$",
        EXPECTED_VERSION,
    )
    require_match(
        "docker-compose.yml",
        r"CACHE_BUST_VERSION:\s*\$\{CACHE_BUST_VERSION:-([^}]+)\}",
        EXPECTED_VERSION,
    )
    require_match(
        "CHANGELOG.md",
        r"^## \[([^\]]+)\] - (?:Unreleased|\d{4}-\d{2}-\d{2})$",
        EXPECTED_VERSION,
    )
    require_match(
        "docs/architecture/README.md",
        r"Recipe Clipper `([^`]+)` uses",
        EXPECTED_VERSION,
    )
    print(f"Release version sources agree on {EXPECTED_VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
