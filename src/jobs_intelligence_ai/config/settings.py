"""
config.py — Easy-to-change settings for Jobs Intelligence Austria.

Edit this file to switch models, tune matching, or adjust app behaviour.
All other modules import from the root config.py which re-exports everything here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  COUNTRY  — selects the active profile (DB, columns, vector store, features)
#  Set COUNTRY=sk in .env to run the Slovak demo; defaults to Austria.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from .profiles import get_profile

COUNTRY          = os.getenv("COUNTRY", "at").lower()
PROFILE          = get_profile(COUNTRY)
COUNTRY_LABEL    = PROFILE.label
COUNTRY_DEMONYM  = PROFILE.demonym
COUNTRY_LANGUAGE = PROFILE.language
DB_SCHEMA        = PROFILE.db_schema
APP_SCHEMA       = PROFILE.app_schema     # shared pipeline DB (candidates etc.)
TABLE_PREFIX     = PROFILE.table_prefix   # per-country table prefix ("" / "sk_")
CURRENCY         = PROFILE.currency
HAS_GUIDED       = PROFILE.has_guided
HAS_MAP          = PROFILE.has_map
HAS_ANALYTICS    = PROFILE.has_analytics
HAS_OCC_FILTER   = PROFILE.has_occ_filter

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI MODELS  — change these to swap model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Main chat + matching model
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.5")

# Model used for lightweight batch classification (seniority, etc.)
# gpt-4o-mini is fast and cheap — no need for a large model here
CLASSIFIER_MODEL = os.getenv("CLASSIFIER_MODEL", "gpt-5.4-nano")

# Embedding model (used if you re-index the vector store)
EMBEDDING_MODEL = "text-embedding-3-small"

# How many documents file_search retrieves from the vector store per query
MAX_NUM_RESULTS = 30

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MATCHING THRESHOLDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SCORE_A_MIN = 0.80   # A grade — strong match (>= 80%)
SCORE_B_MIN = 0.60   # B grade — good match (60–80%)
                     # below SCORE_B_MIN → C grade (< 60%)

DEFAULT_TOP_N = 20   # default results returned per search
MAX_TOP_N     = 50   # hard cap

# Matching cycles: a single vector+LLM pass under-covers (stochastic retrieval +
# the model lists only a subset), so we run the same query several times and
# merge/dedupe the results to raise recall. MATCH_CYCLES drives the legacy
# fixed-count parallel path (/api/match); the streaming path (/api/match/stream)
# ignores it and instead CONVERGES — running waves until the pool stops growing.
MATCH_CYCLES     = int(os.getenv("MATCH_CYCLES", "5"))   # passes (legacy fixed path)

# Convergence knobs for the streaming search. It runs cycles in parallel WAVES,
# accumulating a deduped job pool, and stops once a whole wave adds
# <= MATCH_CONVERGE_NEW new jobs (after MIN_MATCH_CYCLES) or MAX_MATCH_CYCLES is
# hit — so results stabilize on the genuinely-compatible jobs instead of churning
# run-to-run from sampling only a few cycles. All env-tunable.
MAX_MATCH_CYCLES   = int(os.getenv("MAX_MATCH_CYCLES",   "8"))  # hard cap
MIN_MATCH_CYCLES   = int(os.getenv("MIN_MATCH_CYCLES",   "3"))  # floor before converging
MATCH_WAVE_SIZE    = int(os.getenv("MATCH_WAVE_SIZE",    "2"))  # cycles per parallel wave
MATCH_CONVERGE_NEW = int(os.getenv("MATCH_CONVERGE_NEW", "1"))  # stop when a wave adds <= this

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OPENAI KEYS & VECTOR STORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
VECTOR_STORE_ID = os.getenv(PROFILE.vector_store_env, "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  APIFY  (LinkedIn profile enrichment actor)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

APIFY_API_KEY  = os.getenv("APIFY_API_KEY", "")
# anchor/linkedin-profile-enrichment — input { startUrls: [{url, id}] }
APIFY_LINKEDIN_ACTOR = os.getenv("APIFY_LINKEDIN_ACTOR", "AgfKk0sQQxkpQJ1Dt")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATABASE_URL = os.getenv(PROFILE.db_url_env, "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FLASK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_PORT  = int(os.getenv("FLASK_PORT", 5000))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB COLUMN MAPPING  (View_Jobs_Full → internal key)
#  Now provided per-country by the active profile — see core/profiles.py.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COL = PROFILE.col
