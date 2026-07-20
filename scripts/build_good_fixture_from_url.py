#!/usr/bin/env python3
"""Build GOOD parser fixtures from a live recipe URL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.main import (
    fetch_recipe_data_from_url,
    REQUEST_HEADERS,
    infer_source,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class _MockHtmlResponse:
    def __init__(self, html: str):
        self.text = html
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def raise_for_status(self) -> None:
        return None


def _parse_saved_html_with_real_pipeline(url: str, html: str) -> dict:
    with patch("backend.app.main.requests.get", return_value=_MockHtmlResponse(html)):
        return fetch_recipe_data_from_url(url)


def build_good_fixture(url: str, fixture_name: str, html_override_path: str | None = None) -> Path:
    fixture_dir = Path("backend/tests/fixtures") / fixture_name
    fixture_dir.mkdir(parents=True, exist_ok=True)

    if html_override_path:
        html = Path(html_override_path).read_text(encoding="utf-8")
    else:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text or ""

    page_path = fixture_dir / "page.html"
    page_path.write_text(html, encoding="utf-8")

    parser_result = _parse_saved_html_with_real_pipeline(url, html)
    _write_json(fixture_dir / "parser_expected.json", parser_result)

    source_app, source_type = infer_source(url)
    final_result = {
        "url": url,
        "title": parser_result.get("title", ""),
        "source_app": source_app,
        "source_type": source_type,
        "image_url": parser_result.get("image_url", ""),
        "ingredients": parser_result.get("ingredients", []),
        "instructions": parser_result.get("instructions", []),
        "ingredient_groups": parser_result.get("ingredient_groups", []),
        "instruction_groups": parser_result.get("instruction_groups", []),
        "servings": parser_result.get("servings", ""),
        "prep_time": parser_result.get("prep_time", ""),
        "cook_time": parser_result.get("cook_time", ""),
        "total_time": parser_result.get("total_time", ""),
        "prep_minutes": parser_result.get("prep_minutes"),
        "cook_minutes": parser_result.get("cook_minutes"),
        "total_minutes": parser_result.get("total_minutes"),
        "needs_review": False,
    }
    _write_json(fixture_dir / "final_expected.json", final_result)

    return fixture_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GOOD recipe fixture from URL")
    parser.add_argument("--url", required=True, help="Recipe page URL")
    parser.add_argument("--fixture-name", required=True, help="Fixture directory name")
    parser.add_argument(
        "--html-file",
        help="Optional local HTML file to use instead of fetching URL (useful in restricted environments)",
    )
    args = parser.parse_args()

    fixture_dir = build_good_fixture(args.url, args.fixture_name, args.html_file)
    print(f"Fixture written to: {fixture_dir}")


if __name__ == "__main__":
    main()
