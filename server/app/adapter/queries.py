"""Read-side queries for the rank/XP endpoint (spec §7.6, §8).

Returns the persisted state from the most recent day-close. If a day hasn't been closed
since the latest logs, these reflect the last close (day-close is explicit, §10).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AccountLevel, Domain, RankState, Season, XPLedger


def current_rank(session: Session) -> dict:
    season = session.query(Season).order_by(Season.start_day.desc()).first()
    if season is None:
        return {"season": None, "domains": {}, "overall": None, "xp": _xp(session)}

    key_by_id = {d.id: d.key for d in session.query(Domain).all()}
    domains: dict[str, dict] = {}
    for rs in session.query(RankState).filter(
        RankState.season_id == season.id, RankState.scope == "domain"
    ).all():
        domains[key_by_id.get(rs.scope_id, str(rs.scope_id))] = _rs_dict(rs)

    overall_rs = session.query(RankState).filter(
        RankState.season_id == season.id, RankState.scope == "overall",
        RankState.scope_id.is_(None),
    ).first()

    return {
        "season": season.name,
        "domains": domains,
        "overall": _rs_dict(overall_rs) if overall_rs else None,
        "xp": _xp(session),
    }


def _rs_dict(rs: RankState) -> dict:
    label = f"{rs.tier} {['', 'I', 'II', 'III', 'IV'][rs.division]}" if rs.division \
        else f"{rs.tier} ({int(rs.lp)} LP)"
    return {"lp": round(rs.lp, 2), "tier": rs.tier, "division": rs.division, "label": label}


def _xp(session: Session) -> dict:
    latest = session.query(XPLedger).order_by(
        XPLedger.effective_day.desc().nullslast(), XPLedger.created_at.desc()
    ).first()
    account = session.query(AccountLevel).first()
    return {
        "total": latest.balance if latest else 0,
        "level": account.level if account else 1,
        "xp_into_level": account.xp_into_level if account else 0,
    }
