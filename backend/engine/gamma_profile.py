import numpy as np
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class GammaExposureLevel(BaseModel):
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float
    call_oi: int = 0
    put_oi: int = 0

class GammaProfile(BaseModel):
    spot_price: float
    total_net_gex: float
    call_wall: float = Field(description="Strike with highest positive Call GEX (resistance/ceiling)")
    put_wall: float = Field(description="Strike with highest negative Put GEX (support/floor)")
    gamma_flip: float = Field(description="Zero-gamma level separating stabilizing vs accelerating regimes")
    regime: str = Field(description="'POSITIVE_GAMMA' (Mean-reverting) or 'NEGATIVE_GAMMA' (Trend-accelerating)")
    levels: List[GammaExposureLevel] = []

def calculate_gamma_profile(legs: List[Dict], spot_price: float) -> GammaProfile:
    """
    Calculate Dealer Gamma Exposure (GEX) profile across strikes.
    Standard convention:
    Call GEX = Gamma * Call OI * 100 * Spot^2 * 0.01 (Dealers long calls -> long gamma)
    Put GEX = -Gamma * Put OI * 100 * Spot^2 * 0.01 (Dealers short puts -> short gamma)
    """
    if not legs or spot_price <= 0:
        return GammaProfile(
            spot_price=spot_price,
            total_net_gex=0.0,
            call_wall=round(spot_price * 1.05, 2) if spot_price > 0 else 0.0,
            put_wall=round(spot_price * 0.95, 2) if spot_price > 0 else 0.0,
            gamma_flip=spot_price,
            regime="POSITIVE_GAMMA",
            levels=[]
        )

    strikes_map: Dict[float, Dict] = {}

    for leg in legs:
        strike = float(leg.get("strike", 0.0) or 0.0)
        if strike <= 0:
            continue

        c_type = str(leg.get("type", "CALL")).upper()
        gamma = float(leg.get("gamma", 0.0) or 0.0)
        oi = int(leg.get("open_interest", 0) or leg.get("oi", 0) or 0)
        
        # If gamma is unpopulated from paper feed, approximate based on moneyness & standard normal density
        if gamma <= 0.0:
            dist = abs(strike - spot_price) / spot_price
            gamma = max(0.001, round(0.04 * np.exp(-0.5 * (dist / 0.08) ** 2), 4))

        if strike not in strikes_map:
            strikes_map[strike] = {
                "call_gex": 0.0,
                "put_gex": 0.0,
                "call_oi": 0,
                "put_oi": 0
            }

        # Dollar GEX per 1% move: Gamma * OI * 100 * Spot^2 * 0.01
        dollar_gex = gamma * max(oi, 100) * 100 * (spot_price ** 2) * 0.01 / 1e6  # in $ Millions

        if "CALL" in c_type:
            strikes_map[strike]["call_gex"] += dollar_gex
            strikes_map[strike]["call_oi"] += max(oi, 100)
        else:
            strikes_map[strike]["put_gex"] -= dollar_gex
            strikes_map[strike]["put_oi"] += max(oi, 100)

    levels: List[GammaExposureLevel] = []
    total_net_gex = 0.0

    for strike in sorted(strikes_map.keys()):
        data = strikes_map[strike]
        net_gex = data["call_gex"] + data["put_gex"]
        total_net_gex += net_gex
        levels.append(GammaExposureLevel(
            strike=strike,
            call_gex=round(data["call_gex"], 2),
            put_gex=round(data["put_gex"], 2),
            net_gex=round(net_gex, 2),
            call_oi=data["call_oi"],
            put_oi=data["put_oi"]
        ))

    # Identify Call Wall (strike with highest positive call GEX)
    call_wall = max(levels, key=lambda l: l.call_gex).strike if levels else round(spot_price * 1.05, 2)

    # Identify Put Wall (strike with highest absolute put GEX)
    put_wall = min(levels, key=lambda l: l.put_gex).strike if levels else round(spot_price * 0.95, 2)

    # Find Gamma Flip (strike where cumulative GEX crosses from positive to negative)
    gamma_flip = spot_price
    cum_gex = 0.0
    for l in levels:
        cum_gex += l.net_gex
        if cum_gex >= 0:
            gamma_flip = l.strike
            break

    regime = "POSITIVE_GAMMA" if total_net_gex >= 0 else "NEGATIVE_GAMMA"

    return GammaProfile(
        spot_price=round(spot_price, 2),
        total_net_gex=round(total_net_gex, 2),
        call_wall=round(call_wall, 2),
        put_wall=round(put_wall, 2),
        gamma_flip=round(gamma_flip, 2),
        regime=regime,
        levels=levels
    )
