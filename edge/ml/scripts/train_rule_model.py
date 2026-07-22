#!/usr/bin/env python3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from study_space_ml.scripts.train_rule_model import main

if __name__ == "__main__":
    raise SystemExit(main())
