# ==========================================
# SOCKET.IO SERVER FOR DATA RELAY
# ==========================================
import socketio
import eventlet
from datetime import datetime

# Create Socket.IO server with CORS enabled
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# Store connected clients
connected_clients = set()

@sio.event
def connect(sid, environ):
    print(f"✅ Client connected: {sid}")
    connected_clients.add(sid)
    sio.emit('connection_response', {'status': 'connected', 'message': 'Connected to server'}, room=sid)

@sio.event
def disconnect(sid):
    print(f"❌ Client disconnected: {sid}")
    connected_clients.discard(sid)

@sio.event
def sensor_data(sid, data):
    """Receive sensor data from boat and broadcast to dashboard"""
    print(f"📊 Received data: {data.get('timestamp', 'no timestamp')[:19]}")
    # Add received timestamp
    data['server_timestamp'] = datetime.now().isoformat()
    # Broadcast to all clients (dashboard)
    sio.emit('sensor_data_update', data)

@sio.event
def collection_started(sid, data):
    """Notify that data collection has started"""
    print("🎯 Data collection STARTED")
    sio.emit('collection_started', {'status': 'started'})

@sio.event
def collection_stopped(sid, data):
    """Notify that data collection has stopped"""
    print("⏹️ Data collection STOPPED")
    sio.emit('collection_stopped', {'status': 'stopped'})

@sio.event
def collection_complete(sid, data):
    """Notify that 2-minute collection is complete"""
    print(f"✅ Collection complete: {data.get('total_points', 0)} points collected")
    sio.emit('collection_complete', data)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Socket.IO Server Running")
    print("📍 Port: 8501")
    print("🔗 URL: http://localhost:8501")
    print("=" * 50)
    print("Waiting for connections...")
    eventlet.wsgi.server(eventlet.listen(('', 8501)), app)