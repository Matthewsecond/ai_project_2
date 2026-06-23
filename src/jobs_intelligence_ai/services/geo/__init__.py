"""
geo — geographic reference data for the maps/reports.

Currently holds the simplified Austria Bundesland polygon geometry used by the candidate
pipeline report's opportunity map and the Map tab. Pure data — no LLM, no DB. Public API:

    from jobs_intelligence_ai.services.geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT
"""
from .at_geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT

__all__ = ["AT_POLYGONS", "AT_WIDTH", "AT_HEIGHT"]
