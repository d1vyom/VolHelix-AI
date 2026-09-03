import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.api.websocket import socket_app
from backend.store.trade_log import trade_log
from backend.store.postmortem_store import postmortem_store
from backend.scheduler import VolHelixScheduler

from backend.api.websocket import sio
import socketio

from backend.engine.auto_trader import auto_trader
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initializing Database...")
    await trade_log.init_db()
    await postmortem_store.init_db()
    auto_trader.ensure_guardian_running()
    print("Position Guardian 24/7 TP/SL Engine Active...")
    yield

fastapi_app = FastAPI(title="VolHelix AI Backend", lifespan=lifespan)

# CORS for frontend
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
fastapi_app.include_router(router)

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
