"""
shared — foundation layer: reusable code + domain helpers used across the app.

A service may import from `shared`; `shared` never imports a service or the frontend.
Submodules: llm (OpenAI client), json (LLM-response parsing), job (job-dict mapping),
grading (score banding), taxonomy (sector/role taxonomy).
"""
