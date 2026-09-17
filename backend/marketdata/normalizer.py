from typing import Any
from backend.marketdata.models import Trade, BookDelta, BookSnapshot

def normalize_agg_trade(raw: dict[str, Any]) -> Trade:
    """
    Normalizes a raw Binance aggTrade stream payload into a Trade model.
    
    Aggressor logic:
    Binance 'm' (is_buyer_maker):
      - m == True: The buyer was the passive maker, meaning the seller crossed the spread.
        Therefore, aggressor side is SELL (ask-side fill, negative delta).
      - m == False: The seller was the passive maker, meaning the buyer crossed the spread.
        Therefore, aggressor side is BUY (bid-side fill, positive delta).
    """
    # If payload is wrapped in combined stream object {"stream": "...", "data": {...}}
    data = raw.get("data", raw)
    price = float(data["p"])
    qty = float(data["q"])
    is_buyer_maker = bool(data["m"])
    side = "SELL" if is_buyer_maker else "BUY"
    
    return Trade(
        symbol=str(data["s"]).upper(),
        agg_id=int(data["a"]),
        price=price,
        qty=qty,
        quote_qty=price * qty,
        ts=int(data["T"]),
        is_buyer_maker=is_buyer_maker,
        side=side,
        first_id=int(data.get("f", data["a"])),
        last_id=int(data.get("l", data["a"]))
    )

def normalize_depth_update(raw: dict[str, Any]) -> BookDelta:
    """Normalizes raw Binance depth diff stream payload (@depth@100ms)."""
    data = raw.get("data", raw)
    return BookDelta(
        symbol=str(data["s"]).upper(),
        first_update_id=int(data["U"]),
        final_update_id=int(data["u"]),
        bids=[[float(p), float(q)] for p, q in data.get("b", [])],
        asks=[[float(p), float(q)] for p, q in data.get("a", [])],
        event_ts=int(data.get("E", 0))
    )

def normalize_depth_snapshot(raw: dict[str, Any], symbol: str, source: str = "REST") -> BookSnapshot:
    """Normalizes REST depth snapshot (/api/v3/depth)."""
    return BookSnapshot(
        symbol=symbol.upper(),
        last_update_id=int(raw["lastUpdateId"]),
        bids=[[float(p), float(q)] for p, q in raw.get("bids", [])],
        asks=[[float(p), float(q)] for p, q in raw.get("asks", [])],
        ts=int(raw.get("ts", 0)),
        source=source  # type: ignore[arg-type]
    )
