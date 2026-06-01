"""
config.py — Easy-to-change settings for Jobs Intelligence Austria.

Edit this file to switch models, tune matching, or adjust app behaviour.
All other modules import from the root config.py which re-exports everything here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI MODELS  — change these to swap model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Main chat + matching model
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5.4")

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

SCORE_A_MIN = 0.70   # A grade — strong match
SCORE_B_MIN = 0.50   # B grade — good match
                     # below SCORE_B_MIN → C grade

DEFAULT_TOP_N = 20   # default results returned per search
MAX_TOP_N     = 50   # hard cap

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OPENAI KEYS & VECTOR STORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DATABASE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FLASK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
FLASK_PORT  = int(os.getenv("FLASK_PORT", 5000))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DB COLUMN MAPPING  (View_Jobs_Full → internal key)
#  Only change these if your DB view is renamed.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COL = {
    # Identity
    "job_id":        "id",
    "title":         "position",
    "company":       "company_crawler_name",
    "description":   "description",
    "summary":       "summary",
    # Location
    "state":         "location",
    "city":          "city",
    "municipality":  "municipality",
    "zipcode":       "zipcode",
    "detailed_location": "detailed_location",
    # Salary
    "salary":        "salary",
    "salary_type":   "salary_type",
    "original_salary": "original_salary",
    # Employment
    "work_time":     "work_time",
    "employment_relationship": "employment_relationship",
    "education":     "education",
    # Dates
    "date_posted":   "publication_date",
    "application_deadline": "application_deadline",
    "start_timeline": "start_timeline",
    # Links & meta
    "url":           "cleaned_link",
    "portal":        "portal",
    "order_number":  "order_number",
    "occ_group":     "occupational_group",
    "status":        "status",
    # Skills & contacts
    "skills":        "skills",
    "skills_en":     "skills_english",
    "contacts":      "contacts",
    # Not in view (keep for fallback)
    "esco_skills":   "esco_skills",
    "lat":           "latitude",
    "lon":           "longitude",
}
