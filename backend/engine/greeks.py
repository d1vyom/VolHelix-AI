import numpy as np
from scipy.stats import norm

# Constants
TRADING_DAYS_PER_YEAR = 252

def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """Calculate d1 and d2 for Black-Scholes formula."""
    # Prevent division by zero
    T = max(T, 0.0001)
    sigma = max(sigma, 0.0001)
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2

def black_scholes_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Calculate theoretical option price. T is in years."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    
    if option_type.upper() == 'CALL':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:  # PUT
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        
    return float(max(price, 0.0))

def calculate_delta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Calculate Option Delta."""
    d1, _ = _d1_d2(S, K, T, r, sigma)
    
    if option_type.upper() == 'CALL':
        return float(norm.cdf(d1))
    else:
        return float(norm.cdf(d1) - 1.0)

def calculate_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate Option Gamma (same for calls and puts)."""
    d1, _ = _d1_d2(S, K, T, r, sigma)
    T = max(T, 0.0001)
    sigma = max(sigma, 0.0001)
    
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return float(gamma)

def calculate_theta(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Calculate Option Theta (1 day decay)."""
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    T = max(T, 0.0001)
    
    p1 = -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
    
    if option_type.upper() == 'CALL':
        p2 = r * K * np.exp(-r * T) * norm.cdf(d2)
        theta = p1 - p2
    else:
        p2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
        theta = p1 + p2
        
    return float(theta / 365.0)

def calculate_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Calculate Option Vega (change per 1% change in IV)."""
    d1, _ = _d1_d2(S, K, T, r, sigma)
    T = max(T, 0.0001)
    
    vega = S * norm.pdf(d1) * np.sqrt(T)
    return float(vega / 100.0)
