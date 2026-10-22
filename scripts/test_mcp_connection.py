"""Explicit public Binance connectivity CLI. Imports never load keys or perform I/O."""
__test__ = False


def check_connection(market: str = 'spot', symbol: str = 'BTCUSDT', *, get=None) -> int:
    """Read production server time and price only; never access authenticated trading."""
    import math
    if get is None:
        import requests
        get = requests.get
    roots = {'spot':'https://api.binance.com/api/v3',
             'futures':'https://fapi.binance.com/fapi/v1'}
    if market not in roots or not symbol.isalnum():
        raise ValueError('Choose spot/futures and an alphanumeric symbol')
    try:
        clock=get(roots[market]+'/time',timeout=10)
        clock.raise_for_status()
        if int(clock.json()['serverTime'])<=0:
            raise ValueError('Invalid server time')
        ticker=get(roots[market]+'/ticker/price',params={'symbol':symbol.upper()},timeout=10)
        ticker.raise_for_status()
        price=float(ticker.json()['price'])
        if not math.isfinite(price) or price<=0:
            raise ValueError('Invalid public price')
        print(f'[OK] {market} production public GETs: {symbol.upper()} price {price:g}; authenticated execution untested.')
        return 0
    except Exception as exc:
        print(f'[ERROR] Public connectivity unavailable ({type(exc).__name__}); authenticated execution untested.')
        return 1


def main() -> int:
    """Run only when explicitly requested from the command line."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--market',choices=['spot','futures'],default='spot')
    parser.add_argument('--symbol',default='BTCUSDT')
    args=parser.parse_args()
    return check_connection(args.market,args.symbol)


if __name__=='__main__':
    raise SystemExit(main())
