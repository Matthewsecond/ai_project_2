# services/geo/

Geographic reference data for the maps/reports. Pure data — no LLM, no DB. Packaged in
rework Stage 2.3 #8 from the loose `services/at_geo.py`.

## Layout
```
services/geo/
├── __init__.py   # public API
├── config.py     # re-exports the global HAS_MAP flag (geo has no behavioural knobs)
└── at_geo.py     # simplified Austria Bundesland polygons (normalized, y-up)
```

## Public API
```python
from jobs_intelligence_ai.services.geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT
```
Consumer: `services/reporting/report_pipeline.py` (the candidate-pipeline report's Austria
opportunity map). Whether a map renders at all is gated by the global `config.HAS_MAP`
(re-exported as `geo.config.HAS_MAP`): only the Austrian build ships geometry; the SK build
has `HAS_MAP=False`.

## Tests
`tests/jobs_intelligence_ai/services/geo/unit_tests/test_1_geometry.py` (3, offline): pins
the data — all 9 Bundesländer present, positive canvas dimensions, every ring a list of
(x, y) pairs inside the declared bounds.
