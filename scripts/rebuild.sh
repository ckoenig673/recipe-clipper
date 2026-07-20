#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}" || exit 1

echo "🧹 Cleaning old containers..."
docker compose down --remove-orphans

echo "🐳 Rebuilding..."
docker compose up -d --build

echo "✅ Done"
