# Re-exports everything from core/config.py.
# Edit core/config.py to change settings — this file just keeps imports working.
from core.config import *  # noqa: F401,F403
from core.config import COL, DATABASE_URL, OPENAI_API_KEY, VECTOR_STORE_ID  # noqa: F401
from core.config import APIFY_API_KEY, APIFY_LINKEDIN_ACTOR  # noqa: F401
