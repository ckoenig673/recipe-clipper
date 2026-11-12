import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# The application initializes its SQLite schema while test modules are being
# imported.  Keep that initialization isolated from the container-default
# /app/data path so direct local pytest runs remain writable and deterministic.
os.environ.setdefault(
    "RECIPES_DB_PATH",
    str(Path(tempfile.gettempdir()) / "recipe-clipper-pytest.db"),
)
