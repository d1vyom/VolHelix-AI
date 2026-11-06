from decimal import Decimal
import pytest
from backend.engine.order_flow import analyze_order_flow,calculate_master_strategy_tp_sl,evaluate_master_strategy_setup
from backend.mcp.client import BinanceClient
from backend.tests.test_futures_client import futures

def bars(price,side='BUY'):
    # Genuine OHLC inputs, scaled without mocking analysis or protection levels.
    raw=[dict(open=100,high=101,low=99,close=100,volume=10) for _ in range(20)]
    raw += [dict(open=100,high=100,low=98,close=99,volume=10),dict(open=101,high=104,low=101,close=103,volume=15),dict(open=104,high=107,low=104,close=106,volume=20),dict(open=105,high=106,low=102,close=103,volume=10),dict(open=103,high=104,low=100,close=101,volume=10)]
    if side=='SELL':
        raw=[dict(open=200-b['open'],high=200-b['low'],low=200-b['high'],close=200-b['close'],volume=b['volume']) for b in raw]
    return [{**b,**{key:b[key]*price/100 for key in ['open','high','low','close']}} for b in raw]

@pytest.mark.parametrize('price,tick',[(.001,'0.000001'),(100,'0.01')])
@pytest.mark.parametrize('side',['BUY','SELL'])
def test_real_ohlc_preserves_price_structure_and_direction(price,tick,side):
    data=bars(price,side);a=analyze_order_flow('SOLUSDT',data)
    assert a.current_price==data[-1]['close']
    assert a.order_blocks and a.fair_value_gaps
    assert all(ob.low>0 and ob.high>ob.low for ob in a.order_blocks)
    assert all(g.top>g.bottom>0 for g in a.fair_value_gaps)
    levels=calculate_master_strategy_tp_sl('SOLUSDT',price,a,trend_bias='BULLISH' if side=='BUY' else 'BEARISH',tick_size=tick)
    sl,tp=levels['stop_loss_price'],levels['take_profit_price']
    assert 0<sl<price<tp if side=='BUY' else 0<tp<price<sl
    assert Decimal(str(sl))%Decimal(tick)==0 and Decimal(str(tp))%Decimal(tick)==0
    assert levels['entry_price']==price and levels['risk_reward_ratio']>0

@pytest.mark.parametrize('price',[0,-1,float('nan'),float('inf')])
def test_missing_invalid_price_never_uses_fabricated_default(price):
    a=analyze_order_flow('SOLUSDT',[])
    with pytest.raises(ValueError,match='price'):
        calculate_master_strategy_tp_sl('SOLUSDT',price,a)

@pytest.mark.parametrize('market',['spot','futures'])
@pytest.mark.parametrize('price,tick',[(.001,'0.000001'),(100,'0.01')])
def test_actual_execution_context_uses_exchange_tick(monkeypatch,exchange_fixture,futures,market,price,tick):
    from backend.engine import order_flow
    from backend.config import settings
    monkeypatch.setattr(settings,'FLOW_CONFLUENCE_ENABLED',False)
    monkeypatch.setattr(order_flow,'analyze_order_flow',analyze_order_flow)
    monkeypatch.setattr(order_flow,'evaluate_master_strategy_setup',evaluate_master_strategy_setup)
    c=exchange_fixture if market=='spot' else futures
    if market=='spot':monkeypatch.setattr(c,'get_execution_context',BinanceClient.get_execution_context.__get__(c))
    side='BUY' if market=='spot' else 'SELL'
    data=bars(price,side)
    monkeypatch.setattr(c,'get_klines',lambda *a,**kw:data)
    monkeypatch.setattr(c,'get_price',lambda *a,**kw:{'price':price})
    info={'status':'TRADING','filters':[{'filterType':'PRICE_FILTER','tickSize':tick}]}
    monkeypatch.setattr(c,'get_execution_info',lambda symbol:info)
    result=c.get_execution_context('SOLUSDT')
    assert result['levels']['entry_price']==price
    sl,tp=result['stop_loss'],result['take_profit']
    assert 0<sl<price<tp if side=='BUY' else 0<tp<price<sl
    assert Decimal(str(sl))%Decimal(tick)==0 and Decimal(str(tp))%Decimal(tick)==0
    info['filters']=[]
    with pytest.raises(ValueError,match='tick'):c.get_execution_context('SOLUSDT')
