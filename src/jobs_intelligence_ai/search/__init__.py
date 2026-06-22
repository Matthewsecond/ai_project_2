"""
search — Convergence search: find the jobs that fit a candidate profile.

Run it as a module:
    python -m jobs_intelligence_ai.search "Senior Python engineer, Bratislava" --sk --stream

Or drive it from code via the one public class, the Orchestrator:
    from jobs_intelligence_ai.search.orchestrator import Orchestrator
    jobs = Orchestrator().run("Senior Python engineer, Bratislava")  # all matches
    jobs = Orchestrator().run("...", filters={"limit": 20})          # capped

The package __init__ intentionally exports nothing: importing `search` must not
pull in the global config, so `--country` in __main__ can set the environment
before the config-bound modules load. Import the Orchestrator from its submodule.
"""
