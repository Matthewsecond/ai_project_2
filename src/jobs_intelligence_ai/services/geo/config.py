"""
config.py — settings for the `geo` service (flat constants, per rework §5).

geo is pure reference geometry, so it has no behavioural knobs of its own. WHETHER a map is
shown at all is a global/environment decision (a country either ships map geometry or not),
exposed as `config.HAS_MAP` — re-exported here as the one switch consumers care about.
Today only the Austrian build has geometry (see at_geo.py); the SK build has `HAS_MAP=False`.
"""
from jobs_intelligence_ai import config

# Whether this deployment has map geometry to render (global/environment flag).
HAS_MAP = config.HAS_MAP
