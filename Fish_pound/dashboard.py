
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from flask import Flask, request, jsonify
import threading
import json
from collections import deque
from datetime import datetime
import socket
import random

# ==========================================
# FLASK SERVER TO RECEIVE DATA FROM BOAT
# ==========================================
app = Flask(__name__)
data_buffer = deque(maxlen=120)  # Store last 120 readings (2 minutes)
current_mode = "idle"  # idle, collection, ai
current_pound_id = ""
current_fish_type = ""
predicted_fish = ""
prediction_confidence = 0

@app.route('/api/data', methods=['POST'])
def receive_data():
    """Receive sensor data from boat"""
    global current_mode, current_pound_id, current_fish_type
    
    try:
        data = request.json
        data['received_at'] = datetime.now().isoformat()
        
        # Add mode-specific metadata
        data['mode'] = current_mode
        
        if current_mode == "collection":
            data['pound_id'] = current_pound_id
            data['fish_type'] = current_fish_type
            data['is_training_data'] = True
        elif current_mode == "ai":
            data['pound_id'] = current_pound_id
            data['predicted_fish'] = predicted_fish
            data['confidence'] = prediction_confidence
            data['is_ai_prediction'] = True
        
        data_buffer.append(data)
        print(f"✅ [{current_mode.upper()}] Received: {data.get('ph', 0)}")
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """Set current mode from boat joystick"""
    global current_mode, current_pound_id, current_fish_type, data_buffer
    
    try:
        mode_data = request.json
        new_mode = mode_data.get('mode', 'idle')
        
        if new_mode == "collection":
            current_mode = "collection"
            # Clear buffer for new collection session
            data_buffer.clear()
            print("🎯 DATA COLLECTION MODE ACTIVATED")
            
        elif new_mode == "ai":
            current_mode = "ai"
            data_buffer.clear()
            print("🤖 AI PREDICTION MODE ACTIVATED")
            
        elif new_mode == "stop":
            current_mode = "idle"
            print("⏹️ Collection stopped")
            
        return jsonify({"status": "success", "mode": current_mode}), 200
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/api/pound_id', methods=['POST'])
def set_pound_id():
    """Set pound ID from dashboard"""
    global current_pound_id
    data = request.json
    current_pound_id = data.get('pound_id', '')
    return jsonify({"status": "success"}), 200

@app.route('/api/fish_type', methods=['POST'])
def set_fish_type():
    """Set fish type from dashboard (collection mode only)"""
    global current_fish_type
    data = request.json
    current_fish_type = data.get('fish_type', '')
    return jsonify({"status": "success"}), 200

@app.route('/api/prediction', methods=['POST'])
def set_prediction():
    """Receive AI prediction from boat"""
    global predicted_fish, prediction_confidence
    data = request.json
    predicted_fish = data.get('fish', '')
    prediction_confidence = data.get('confidence', 0)
    return jsonify({"status": "success"}), 200

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current status for dashboard"""
    return jsonify({
        'mode': current_mode,
        'pound_id': current_pound_id,
        'fish_type': current_fish_type,
        'predicted_fish': predicted_fish,
        'confidence': prediction_confidence,
        'samples': len(data_buffer)
    })

def get_local_ip():
    """Get local IP address"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def run_flask():
    """Run Flask server"""
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

# Start Flask server
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ==========================================
# STREAMLIT DASHBOARD
# ==========================================
st.set_page_config(
    page_title="AI Boat Dashboard",
    page_icon="🚤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .mode-collection {
        background-color: #d4edda;
        color: #155724;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #28a745;
        margin-bottom: 20px;
    }
    .mode-ai {
        background-color: #cce5ff;
        color: #004085;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #007bff;
        margin-bottom: 20px;
    }
    .mode-idle {
        background-color: #f8f9fa;
        color: #6c757d;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #6c757d;
        margin-bottom: 20px;
    }
    .prediction-card {
        background-color: #e8f5e9;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin: 10px 0;
    }
    .stButton button {
        width: 100%;
    }
    .input-disabled {
        opacity: 0.5;
        pointer-events: none;
    }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🚤 AI Boat Monitoring Dashboard")
