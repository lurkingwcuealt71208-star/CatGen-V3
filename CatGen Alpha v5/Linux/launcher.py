from pathlib import Path
import sys
import os

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CATGEN_REQUIREMENTS_PATH", str(Path(__file__).resolve().parent / "requirements.txt"))

from launcher_core import main


if __name__ == "__main__":
    main()
