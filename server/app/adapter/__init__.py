"""Postgres <-> scoring-engine adapter (spec §6, §20).

Wraps the pure, DB-free engine in ``app/scoring/`` WITHOUT modifying it. Loads the
relevant config + logs out of Postgres, replays the engine deterministically, and
persists the results (``day_evaluations`` / ``rank_state`` / ``xp_ledger`` /
``account_level``). Nothing here holds scoring state that isn't reconstructable from
``logs + config`` — the persisted rows are a recomputable cache (§20 invariant 4).
"""
