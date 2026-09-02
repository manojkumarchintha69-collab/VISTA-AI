import sqlite3
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# 1. Page Configuration
st.set_page_config(
    page_title="VISTA AI — BEL ANPR Control Center",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Custom CSS Theme (Control Center Vibe)
st.markdown("""
    <style>
    /* Main Dark Theme background */
    .stApp {
        background-color: #0E1117;
        color: #E0E6ED;
    }
    
    /* Header Container Styling */
    .header-container {
        background: linear-gradient(90deg, #161B22 0%, #0D1117 100%);
        padding: 20px 25px;
        border-radius: 12px;
        border: 1px solid #30363D;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    .header-title {
        color: #58A6FF;
        font-size: 28px;
        font-weight: 700;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .header-subtitle {
        color: #8B949E;
        font-size: 14px;
        margin-top: 5px;
    }
    
    /* Metric Cards Styling */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 15px 20px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    div[data-testid="stMetricLabel"] {
        color: #8B949E !important;
        font-size: 13px !important;
        font-weight: 600;
    }
    
    div[data-testid="stMetricValue"] {
        color: #00D2FF !important;
        font-size: 26px !important;
        font-weight: 700;
    }

    /* Sidebar Customization */
    section[data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #30363D;
    }
    
    /* Tab Navigation Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: #161B22;
        border-radius: 6px 6px 0 0;
        color: #8B949E;
        padding: 10px 20px;
        border: 1px solid #30363D;
    }

    .stTabs [aria-selected="true"] {
        background-color: #1F242C !important;
        color: #58A6FF !important;
        border-bottom: 2px solid #58A6FF !important;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Banner Header
st.markdown("""
    <div class="header-container">
        <div class="header-title">🚨 VISTA AI — City-Wide ANPR & Trajectory Engine</div>
        <div class="header-subtitle">Vision Intelligence For Smart Traffic Analytics</div>
    </div>
""", unsafe_allow_html=True)

# 4. Camera Nodes Coordinates & Metadata
CAMERA_NODES = {
    "Cam_1_MainGate": {
        "coords": [17.3850, 78.4867],
        "location": "Main Gate Junction (Koti)"
    },
    "Cam_2_Junction": {
        "coords": [17.3890, 78.4910],
        "location": "Central Circle Signal (Narayanguda)"
    },
    "Cam_3_Canteen": {
        "coords": [17.3930, 78.4960],
        "location": "North Gate Signal (Barkatpura)"
    },
}

# 5. Fetch SQLite Database Logs
conn = sqlite3.connect("traffic.db")
df = pd.read_sql_query("SELECT * FROM vehicle_logs", conn)
conn.close()

# 6. Sidebar Controls
st.sidebar.markdown("### 🔍 Target Search Controls")
search_plate = st.sidebar.text_input(
    "Search License Plate:",
    placeholder="e.g., 7EAL, JALACOM",
    value=""
).strip()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 System Database Logs")
if not df.empty:
    st.sidebar.dataframe(
        df[["timestamp", "camera_id", "plate_number"]].tail(10),
        width="stretch",
        height=280
    )

# 7. Search Processing & High-Level Metrics
matched_df = pd.DataFrame()
matched_times = {}

if search_plate:
    matched_df = df[df["plate_number"].astype(str).str.contains(search_plate, case=False, na=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Active Nodes", f"{len(CAMERA_NODES)} Units", "Operational")
m2.metric("Total System Hits", len(df) if not df.empty else 0, "Live SQLite Feed")
m3.metric("Target Search", search_plate.upper() if search_plate else "ALL VEHICLES")
m4.metric("Detections Found", len(matched_df) if search_plate else 0, "Active Trajectory" if not matched_df.empty else "No Hits")

st.markdown("---")

# 8. Main Tab Navigation
tab1, tab2, tab3 = st.tabs(["🗺️ Live Trajectory Map", "📊 Database Analysis", "📷 Camera Specifications"])

with tab1:
    # Initialize Map with Standard OpenStreetMap Tiles
    m = folium.Map(
        location=[17.3890, 78.4910],
        zoom_start=14,
        tiles="OpenStreetMap"
    )

    # Base Surveillance Corridor Line (Cyan Blue)
    all_coords = [data["coords"] for data in CAMERA_NODES.values()]
    folium.PolyLine(
        locations=all_coords,
        color="#0055FF",
        weight=7,
        opacity=0.7,
        tooltip="Monitored Surveillance Corridor",
    ).add_to(m)

    # Highlight Target Trajectory
    if not matched_df.empty:
        target_coords = []
        for _, row in matched_df.iterrows():
            cid = row["camera_id"]
            if cid in CAMERA_NODES:
                coord = CAMERA_NODES[cid]["coords"]
                matched_times[cid] = row.get("timestamp", "Detected")
                if not target_coords or target_coords[-1] != coord:
                    target_coords.append(coord)

        if len(target_coords) > 1:
            folium.PolyLine(
                locations=target_coords,
                color="#FF0000",
                weight=11,
                opacity=0.9,
                tooltip=f"Vehicle Route: {search_plate.upper()}",
            ).add_to(m)
            st.success(f"✅ Reconstructed spatio-temporal trajectory for target: **{search_plate.upper()}**")
        else:
            st.info(f"Vehicle **{search_plate.upper()}** spotted at node: **{matched_df['camera_id'].iloc[0]}**")
    elif search_plate:
        st.warning(f"No records found matching target: **{search_plate.upper()}**")

    # Render Camera Markers with Hover Cards
    for cam_id, data in CAMERA_NODES.items():
        loc_title = data["location"]
        
        if cam_id in matched_times:
            hover_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 6px; width: 180px;">
                <b style="color: #FF0055;">🚨 TARGET MATCHED</b><br>
                <b>Location:</b> {loc_title}<br>
                <b>Plate:</b> {search_plate.upper()}<br>
                <b>Time:</b> {matched_times[cam_id]}
            </div>
            """
            icon = folium.Icon(color="red", icon="warning-sign")
        else:
            hover_html = f"""
            <div style="font-family: Arial, sans-serif; padding: 6px; width: 180px;">
                <b style="color: #0055FF;">📷 NODE ACTIVE</b><br>
                <b>ID:</b> {cam_id}<br>
                <b>Location:</b> {loc_title}
            </div>
            """
            icon = folium.Icon(color="blue", icon="camera")

        folium.Marker(
            location=data["coords"],
            tooltip=hover_html,
            icon=icon,
        ).add_to(m)

    st_folium(m, width=1200, height=520)

with tab2:
    st.markdown("### 📊 Database Analysis")
    if not matched_df.empty:
        st.markdown(f"#### Filtered Results for `{search_plate.upper()}`")
        st.dataframe(matched_df, width="stretch")
    else:
        st.markdown("#### Full System Logs (`traffic.db`)")
        st.dataframe(df, width="stretch")

with tab3:
    st.markdown("### 📷 Registered Node Specifications")
    node_data = []
    for cid, data in CAMERA_NODES.items():
        node_data.append({
            "Camera Node ID": cid,
            "Signal Location": data["location"],
            "Latitude": data["coords"][0],
            "Longitude": data["coords"][1],
            "Status": "🟢 Active / Online"
        })
    st.table(pd.DataFrame(node_data))