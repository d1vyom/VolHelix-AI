"""Controlled runtime regressions; no trading loop or external I/O."""
import asyncio
import threading
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend.main import fastapi_app


def test_constructor_has_no_guardian_thread():
    from backend.engine.auto_trader import auto_trader
    assert auto_trader._guardian_thread is None


def test_shutdown_joins_guardian_and_scanner(monkeypatch):
    import backend.engine.auto_trader as module
    trader=module.auto_trader
    finished=[]
    def loop(event,name):
        event.wait(2)
        finished.append(name)
    trader._guardian_thread=threading.Thread(target=loop,args=(trader._guardian_stop_event,'guardian'))
    trader._worker_thread=threading.Thread(target=loop,args=(trader._stop_event,'scanner'))
    trader._guardian_thread.start();trader._worker_thread.start();trader.is_running=True
    trader.shutdown()
    assert sorted(finished)==['guardian','scanner']
    assert not trader._guardian_thread.is_alive() and not trader._worker_thread.is_alive()


def test_lifespan_shutdown_runs_even_when_broadcaster_cleanup_fails(monkeypatch):
    import backend.main as main
    stopped=[]
    monkeypatch.setattr(main.auto_trader,'ensure_guardian_running',lambda:None)
    monkeypatch.setattr(main.auto_trader,'shutdown',lambda:stopped.append('trader'))
    monkeypatch.setattr(main,'stop_broadcasters',AsyncMock(side_effect=RuntimeError('controlled outage')))
    monkeypatch.setattr(main,'stop_hubs',AsyncMock(side_effect=lambda:stopped.append('hubs')))
    with TestClient(fastapi_app):
        pass
    assert set(stopped)=={'trader','hubs'}


def test_logger_has_no_network_sink(monkeypatch):
    import backend.utils.logger as module
    sinks=[]
    monkeypatch.setattr(module.logger,'add',lambda sink,**kw:sinks.append(sink))
    monkeypatch.setattr(module.logger,'remove',lambda:None)
    module.setup_logger()
    assert all(not callable(sink) for sink in sinks)


def test_history_audit_and_caches_keep_recent_bounded_entries(exchange_fixture):
    import backend.mcp.client as client_module
    import backend.api.routes as routes
    from backend.store.portfolio_store import portfolio_store
    from backend.models.market import Regime
    for i in range(1100):
        client_module._set_client_cache(f'quote_{i}',i)
        routes._set_cached(f'bars_{i}',i)
        exchange_fixture._log_call('read',{'i':i},{},datetime.now())
        portfolio_store.update_from_exchange({'equity':i,'buying_power':0},[],Regime.NORMAL)
    assert len(client_module._CLIENT_CACHE)<=1000 and len(routes._CACHE)<=1000
    assert len(exchange_fixture.call_logs)<=1000 and exchange_fixture.mcp_logs is exchange_fixture.call_logs
    assert len(portfolio_store.snapshot_history)<=1000
    assert portfolio_store.snapshot_history[-1].equity==1099


@pytest.mark.parametrize('path',['/api/exchange/quote','/api/alpaca/quote','/api/exchange/account','/api/alpaca/account'])
def test_legacy_read_failure_has_no_invented_financial_success(path,monkeypatch):
    import backend.api.routes as routes
    c=SimpleNamespace(get_24hr_ticker=Mock(side_effect=TimeoutError()),get_account=Mock(side_effect=TimeoutError()))
    monkeypatch.setattr(routes,'_get_binance_client',lambda:c)
    response=TestClient(fastapi_app).get(path)
    assert response.status_code==503


def test_legacy_quote_does_not_invent_bid_or_spread(monkeypatch):
    import backend.api.routes as routes
    c=SimpleNamespace(get_24hr_ticker=lambda s:{'last_price':.00001234,'bid':0,'ask':0})
    monkeypatch.setattr(routes,'_get_binance_client',lambda:c)
    response=TestClient(fastapi_app).get('/api/exchange/quote').json()
    assert response['last']==.00001234
    assert response['bid'] is None and response['ask'] is None and response['spread'] is None


def test_slow_legacy_quote_does_not_block_health(monkeypatch):
    import httpx
    import backend.api.routes as routes
    entered=threading.Event(); release=threading.Event()
    def ticker(symbol):
        entered.set();release.wait(2)
        return {'last_price':100,'bid':99,'ask':101}
    monkeypatch.setattr(routes,'_get_binance_client',lambda:SimpleNamespace(get_24hr_ticker=ticker))
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fastapi_app),base_url='http://test') as client:
            pending=asyncio.create_task(client.get('/api/exchange/quote'))
            try:
                assert await asyncio.to_thread(entered.wait,1)
                response=await asyncio.wait_for(client.get('/api/health'),.5)
                assert response.status_code==200
            finally:
                release.set();await pending
    asyncio.run(scenario())

