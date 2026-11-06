import asyncio
from unittest.mock import Mock
import pytest
from backend.exchange.lifecycle import position_snapshot
from backend.models.trade import TradeRecord,TradeProposal
from backend.store.trade_log import trade_log

def setup(monkeypatch,c):
    c.trading_client.get_account.return_value={'canTrade':True,'balances':[{'asset':'ADA','free':'10','locked':'0'}]}
    c.market_client.get_all_tickers.side_effect=None
    c.market_client.get_all_tickers.return_value=[{'symbol':'ADAUSDT','price':'2'}]
    c.market_client.get_exchange_info.side_effect=None
    c.market_client.get_exchange_info.return_value={'symbols':[{'symbol':'ADAUSDT','baseAsset':'ADA','quoteAsset':'USDT','status':'TRADING','isSpotTradingAllowed':True}]}
    monkeypatch.setattr('backend.exchange.registry.get_exchange_client',lambda market:c)

def test_non_watchlist_tracked_and_wallet_holdings_get_verified_value(monkeypatch,exchange_fixture):
    c=exchange_fixture;setup(monkeypatch,c)
    wallet=asyncio.run(position_snapshot('spot'))
    assert wallet['available'] and len(wallet['positions'])==1
    assert wallet['positions'][0]['current_price']==2
    assert not wallet['positions'][0].get('trade_id')
    assert asyncio.run(trade_log.get_all_trades())==[]
    t=TradeRecord(trade_id='spot:ADAUSDT:1',proposal=TradeProposal(id='1',symbol='ADAUSDT',qty=10,entry_price=1),entry_price=1,current_price=1)
    asyncio.run(trade_log.save_trade(t))
    snapshot=asyncio.run(position_snapshot('spot'));p=snapshot['positions'][0]
    assert snapshot['available'] and not p['stale']
    assert p['current_price']==2 and p['unrealized_pl']==10

def test_dynamic_wallet_valuation_outage_is_unavailable(monkeypatch,exchange_fixture):
    setup(monkeypatch,exchange_fixture)
    exchange_fixture.market_client.get_all_tickers.side_effect=TimeoutError('Production unavailable')
    snapshot=asyncio.run(position_snapshot('spot'))
    assert not snapshot['available'] and snapshot['error']

def test_genuinely_empty_spot_account_needs_no_market_reads(monkeypatch,exchange_fixture):
    c=exchange_fixture;setup(monkeypatch,c);c.trading_client.get_account.return_value['balances']=[]
    c.market_client.get_all_tickers=Mock(side_effect=AssertionError('No valuation needed'))
    snapshot=asyncio.run(position_snapshot('spot'))
    assert snapshot['available'] and snapshot['positions']==[]
    c.market_client.get_all_tickers.assert_not_called()


def test_missing_eligible_price_preserves_stale_tracked_exposure(monkeypatch,exchange_fixture):
    c=exchange_fixture;setup(monkeypatch,c);c.market_client.get_all_tickers.return_value=[]
    t=TradeRecord(trade_id='spot:ADAUSDT:1',proposal=TradeProposal(id='1',symbol='ADAUSDT',qty=10,entry_price=1),entry_price=1,current_price=1)
    asyncio.run(trade_log.save_trade(t))
    snapshot=asyncio.run(position_snapshot('spot'))
    assert snapshot['available'] is False and snapshot['positions'][0]['stale']
    assert snapshot['positions'][0]['qty']==10 and snapshot['positions'][0]['current_price']==1


def test_unsupported_gift_does_not_become_tracked_position(monkeypatch,exchange_fixture):
    c=exchange_fixture;setup(monkeypatch,c)
    c.market_client.get_exchange_info.return_value['symbols'][0]['isSpotTradingAllowed']=False
    snapshot=asyncio.run(position_snapshot('spot'))
    assert snapshot['available'] and snapshot['positions']==[]
    assert asyncio.run(trade_log.get_all_trades())==[]