st.markdown("---")

# Get local IP
local_ip = get_local_ip()

# ==========================================
# SIDEBAR - Status & Controls
# ==========================================
with st.sidebar:
    st.header("📡 Connection")
    st.success(f"✅ Server Running")
    st.info(f"📱 Boat sends data to: **{local_ip}:5000**")
    
    st.markdown("---")
    
    # Mode display
    st.header("🎮 Current Mode")
    if current_mode == "collection":
        st.markdown('<div class="mode-collection">🟢 DATA COLLECTION MODE<br>Entering training data</div>', unsafe_allow_html=True)
    elif current_mode == "ai":
        st.markdown('<div class="mode-ai">🔵 AI PREDICTION MODE<br>ML model active</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="mode-idle">⚪ IDLE<br>Press START or SELECT on joystick</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Statistics
    st.header("📊 Statistics")
    st.metric("Total Samples", len(data_buffer))
    if len(data_buffer) > 0:
        progress = len(data_buffer)
        st.progress(progress / 120)
        st.caption(f"Progress: {progress}/120 samples (2 minutes)")
    
    st.markdown("---")
    
    # Manual controls (for testing)
    st.header("🛠️ Manual Controls")
    if st.button("🟢 Force Collection Mode"):
        current_mode = "collection"
        data_buffer.clear()
        st.rerun()
    if st.button("🔵 Force AI Mode"):
        current_mode = "ai"
        data_buffer.clear()
        st.rerun()
    if st.button("⏹️ Force Stop"):
        current_mode = "idle"
        st.rerun()

# ==========================================
# MAIN CONTENT - Mode Specific UI
# ==========================================

# Pound ID input (common for both modes)
st.subheader("📍 Pond/Location Information")
pound_id = st.text_input("Pound ID / Location Name", value=current_pound_id, 
                          placeholder="Enter Pound ID (e.g., Pond_A, North_Pond)")
if pound_id != current_pound_id:
    current_pound_id = pound_id
    # Send to server (optional)

st.markdown("---")

# Mode-specific UI
if current_mode == "collection":
    st.markdown("### 🟢 DATA COLLECTION MODE")
    st.markdown("Enter the actual fish species in this pond for training data:")
    
    fish_types = ["Tilapia", "Catfish", "Carp", "Trout", "Bass", "Salmon", "Perch", "Other"]
    selected_fish = st.selectbox("Actual Fish Species in Pond:", fish_types)
    
    if selected_fish != current_fish_type:
        current_fish_type = selected_fish
    
    st.info(f"📝 Training data will be saved with labels: Pound ID = '{current_pound_id}', Fish = '{current_fish_type}'")
    
    # Show collection indicator
    if len(data_buffer) > 0:
        st.success(f"🎯 COLLECTING DATA - {len(data_buffer)}/120 samples")

elif current_mode == "ai":
    st.markdown("### 🤖 AI PREDICTION MODE")
    st.markdown("AI model is predicting fish species from sensor data:")
    
    # Create prediction card if we have predictions
    if predicted_fish and prediction_confidence > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"""
            <div class="prediction-card">
                <h3>🐟 Predicted Fish</h3>
                <h1 style="font-size: 48px;">{predicted_fish}</h1>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="prediction-card">
                <h3>📊 Confidence</h3>
                <h1 style="font-size: 48px;">{prediction_confidence:.1f}%</h1>
                <progress value="{prediction_confidence}" max="100" style="width: 100%"></progress>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("🤖 Waiting for AI predictions... Data collection in progress")
    
    if len(data_buffer) > 0:
        st.success(f"🤖 AI ANALYZING - {len(data_buffer)}/120 samples")

else:  # idle mode
    st.markdown("### ⚪ IDLE MODE")
    st.info("Press **START** button on joystick for Data Collection Mode")
    st.info("Press **SELECT** button on joystick for AI Prediction Mode")

st.markdown("---")

# ==========================================
# REAL-TIME SENSOR DATA DISPLAY
# ==========================================

if len(data_buffer) > 0:
    # Current readings
    st.subheader("📈 Current Sensor Readings")
    latest = data_buffer[-1]
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🧪 pH Level", f"{latest.get('ph', 0):.2f}")
    with col2:
        st.metric("💧 Turbidity", f"{latest.get('turbidity', 0):.1f} NTU")
    with col3:
        st.metric("⚡ TDS", f"{latest.get('tds', 0):.0f} ppm")
    with col4:
        st.metric("🌡️ Temperature", f"{latest.get('temperature', 0):.1f}°C")
    
    # Water quality indicator
    ph = latest.get('ph', 7)
    turb = latest.get('turbidity', 0)
    wqi = 100 - (turb * 2) - abs(7 - ph) * 10
    wqi = max(0, min(100, wqi))
    
    if wqi >= 70:
        st.success(f"💯 Water Quality Index: {wqi:.0f}% - Good")
    elif wqi >= 40:
        st.warning(f"⚠️ Water Quality Index: {wqi:.0f}% - Moderate")
    else:
        st.error(f"❌ Water Quality Index: {wqi:.0f}% - Poor")
    
    st.markdown("---")
    
    # Charts
    st.subheader("📊 Sensor Data Visualization")
    
    if len(data_buffer) > 1:
        df = pd.DataFrame(list(data_buffer))
        
        # Create subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('pH Level (6.5-8.5 Normal)', 'Turbidity (NTU)',
                           'TDS (ppm)', 'Temperature (°C)'),
            vertical_spacing=0.15,
            horizontal_spacing=0.1
        )
        
        # pH Chart
        fig.add_trace(
            go.Scatter(x=df.index, y=df['ph'],
                      mode='lines+markers', name='pH',
                      line=dict(color='#00ff00', width=2)),
            row=1, col=1
        )
        fig.add_hline(y=7, line_dash="dash", line_color="gray", row=1, col=1)
        fig.add_hrect(y0=6.5, y1=8.5, line_width=0, fillcolor="green", opacity=0.1, row=1, col=1)
        
        # Turbidity Chart
        fig.add_trace(
            go.Scatter(x=df.index, y=df['turbidity'],
                      mode='lines+markers', name='Turbidity',
                      line=dict(color='#ff6600', width=2)),
            row=1, col=2
        )
        
        # TDS Chart
        fig.add_trace(
            go.Scatter(x=df.index, y=df['tds'],
                      mode='lines+markers', name='TDS',
                      line=dict(color='#ff0000', width=2)),
            row=2, col=1
        )
        
        # Temperature Chart
        fig.add_trace(
            go.Scatter(x=df.index, y=df['temperature'],
                      mode='lines+markers', name='Temperature',
                      line=dict(color='#0066ff', width=2)),
            row=2, col=2
        )
        
        fig.update_layout(height=600, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
        
        # Raw data table
        with st.expander("📋 View Raw Data"):
            display_df = df.copy()
            if 'received_at' in display_df.columns:
                display_df['time'] = pd.to_datetime(display_df['received_at']).dt.strftime('%H:%M:%S')
            
            # Show mode-specific columns
            if current_mode == "collection":
                columns = ['time', 'ph', 'turbidity', 'tds', 'temperature', 'pound_id', 'fish_type']
            else:
                columns = ['time', 'ph', 'turbidity', 'tds', 'temperature', 'pound_id', 'predicted_fish', 'confidence']
            
            available_cols = [col for col in columns if col in display_df.columns]
            st.dataframe(display_df[available_cols].tail(20), use_container_width=True)
            
            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="💾 Download CSV",
                data=csv,
                file_name=f"boat_data_{current_mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

else:
    st.info("🎮 Press START (Collection Mode) or SELECT (AI Mode) on joystick to begin data collection")
    
    # Instructions
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        ### 🟢 Data Collection Mode (START Button)
        - Enter actual fish species
        - Collects training data
        - Saves labeled data for ML training
        """)
    
    with col2:
        st.markdown("""
        ### 🔵 AI Prediction Mode (SELECT Button)
        - AI predicts fish species
        - Real-time analysis
        - Uses trained ML model
        """)

# Auto-refresh
import time
time.sleep(2)
st.rerun()