def test_portfolio_does_not_report_seed_difference_as_trade_profit():
    from backend.store.portfolio_store import portfolio_store
    from backend.models.market import Regime
    portfolio_store.update_from_exchange({'equity':12000,'buying_power':12000},[],Regime.NORMAL)
    snapshot=portfolio_store.get_snapshot()
    assert snapshot.total_pnl is None and snapshot.total_pnl_pct is None
    assert snapshot.daily_pnl is None and snapshot.daily_risk_available is False

def test_cors_allows_local_frontend_but_not_arbitrary_credentials():
    client=TestClient(fastapi_app)
    allowed=client.options('/api/health',headers={'origin':'http://localhost:3000','access-control-request-method':'GET'})
    denied=client.options('/api/health',headers={'origin':'https://unrelated.example','access-control-request-method':'GET'})
    assert allowed.headers.get('access-control-allow-origin')=='http://localhost:3000'
    assert denied.status_code==400 and 'access-control-allow-origin' not in denied.headers

def test_trading_notifications_use_bounded_owned_loop_tasks(monkeypatch):
    import backend.engine.auto_trader as module
    from backend.api.websocket import sio
    trader=module.auto_trader
    async def scenario():
        trader.bind_event_loop(asyncio.get_running_loop())
        waiting=asyncio.Event()
        async def emit(*args,**kwargs):
            await waiting.wait()
        monkeypatch.setattr(sio,'emit',emit)
        for i in range(100):
            trader._emit_fill_event(str(i),'SOLUSDT',100,'confirmed fill')
        await asyncio.sleep(.01)
        assert 0<len(trader._event_tasks)<=32
        await trader.stop_events()
        assert not trader._event_tasks
    asyncio.run(scenario())


def test_stop_events_waits_for_notification_async_finally():
    from backend.engine.auto_trader import auto_trader
    async def scenario():
        trader=auto_trader
        trader.bind_event_loop(asyncio.get_running_loop())
        entered=asyncio.Event(); cleaning=asyncio.Event(); release=asyncio.Event(); cleaned=asyncio.Event()
        async def notification():
            try:
                entered.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()
                cleaned.set()
        trader._schedule_event(notification)
        await asyncio.wait_for(entered.wait(),1)
        stopping=asyncio.create_task(trader.stop_events())
        await asyncio.wait_for(cleaning.wait(),1)
        try:
            done,_=await asyncio.wait({stopping},timeout=.05)
            assert not done, 'shutdown returned before actual notification cleanup'
        finally:
            release.set()
            await stopping
            await asyncio.wait_for(cleaned.wait(),1)
        assert cleaned.is_set()
    asyncio.run(scenario())


def test_notification_admission_racing_shutdown_does_not_leak_slots_or_start_work():
    from backend.engine.auto_trader import auto_trader
    async def scenario():
        trader=auto_trader
        loop=asyncio.get_running_loop()
        started=[]
        async def notification():
            started.append(True)
            await asyncio.Event().wait()
        trader.bind_event_loop(loop)
        # Exercise cross-thread admissions immediately followed by loop-owned shutdown.
        await asyncio.to_thread(lambda: [trader._schedule_event(notification) for _ in range(100)])
        await trader.stop_events()
        started.clear()
        trader._schedule_event(notification)
        await asyncio.sleep(0)
        assert not started
        # Every accepted slot must be reusable after a new lifespan binding.
        trader.bind_event_loop(loop)
        for _ in range(100):
            trader._schedule_event(notification)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(started)==32
        await trader.stop_events()
    asyncio.run(scenario())

def test_missing_daily_pnl_model_cannot_claim_risk_data_available():
    from backend.models.portfolio import PortfolioSnapshot
    snapshot=PortfolioSnapshot()
    assert snapshot.daily_risk_available is False


def test_account_failure_preserves_last_observation_as_unavailable():
    from backend.store.portfolio_store import portfolio_store
    from backend.models.market import Regime
    assert portfolio_store.get_snapshot().account_available is False
    portfolio_store.update_from_exchange({'equity':12000,'buying_power':10000},[],Regime.NORMAL)
    assert portfolio_store.get_snapshot().account_available is True
    portfolio_store.update_from_exchange({'error':'down'},[],Regime.NORMAL)
    snapshot=portfolio_store.get_snapshot()
    assert snapshot.equity==12000 and snapshot.account_available is False
