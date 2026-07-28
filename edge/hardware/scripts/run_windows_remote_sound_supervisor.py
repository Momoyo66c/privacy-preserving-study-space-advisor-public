"""Launch the supervisor directly with the D-drive virtual environment.

Windows venv launchers create a second Python process. Task Scheduler can then
stop only the launcher and leave the real supervisor alive. This bootstrap is
executed by the base interpreter directly while loading all dependencies and
project source from ``.venv-windows`` on the project drive.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path


HARDWARE_ROOT = Path(__file__).resolve().parents[1]
VENV_SITE_PACKAGES = (
    HARDWARE_ROOT / ".venv-windows" / "Lib" / "site-packages"
)

if not VENV_SITE_PACKAGES.is_dir():
    raise SystemExit(
        f"missing Windows environment site-packages: {VENV_SITE_PACKAGES}"
    )

site.addsitedir(str(VENV_SITE_PACKAGES))
sys.path.insert(0, str(HARDWARE_ROOT / "src"))
child_paths = [str(HARDWARE_ROOT / "src"), str(VENV_SITE_PACKAGES)]
existing_pythonpath = os.environ.get("PYTHONPATH")
if existing_pythonpath:
    child_paths.append(existing_pythonpath)
os.environ["PYTHONPATH"] = os.pathsep.join(child_paths)

from study_space_hardware.remote_sound_supervisor import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
