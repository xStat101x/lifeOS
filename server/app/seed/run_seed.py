"""Run the §22 seed against the configured database.

    python -m app.seed.run_seed

Assumes migrations have been applied (`alembic upgrade head`).
"""

from __future__ import annotations

from app.db import SessionLocal
from app.seed.seed_data import seed


def main() -> None:
    session = SessionLocal()
    try:
        seed(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
