"""USD-M perpetuals: production data, separate demo execution, no account mutations."""
import hashlib
import math
import uuid
from binance.client import Client as BinanceSDKClient
from backend.config import settings
from backend.exchange.models import normalize_symbol_info

class FuturesClient:
    market = 'futures'

    def __init__(self):
        self.market_client = BinanceSDKClient('', '', ping=False, requests_params={'timeout':10})
        self.market_client.testnet = False
        self.trading_client = BinanceSDKClient(settings.BINANCE_FUTURES_API_KEY,
            settings.BINANCE_FUTURES_API_SECRET,testnet=True,ping=False,requests_params={'timeout':10})
        self.trading_client.FUTURES_TESTNET_URL = 'https://demo-fapi.binance.com/fapi'
        self._credentials_available = bool(settings.BINANCE_FUTURES_API_KEY and settings.BINANCE_FUTURES_API_SECRET)
        self._risk_identity = 'futures-testnet:' + hashlib.sha256(settings.BINANCE_FUTURES_API_KEY.encode()).hexdigest()

    def _require_credentials(self):
        if not self._credentials_available:
            raise ValueError('Futures demo credentials required: set BINANCE_FUTURES_API_KEY and BINANCE_FUTURES_API_SECRET')

    def validate_account_mode(self, symbol):
        self._require_credentials()
        config = self.trading_client.futures_symbol_config(symbol=symbol)
        target = next((p for p in config if p['symbol'] == symbol), None)
        if target is None or int(target['leverage']) != 1:
            raise ValueError('Set Futures symbol leverage to 1x in Binance demo before trading; no settings were changed')

    def get_price(self, symbol):
        raw = self.market_client.futures_symbol_ticker(symbol=symbol)
        price = float(raw['price'])
        if not math.isfinite(price) or price <= 0:
            raise ValueError('Production Futures price unavailable')
        return {'symbol':raw['symbol'],'price':price}

    def get_24hr_ticker(self, symbol):
        raw = self.market_client.futures_ticker(symbol=symbol)
        return {'symbol':raw['symbol'],'last_price':float(raw['lastPrice']),
                'price_change':float(raw['priceChange']),'price_change_pct':float(raw['priceChangePercent']),
                'high':float(raw['highPrice']),'low':float(raw['lowPrice']),
                'volume':float(raw['volume']),'quote_volume':float(raw['quoteVolume']),
                'open':float(raw['openPrice']),'close':float(raw['lastPrice']),'count':int(raw['count'])}

    get_ticker_24hr = get_24hr_ticker

    def get_klines(self, symbol, interval='1h', limit=100):
        raw = self.market_client.futures_klines(symbol=symbol,interval=interval,limit=min(max(limit,1),1000))
        return [dict(open_time=k[0],open=float(k[1]),high=float(k[2]),low=float(k[3]),close=float(k[4]),
                     volume=float(k[5]),close_time=k[6],quote_volume=float(k[7]),trades=int(k[8]),
                     taker_buy_base=float(k[9]),taker_buy_quote=float(k[10])) for k in raw]

    def get_order_book(self, symbol, limit=20):
        raw = self.market_client.futures_order_book(symbol=symbol,limit=limit)
        return {'symbol':symbol,'bids':[[float(p),float(q)] for p,q in raw['bids']],
                'asks':[[float(p),float(q)] for p,q in raw['asks']]}

    def _symbol_info(self, symbol, *, execution):
        client = self.trading_client if execution else self.market_client
        raw = client.futures_exchange_info()
        return normalize_symbol_info(next((s for s in raw['symbols'] if s['symbol']==symbol),None))

    def get_exchange_info(self, symbol):
        return self._symbol_info(symbol,execution=False)

    def get_execution_info(self, symbol):
        return self._symbol_info(symbol,execution=True)

    def get_account(self):
        self._require_credentials()
        if self.trading_client.futures_get_position_mode().get('dualSidePosition') is not False:
            raise ValueError('Set Futures to one-way position mode in Binance demo before trading')
        if self.trading_client.futures_get_multi_assets_mode().get('multiAssetsMargin') is not False:
            raise ValueError('Futures requires single-asset USDT margin mode in Binance demo')
        raw = self.trading_client.futures_account()
        usdt = next((a for a in raw['assets'] if a['asset']=='USDT'),None)
        if usdt is None:
            raise ValueError('Verified Futures USDT margin balance unavailable')
        positions = []
        for p in self.trading_client.futures_position_information():
            quantity = float(p['positionAmt'])
            if p['positionSide'] != 'BOTH':
                raise ValueError('Futures requires one-way positions')
            if not math.isfinite(quantity):
                raise ValueError('Invalid Futures exposure')
            if quantity:
                value = abs(quantity * float(p['markPrice']))
                if not math.isfinite(value) or value <= 0 or p.get('marginAsset','USDT') != 'USDT':
                    raise ValueError('Verified USDT Futures exposure unavailable')
                positions.append({'market':'futures','symbol':p['symbol'],'qty':quantity,
                                  'current_price':float(p['markPrice']),'market_value':value,
                                  'entry_price':float(p['entryPrice'])})
        equity, buying_power = float(usdt['marginBalance']), float(usdt['availableBalance'])
        if not math.isfinite(equity) or not math.isfinite(buying_power):
            raise ValueError('Verified Futures equity and available balance required')
        return {'market':'futures','can_trade':raw.get('canTrade') is True,'equity':equity,
                'buying_power':buying_power,'positions':positions,'balances':{}}

    def get_positions(self):
        return self.get_account()['positions']

    def get_execution_context(self, symbol):
        from backend.engine.order_flow import analyze_order_flow, evaluate_master_strategy_setup
        from backend.exchange.daily_risk import observe_equity
        from backend.store.trade_log import DB_PATH
        account = self.get_account()
        account.update(observe_equity(DB_PATH,self._risk_identity,account['equity']))
        bars = self.get_klines(symbol,interval='1h',limit=100)
        if not bars:
            return {'account':account,'score':0,'is_valid':False}
        setup = evaluate_master_strategy_setup(symbol,self.get_price(symbol)['price'],analyze_order_flow(symbol,bars))
        levels = setup.get('levels',{})
        return dict(setup,account=account,stop_loss=levels.get('stop_loss_price'),take_profit=levels.get('take_profit_price'))

    @staticmethod
    def _normalize_order(raw):
        return {'order_id':raw['orderId'],'symbol':raw['symbol'],'status':raw['status'],
                'orig_qty':raw['origQty'],'executed_qty':raw['executedQty'],
                'cummulative_quote_qty':raw.get('cumQuote',0),'client_order_id':raw.get('clientOrderId')}

    def get_order_by_client_id(self, symbol, client_order_id):
        self._require_credentials()
        return self._normalize_order(self.trading_client.futures_get_order(symbol=symbol,origClientOrderId=client_order_id))

    def get_order(self, symbol, order_id):
        self._require_credentials()
        return self._normalize_order(self.trading_client.futures_get_order(symbol=symbol,orderId=order_id))

    def get_order_fills(self, symbol: str, order_id: str) -> list[dict]:
        """Return order-specific actual Futures commissions without changing position size."""
        self._require_credentials()
        rows=self.trading_client.futures_account_trades(symbol=symbol,orderId=order_id,limit=1000)
        return [row for row in rows if str(row['orderId'])==str(order_id)]

    def get_orders(self, symbol=None, limit=50):
        self._require_credentials()
        params = {'symbol':symbol} if symbol else {}
        return [self._normalize_order(o) for o in self.trading_client.futures_get_open_orders(**params)][:min(limit,1000)]

    def cancel_order(self, symbol, order_id):
        self._require_credentials()
        return self._normalize_order(self.trading_client.futures_cancel_order(symbol=symbol,orderId=order_id))

    def place_order(self, symbol, side, order_type='MARKET', quantity=None, quote_quantity=None,
                    price=None, time_in_force='GTC', client_order_id=None, reduce_only=False):
        from backend.exchange.schemas import OrderRequest
        from backend.exchange.execution import validate_order, OrderOutcomeUnknown
        request = OrderRequest(market='futures',symbol=symbol,side=side,order_type=order_type,
                               qty=quantity,quote_quantity=quote_quantity,limit_price=price,
                               reduce_only=reduce_only,client_order_id=client_order_id)
        verdict = validate_order(request,client=self)
        if not verdict['approved']:
            raise ValueError(verdict['reason'])
        client_order_id = client_order_id or 'vh-' + uuid.uuid4().hex
        params = dict(symbol=symbol,side=request.side,type=request.order_type,quantity=str(quantity),
                      positionSide='BOTH',reduceOnly='true' if reduce_only else 'false',newClientOrderId=client_order_id,newOrderRespType='RESULT')
        if request.order_type == 'LIMIT':
            params.update(price=str(price),timeInForce=time_in_force)
        try:
            return self._normalize_order(self.trading_client.futures_create_order(**params))
        except Exception as exc:
            try:
                return self.get_order_by_client_id(symbol,client_order_id)
            except Exception:
                raise OrderOutcomeUnknown(f'UNKNOWN Futures outcome; reconcile client ID {client_order_id}') from exc
