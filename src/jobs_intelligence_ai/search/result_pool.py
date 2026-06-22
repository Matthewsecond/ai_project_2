"""
result_pool.py — Tallies how often each job id is retrieved across passes.

A single EmbeddingSearch pass is stochastic and under-covers; the Orchestrator
runs a FIXED budget of them and funnels their ids through one ResultPool. The
pool counts how many passes returned each id, so the Orchestrator can keep only
the ids that cleared a quorum (resurfaced in >= K passes) and drop the one-off
long-tail ids a lucky single pass turned up — those are the borderline jobs that
otherwise make the final set, and the A+B count, churn run to run. Scoring is a
separate stage, so the pool tracks id occurrence counts only.
"""


class ResultPool:
    """A tally of matched job ids → how many passes returned each one."""

    def __init__(self):
        self._counts: dict[str, int] = {}

    def add(self, ids: list) -> int:
        """Merge a pass's ids in, incrementing each id's tally. Returns how many
        ids were seen for the FIRST time (not already present) — zero means the
        pass surfaced nothing the pool hadn't already seen."""
        before = len(self._counts)
        for jid in (ids or []):
            if jid:
                key = str(jid)
                self._counts[key] = self._counts.get(key, 0) + 1
        return len(self._counts) - before

    def ids(self, quorum: int = 1) -> list[str]:
        """The ids returned by at least `quorum` passes. quorum=1 is the full
        union (every id ever seen); higher quorums drop the noisy singletons."""
        return [jid for jid, n in self._counts.items() if n >= quorum]

    def __len__(self) -> int:
        return len(self._counts)
