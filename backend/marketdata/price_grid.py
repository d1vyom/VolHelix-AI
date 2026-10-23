"""Decimal exchange grids without binary-boundary drift or fixed-place truncation."""

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def grouped_tick_size(tick_size: float, multiplier: float) -> float:
    """Multiply grid parameters before returning their wire-compatible float."""
    return float(Decimal(str(tick_size)) * Decimal(str(multiplier)))


def round_to_tick(price: float, tick_group: float, *, up: bool = False) -> float:
    """Floor a price to its decimal grid, or ceil asks without moving exact ticks."""
    tick = Decimal(str(tick_group))
    value = Decimal(str(price))
    units = (value / tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR)
    return float(units * tick)
