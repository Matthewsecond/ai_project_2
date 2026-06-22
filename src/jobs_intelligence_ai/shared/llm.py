"""
llm.py — the single OpenAI client for the whole app.

One lazily-created singleton, shared by every caller (chat, search, clustering,
persona, …). Centralizing it here means there is exactly one place that constructs
the client — which also makes it the single seam to mock in tests.

    from jobs_intelligence_ai.shared.llm import get_client
    client = get_client()
"""
import logging

from openai import OpenAI

from jobs_intelligence_ai import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def get_client(api_key: str | None = None) -> OpenAI:
    """Return the shared OpenAI client, creating it once.

    `api_key` defaults to config.OPENAI_API_KEY. Because the client is a singleton,
    only the first call's key takes effect (every caller uses the same configured key).
    """
    global _client
    if _client is None:
        _client = OpenAI(api_key=api_key or config.OPENAI_API_KEY)
    return _client
