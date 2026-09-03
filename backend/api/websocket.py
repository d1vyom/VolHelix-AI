import socketio

# Async Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio)

@sio.event
async def connect(sid, environ):
    print(f"Dashboard client connected: {sid}")
    await sio.emit('status', {'status': 'LIVE'}, room=sid)

@sio.event
async def disconnect(sid):
    print(f"Dashboard client disconnected: {sid}")

async def broadcast_portfolio_update(portfolio_dict: dict):
    await sio.emit('portfolio_update', portfolio_dict)
    
async def broadcast_reasoning_event(event_type: str, message: str, agent: str):
    await sio.emit('reasoning_event', {
        'type': event_type,
        'message': message,
        'agent': agent
    })
