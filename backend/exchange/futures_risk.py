"""Fresh 1x Futures risk with signed exposure and separate exit semantics."""
import math
from decimal import Decimal
from backend.risk.risk_gate import CryptoRiskGate
from backend.exchange.execution import passes_exchange_filters

def validate_futures_order(request, *, client):
    checks = {}
    try:
        if getattr(client,'market',None) != 'futures':
            raise ValueError('Futures requires the Futures adapter')
        info = client.get_execution_info(request.symbol)
        if (info['status'] != 'TRADING' or info['quote_asset'] != 'USDT'
            or info['contract_type'] != 'PERPETUAL' or info['margin_asset'] != 'USDT'):
            raise ValueError('Active USDT perpetual unavailable on Futures demo')
        # Entry setup must not strand a genuine reduce-only exit at old leverage.
        # get_account still verifies one-way and single-asset mode for both paths.
        if not request.reduce_only:
            client.validate_account_mode(request.symbol)
        current = Decimal(str(client.get_price(request.symbol)['price']))
        if not current.is_finite() or current <= 0:
            raise ValueError('Market price unavailable')
        price = Decimal(str(request.limit_price)) if request.order_type == 'LIMIT' else current
        quantity = Decimal(str(request.qty))
        notional = quantity * price
        context = {} if request.reduce_only else client.get_execution_context(request.symbol)
        account = client.get_account() if request.reduce_only else context['account']
        if account.get('can_trade') is not True:
            raise ValueError('Verified Futures account unavailable')
        positions = account['positions']
        exposure = {p['symbol']:float(p['market_value']) for p in positions}
        signed = sum(Decimal(str(p['qty'])) for p in positions if p['symbol']==request.symbol)
        if any(not math.isfinite(v) or v < 0 for v in exposure.values()):
            raise ValueError('Verified Futures exposure unavailable')
        checks['exchange_filters'] = passes_exchange_filters(request,info,quantity,price,notional)
        if request.reduce_only:
            checks['reduce_only'] = ((signed>0 and request.side=='SELL') or (signed<0 and request.side=='BUY')) and quantity<=abs(signed)
        else:
            gate = CryptoRiskGate
            nav = float(account['equity'])
            pnl = float(account['daily_pnl'])
            baseline = float(account.get('baseline_equity',nav))
            available = float(account['buying_power'])
            if not all(math.isfinite(v) for v in (nav,pnl,baseline,available)) or nav<=0 or baseline<=0 or available<0:
                raise ValueError('Verified Futures account risk required')
            value = float(notional)
            score = float(context.get('score',0))
            checks['confluence'] = math.isfinite(score) and score >= .70 and context.get('is_valid') is True and context.get('side')==request.side
            checks['capital_limit'] = value <= gate.MAX_POSITION_PCT * nav
            checks['funds'] = value <= available
            checks['drawdown_circuit_breaker'] = max(0,-pnl)/min(nav,baseline) < gate.MAX_DAILY_DRAWDOWN
            checks['stop_loss'] = context.get('stop_loss') is not None and math.isfinite(float(context['stop_loss'])) and float(context['stop_loss'])>0
            checks['take_profit'] = context.get('take_profit') is not None and math.isfinite(float(context['take_profit'])) and float(context['take_profit'])>0
            # An opposite-side order must explicitly close with reduceOnly first;
            # an entry cannot silently reverse existing exposure.
            checks['entry_direction'] = signed == 0 or (signed>0 and request.side=='BUY') or (signed<0 and request.side=='SELL')
            checks['max_portfolio_exposure'] = sum(exposure.values())+value <= gate.MAX_EXPOSURE_PCT*nav
            checks['single_asset_concentration'] = exposure.get(request.symbol,0)+value <= gate.MAX_SINGLE_ASSET_PCT*nav
            checks['simultaneous_positions'] = request.symbol in exposure or len(exposure)<gate.MAX_POSITIONS
            checks['min_order_size'] = value >= gate.MIN_ORDER_VALUE_USDT
            checks['volatility_sizing'] = True  # Existing gate records regime; it does not increase size.
            checks['correlation_limit'] = all(request.symbol not in group or request.symbol in exposure
                or sum(s in exposure for s in group)<2 for group in gate.CORRELATION_GROUPS.values())
        approved = all(checks.values())
        return {'approved':approved,'checks':checks,'reason':'Approved' if approved else 'Failed: '+', '.join(k for k,v in checks.items() if not v),
                'market':'futures','testnet':True,'symbol':request.symbol,'side':request.side,
                'quantity':str(quantity),'price':str(price),'market_price':str(current),'notional':str(notional),
                'order_type':request.order_type,'reduce_only':request.reduce_only,
                'risk_coverage':account.get('coverage'),'coverage_started_at':account.get('coverage_started_at'),'_reservation_account':account}
    except Exception as exc:
        return {'approved':False,'checks':checks,'reason':str(exc),'market':'futures','testnet':True}
