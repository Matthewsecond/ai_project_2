# Re-exports everything from settings.py so callers can `from jobs_intelligence_ai import config`
# and read config.COL, config.DATABASE_URL, etc. Edit settings.py to change behaviour.
from .settings import *  # noqa: F401,F403
from .settings import COL, DATABASE_URL, OPENAI_API_KEY, VECTOR_STORE_ID  # noqa: F401
from .settings import APIFY_API_KEY, APIFY_LINKEDIN_ACTOR, APIFY_LINKEDIN_MODE  # noqa: F401
from .settings import (  # noqa: F401
    COUNTRY, PROFILE, COUNTRY_LABEL, COUNTRY_DEMONYM, COUNTRY_LANGUAGE,
    DB_SCHEMA, APP_SCHEMA, TABLE_PREFIX, CURRENCY,
    HAS_GUIDED, HAS_MAP, HAS_ANALYTICS, HAS_OCC_FILTER,
)
