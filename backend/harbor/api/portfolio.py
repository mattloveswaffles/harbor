"""GET /me/portfolio: the simulated T. Rowe Price ETF holdings, priced with real closes."""

from fastapi import APIRouter
from sqlmodel import col, select

from harbor.clock import iso
from harbor.deps import ClockDep, SessionDep, UserDep
from harbor.models import Lot
from harbor.planning import prices

router = APIRouter(tags=["portfolio"])

DISCLAIMER = ("A simulated portfolio for the Harbor demo, priced with real daily closes. "
              "Not investment advice and not a recommendation to buy or sell any fund.")


@router.get("/me/portfolio")
def get_portfolio(session: SessionDep, user: UserDep, clock: ClockDep) -> dict:
    now = clock.now()
    lots = session.exec(select(Lot).where(Lot.user_id == user.id, col(Lot.sold_at).is_(None))
                        .order_by(col(Lot.symbol), col(Lot.acquired))).all()
    holdings, priced_at = [], None
    for symbol in sorted({lot.symbol for lot in lots}):
        mine = [lot for lot in lots if lot.symbol == symbol]
        price = prices().price_at(symbol, now)
        shares = sum(lot.shares_micro for lot in mine)
        basis = sum(lot.cost_basis_cents for lot in mine)
        value = shares * price.price_cents // 1_000_000 if price else None
        if price and (priced_at is None or price.as_of > priced_at):
            priced_at = price.as_of
        holdings.append({
            "symbol": symbol, "name": price.name if price else symbol,
            "shares": round(shares / 1_000_000, 4), "shares_micro": shares,
            "price_cents": price.price_cents if price else None,
            "price_as_of": iso(price.as_of) if price else None, "price_source": "fixture",
            "value_cents": value, "cost_basis_cents": basis,
            "unrealized_gain_cents": value - basis if value is not None else None,
            "lots": [{"id": l.id, "shares_micro": l.shares_micro, "cost_basis_cents": l.cost_basis_cents,
                      "acquired": l.acquired.isoformat()} for l in mine],
        })
    return {
        "server_time": iso(now),
        "total_value_cents": sum(h["value_cents"] or 0 for h in holdings),
        "priced_at": iso(priced_at), "disclaimer": DISCLAIMER, "holdings": holdings,
    }
