from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.integration.gate_a_support import create_gate_a_app, ingest_simulated_observation


def main() -> None:
    port = int(os.environ.get("GATE_A_BACKEND_PORT", "8011"))
    database_path = Path(tempfile.gettempdir()) / f"pssa-gate-a-{os.getpid()}.db"
    app = create_gate_a_app(f"sqlite:///{database_path.as_posix()}")
    ingest_simulated_observation(app)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
