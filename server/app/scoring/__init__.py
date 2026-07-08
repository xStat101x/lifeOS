"""Pure, DB-free scoring engine (spec §7–§9).

Nothing in this package imports SQLAlchemy or touches a database. It operates on
plain dataclasses (logs + ``ScoringConfig``) and returns evaluations, so it runs with
zero external services, is deterministic (§20), and can be ported to the phone (§4.1).
A separate adapter (later) loads rows from Postgres and feeds these functions.
"""
