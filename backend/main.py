import asyncio
from backend.config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.api.flow_routes import router as flow_router
from backend.api.websocket import socket_app, stop_broadcasters
from backend.store.trade_log import trade_log
from backend.store.postmortem_store import postmortem_store
# VolHelixScheduler is imported but deliberately not started here.
# TradingOrchestrator is driven exclusively through the auto_trader loop and Position Guardian.
from backend.scheduler import VolHelixScheduler

from backend.api.websocket import sio
import socketio

from backend.engine.auto_trader import auto_trader
from contextlib import asynccontextmanager

from backend.marketdata.hub import hub, stop_hubs

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    await trade_log.init_db()
    await postmortem_store.init_db()
    auto_trader.bind_event_loop(asyncio.get_running_loop())
    auto_trader.ensure_guardian_running()
    print("Position Guardian 24/7 TP/SL Engine Active...")
    
    try:
        await hub.start()
    except Exception as e:
        print(f"Failed to start MarketDataHub: {e}")
        
    try:
        yield
    finally:
        await asyncio.to_thread(auto_trader.shutdown)
        for cleanup in (auto_trader.stop_events,stop_broadcasters,stop_hubs):
            try:
                await cleanup()
            except Exception as e:
                print(f"Failed runtime cleanup: {e}")

fastapi_app = FastAPI(title="VolHelix AI Backend", lifespan=lifespan)

# CORS for frontend
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
fastapi_app.include_router(router)
fastapi_app.include_router(flow_router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
