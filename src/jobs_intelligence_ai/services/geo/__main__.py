"""
__main__.py — Print a summary of the bundled Austria geo data (pure data, no DB/LLM).

    python -m jobs_intelligence_ai.services.geo

Lists each Bundesland with its ring/point counts, plus the canvas size the
opportunity map is drawn against — useful for eyeballing that the polygon data
loaded correctly.
"""
import sys

from .at_geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT


def _force_utf8() -> None:
    # Windows consoles default to cp1252 and choke on the umlauts in Bundesland
    # names (KÄRNTEN, NIEDERÖSTERREICH, ...) — print as UTF-8 instead.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    _force_utf8()
    print(f"Canvas: {AT_WIDTH} x {AT_HEIGHT}")
    print(f"{len(AT_POLYGONS)} Bundesland(er):")
    for name, polygons in sorted(AT_POLYGONS.items()):
        points = sum(len(ring) for ring in polygons)
        print(f"  {name:<20} {len(polygons)} ring(s), {points} point(s)")


if __name__ == "__main__":
    main()
