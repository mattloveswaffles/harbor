"""Write docs/openapi.json from the FastAPI app, for the frontend's typed client (openapi-typescript).

Run from backend/ after any endpoint or field change:

    python tools/export_openapi.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND.parent / "docs" / "openapi.json"


def main() -> None:
    sys.path.insert(0, str(BACKEND))
    # The schema doesn't depend on the bank or the database, so use throwaway ones.
    os.environ["NESSIE_MODE"] = "fake"
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'openapi.db'}"
    from harbor.main import app

    schema = app.openapi()
    OUT.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(schema['paths'])} paths)")


if __name__ == "__main__":
    main()
