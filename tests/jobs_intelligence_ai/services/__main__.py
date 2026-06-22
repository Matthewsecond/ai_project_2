import sys

from tests._runner import run_package

if __name__ == "__main__":
    raise SystemExit(run_package(__file__, __package__, sys.argv[1:]))
