import sys
from pathlib import Path

from tests._runner import run_pytest

if __name__ == "__main__":
    raise SystemExit(run_pytest(Path(__file__).resolve().parent, sys.argv[1:]))
