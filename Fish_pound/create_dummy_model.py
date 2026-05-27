cd ~/Documents/Salamat_Ali_Project_Portfolio/Fish_pound
cat > dashboard_dummy.py << 'EOF'
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta
from collections import deque
import random

# Page configuration
st.set_page_config(
    page_title="AI Boat Dashboard",
    page_icon="🚤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
    }
    .stAlert {
        margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# DUMMY DATA GENERATOR
# ==========================================
class DummyDataGenerator:
    def __init__(self):
        self.fish_species = ["Tilapia", "Catfish", "Carp", "Trout", "Bass", "Salmon", "Perch"]
        self.water_types = ["Clear", "Algae-affected", "Contaminated", "Muddy"]
        
    def generate_data_point(self):
        """Generate a realistic dummy data point"""
        
        # Generate correlated values for realism
        ph = round(random.uniform(6.5, 8.0), 2)
        turbidity = round(random.uniform(0.5, 14.0), 2)
        tds = round(ph * 50 + random.uniform(-50, 50), 0)
        temperature = round(random.uniform(20, 32), 1)
        ultrasonic = round(random.uniform(0.1, 2.5), 2)
        
        # Color values (correlated with water type)
        if turbidity < 3:
            water_type = "Clear"
            red, green, blue = random.randint(30000, 50000), random.randint(30000, 50000), random.randint(40000, 60000)
        elif turbidity < 7:
            if random.random() > 0.5:
                water_type = "Algae-affected"
                red, green, blue = random.randint(20000, 40000), random.randint(40000, 60000), random.randint(20000, 40000)
            else:
                water_type = "Contaminated"
                red, green, blue = random.randint(30000, 50000), random.randint(20000, 40000), random.randint(20000, 40000)
        else:
            water_type = "Muddy"
            red, green, blue = random.randint(40000, 60000), random.randint(30000, 50000), random.randint(20000, 40000)
        
        # Fish species based on water quality
        if water_type == "Clear":
            fish = random.choice(["Tilapia", "Trout", "Salmon"])
        elif water_type == "Algae-affected":
            fish = random.choice(["Catfish", "Carp"])
        elif water_type == "Contaminated":
            fish = random.choice(["Carp", "Bass"])
        else:
            fish = random.choice(["Catfish", "Carp"])
        
        return {
            "timestamp": datetime.now(),
            "ph": ph,
            "turbidity": turbidity,
            "tds": tds,
            "temperature": temperature,
            "ultrasonic": ultrasonic,
            "water_type": water_type,
            "fish_species": fish,
            "red": red,
            "green": green,
            "blue": blue,
            "clear": red + green + blue
        }

# Initialize session state
if 'data_buffer' not in st.session_state:
    st.session_state.data_buffer = deque(maxlen=120)
if 'is_collecting' not in st.session_state:
    st.session_state.is_collecting = False
if 'data_generator' not in st.session_state:
    st.session_state.data_generator = DummyDataGenerator()
if 'collection_start_time' not in st.session_state:
    st.session_state.collection_start_time = None

# ==========================================
# DATA COLLECTION FUNCTION
# ==========================================
def start_collection():
    st.session_state.data_buffer.clear()
    st.session_state.is_collecting = True
    st.session_state.collection_start_time = datetime.now()

def stop_collection():
    st.session_state.is_collecting = False

def generate_data():
    """Generate one data point"""
    if st.session_state.is_collecting:
        data_point = st.session_state.data_generator.generate_data_point()
        st.session_state.data_buffer.append(data_point)
        
        # Auto-stop after 2 minutes (120 points)
        if len(st.session_state.data_buffer) >= 120:
            st.session_state.is_collecting = False
            return True  # Collection complete
    return False  # Still collecting

# ==========================================
# DASHBOARD UI
# ==========================================
st.title("🚤 AI Boat Monitoring Dashboard")
st.markdown("---")

# Sidebar controls
with st.sidebar:
    st.header("🎮 Controls")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ START", use_container_width=True):
            start_collection()
            st.rerun()
    with col2:
        if st.button("⏹️ STOP", use_container_width=True):
            stop_collection()
            st.rerun()
    
    st.markdown("---")
    
    # Status display
    st.header("📡 Status")
    if st.session_state.is_collecting:
        st.success("🟢 COLLECTING DATA")
        progress = len(st.session_state.data_buffer)
        st.progress(progress / 120)
        st.caption(f"Progress: {progress}/120 samples (2 minutes)")
    else:
        if len(st.session_state.data_buffer) > 0:
            st.info("✅ Collection complete")
        else:
            st.warning("⚪ Waiting to start")
    
    st.markdown("---")
    
    # Statistics
    st.header("📊 Statistics")
    if st.session_state.data_buffer:
        st.metric("Total Samples", len(st.session_state.data_buffer))
        
        # Time elapsed
        if st.session_state.collection_start_time:
            elapsed = (datetime.now() - st.session_state.collection_start_time).seconds
            st.metric("Time Elapsed", f"{elapsed} seconds")
            st.metric("Remaining", f"{max(0, 120 - elapsed)} seconds")
    
    st.markdown("---")
    
    # Export data
    if st.session_state.data_buffer:
        if st.button("💾 Export CSV", use_container_width=True):
            df = pd.DataFrame(list(st.session_state.data_buffer))
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download",
                data=csv,
                file_name=f"boat_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    if st.button("🗑️ Clear Data", use_container_width=True):
        st.session_state.data_buffer.clear()
        st.session_state.is_collecting = False
        st.rerun()

# Main content - Current metrics
st.subheader("📈 Current Readings")

# Create 4 columns for metrics
col1, col2, col3, col4 = st.columns(4)

if st.session_state.data_buffer:
    latest = st.session_state.data_buffer[-1]
    
    with col1:
        st.metric("🐟 Fish Species", latest['fish_species'])
    with col2:
        st.metric("💧 Water Type", latest['water_type'])
    with col3:
        ph = latest['ph']
        color = "normal" if 6.5 <= ph <= 8.5 else "inverse"
        st.metric("🧪 pH Level", f"{ph:.2f}", delta=None)
    with col4:
        st.metric("🌡️ Temperature", f"{latest['temperature']:.1f}°C")
    
    # Second row of metrics
    st.markdown("---")
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        st.metric("💧 Turbidity", f"{latest['turbidity']:.1f} NTU")
    with col6:
        st.metric("⚡ TDS", f"{latest['tds']:.0f} ppm")
    with col7:
        st.metric("📡 Ultrasonic", f"{latest['ultrasonic']:.2f} m")
    with col8:
        # Water quality indicator
        wqi = 100 - (latest['turbidity'] * 2) - abs(7 - latest['ph']) * 10
        wqi = max(0, min(100, wqi))
        st.metric("💯 Water Quality", f"{wqi:.0f}%")
else:
    with col1:
        st.info("No data yet")
    with col2:
        st.info("Press START")
    with col3:
        st.info("to begin")
    with col4:
        st.info("collection")

st.markdown("---")

# Charts
st.subheader("📊 Sensor Data Visualization")

# Check if we have data
if len(st.session_state.data_buffer) > 0:
    df = pd.DataFrame(list(st.session_state.data_buffer))
    
    # Create subplots
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=('pH Level (6.5-8.5 Normal Range)',
                       'Turbidity (NTU)',
                       'TDS (ppm)',
                       'Temperature (°C)',
                       'Water Quality Index (WQI)',
                       'Data Collection Progress'),
        vertical_spacing=0.12,
        horizontal_spacing=0.1
    )
    
    # 1. pH Chart
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['ph'],
                  mode='lines+markers',
                  name='pH',
                  line=dict(color='#00ff00', width=2),
                  marker=dict(size=4)),
        row=1, col=1
    )
    # Add pH normal range indicators
    fig.add_hline(y=7, line_dash="dash", line_color="gray", row=1, col=1)
    fig.add_hrect(y0=6.5, y1=8.5, line_width=0, fillcolor="green", opacity=0.1, row=1, col=1)
    
    # 2. Turbidity Chart
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['turbidity'],
                  mode='lines+markers',
                  name='Turbidity',
                  line=dict(color='#ff6600', width=2),
                  marker=dict(size=4),
                  fill='tozeroy'),
        row=1, col=2
    )
    
    # 3. TDS Chart
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['tds'],
                  mode='lines+markers',
                  name='TDS',
                  line=dict(color='#ff0000', width=2),
                  marker=dict(size=4)),
        row=2, col=1
    )
    
    # 4. Temperature Chart
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=df['temperature'],
                  mode='lines+markers',
                  name='Temperature',
                  line=dict(color='#0066ff', width=2),
                  marker=dict(size=4),
                  fill='tozeroy'),
        row=2, col=2
    )
    
    # 5. Water Quality Index
    wqi = 100 - (df['turbidity'] * 2) - abs(7 - df['ph']) * 10
    wqi = wqi.clip(0, 100)
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=wqi,
                  mode='lines+markers',
                  name='WQI',
                  line=dict(color='#9b59b6', width=3),
                  marker=dict(size=6),
                  fill='tozeroy'),
        row=3, col=1
    )
    # Add quality thresholds
    fig.add_hline(y=80, line_dash="dash", line_color="green", row=3, col=1)
    fig.add_hline(y=60, line_dash="dash", line_color="orange", row=3, col=1)
    fig.add_hline(y=40, line_dash="dash", line_color="red", row=3, col=1)
    
    # 6. Progress indicator
    progress = list(range(1, len(df) + 1))
    fig.add_trace(
        go.Scatter(x=df['timestamp'], y=progress,
                  mode='lines',
                  name='Samples',
                  line=dict(color='#00ccff', width=3),
                  fill='tozeroy'),
        row=3, col=2
    )
    fig.add_hline(y=120, line_dash="dash", line_color="red", row=3, col=2)
    
    # Update layout
    fig.update_layout(
        height=900,
        showlegend=True,
        title_text="Real-time Sensor Data Timeline",
        title_x=0.5,
        hovermode='x unified'
    )
    
    # Update axes labels
    fig.update_xaxes(title_text="Time", row=3, col=1)
    fig.update_xaxes(title_text="Time", row=3, col=2)
    fig.update_yaxes(title_text="pH", row=1, col=1)
    fig.update_yaxes(title_text="Turbidity (NTU)", row=1, col=2)
    fig.update_yaxes(title_text="TDS (ppm)", row=2, col=1)
    fig.update_yaxes(title_text="Temperature (°C)", row=2, col=2)
    fig.update_yaxes(title_text="WQI Score", row=3, col=1)
    fig.update_yaxes(title_text="Sample Count", row=3, col=2)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Raw data table (collapsible)
    with st.expander("📋 View Raw Data Table"):
        # Format the dataframe for display
        display_df = df.copy()
        display_df['timestamp'] = display_df['timestamp'].dt.strftime('%H:%M:%S')
        display_df = display_df[['timestamp', 'fish_species', 'water_type', 'ph', 'turbidity', 'tds', 'temperature']]
        display_df.columns = ['Time', 'Fish', 'Water Type', 'pH', 'Turbidity', 'TDS', 'Temp (°C)']
        st.dataframe(display_df.tail(20), use_container_width=True)
    
    # Summary statistics
    with st.expander("📈 Summary Statistics"):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Average pH", f"{df['ph'].mean():.2f}")
            st.metric("Min pH", f"{df['ph'].min():.2f}")
            st.metric("Max pH", f"{df['ph'].max():.2f}")
        
        with col2:
            st.metric("Average Turbidity", f"{df['turbidity'].mean():.1f} NTU")
            st.metric("Min Turbidity", f"{df['turbidity'].min():.1f} NTU")
            st.metric("Max Turbidity", f"{df['turbidity'].max():.1f} NTU")
        
        with col3:
            st.metric("Average Temperature", f"{df['temperature'].mean():.1f}°C")
            st.metric("Average TDS", f"{df['tds'].mean():.0f} ppm")
            
        # Water type distribution
        st.subheader("Water Type Distribution")
        water_counts = df['water_type'].value_counts()
        st.bar_chart(water_counts)
        
        # Fish species distribution
        st.subheader("Fish Species Detected")
        fish_counts = df['fish_species'].value_counts()
        st.bar_chart(fish_counts)

else:
    st.info("🎯 Press the START button in the sidebar to begin 2-minute data collection")
    
    # Show placeholder with instructions
    col1, col2, col3 = st.columns(3)
    with col2:
        st.markdown("""
        ### How to use:
        1. Click **START** in the sidebar
        2. Watch real-time data appear
        3. Data collected for 2 minutes (120 samples)
        4. View charts and statistics
        5. Export data as CSV
        """)
        st.image("https://cdn-icons-png.flaticon.com/512/3096/3096992.png", width=150)

# Auto-refresh for real-time updates
if st.session_state.is_collecting:
    # Generate new data point
    collection_complete = generate_data()
    if collection_complete:
        st.success("✅ 2-minute data collection complete!")
        st.balloons()
    
    # Auto-refresh every 1 second
    time.sleep(1)
    st.rerun()

# Footer
st.markdown("---")
st.caption(f"🚤 AI Boat Dashboard | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
EOF

echo "✅ Created dashboard_dummy.py"