import sqlite3
from pathlib import Path
import folium
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

# 1. Page Configuration
st.set_page_config(
    page_title="VISTA AI — BEL ANPR Control Center",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = Path(__file__).parent / "traffic.db"

# 2. Custom CSS Theme
st.markdown(
    """
    <style>
    .stApp { background-color: #0E1117; color: #E0E6ED; }
    .header-container {
        background: linear-gradient(90deg, #161B22 0%, #0D1117 100%);
        padding: 20px 25px;
        border-radius: 12px;
        border: 1px solid #30363D;
        margin-bottom: 20px;
    }
    .header-title { color: #58A6FF; font-size: 28px; font-weight: 700; margin: 0; }
    .header-subtitle { color: #8B949E; font-size: 14px; margin-top: 5px; }
    div[data-testid="stMetric"] {
        background-color: #161B22; border: 1px solid #30363D; padding: 15px 20px; border-radius: 10px;
    }
    section[data-testid="stSidebar"] { background-color: #161B22; border-right: 1px solid #30363D; }
    </style>
""",
    unsafe_allow_html=True,
)

# 3. Header Banner
st.markdown(
    """
    <div class="header-container">
        <div class="header-title">🚨 VISTA AI — City-Wide ANPR & Trajectory Engine</div>
        <div class="header-subtitle">Vision Intelligence For Smart Traffic Analytics</div>
    </div>
""",
    unsafe_allow_html=True,
)

# 4. Camera Nodes Metadata
CAMERA_NODES = {
    "Cam_1_MainGate": {"coords": [17.3850, 78.4867], "location": "Main Gate Junction (Koti)"},
    "Cam_2_Junction": {"coords": [17.3890, 78.4910], "location": "Central Circle Signal (Narayanguda)"},
    "Cam_3_Canteen": {"coords": [17.3930, 78.4960], "location": "North Gate Signal (Barkatpura)"},
}

# 5. Fetch Database Data
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS watchlist (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_number TEXT UNIQUE, reason TEXT, added_at TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS accident_alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, camera_id TEXT, location TEXT, severity TEXT, status TEXT)")
conn.commit()

try:
    df = pd.read_sql_query("SELECT * FROM vehicle_logs", conn)
except Exception:
    df = pd.DataFrame()

try:
    accident_df = pd.read_sql_query("SELECT * FROM accident_alerts WHERE status != 'RESOLVED' ORDER BY id DESC", conn)
    all_accidents_df = pd.read_sql_query("SELECT * FROM accident_alerts ORDER BY id DESC", conn)
except Exception:
    accident_df = pd.DataFrame()
    all_accidents_df = pd.DataFrame()

try:
    watchlist_df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY id DESC", conn)
except Exception:
    watchlist_df = pd.DataFrame()

conn.close()

if "dismissed_watchlist_ids" not in st.session_state:
    st.session_state["dismissed_watchlist_ids"] = []

# 6. Sidebar Controls
st.sidebar.markdown("### 🚔 Police Hotlist Portal")
with st.sidebar.form("add_watchlist_form", clear_on_submit=True):
    new_wanted_plate = st.text_input("Enter Flagged Plate No:", placeholder="e.g., WILDFILMS").strip().upper()
    flag_reason = st.text_input("Reason / Case Ref:", placeholder="e.g., Stolen Vehicle").strip()
    submit_btn = st.form_submit_button("➕ Add to Watchlist")

    if submit_btn and new_wanted_plate:
        c_insert = sqlite3.connect(DB_PATH)
        cur_ins = c_insert.cursor()
        try:
            cur_ins.execute("INSERT INTO watchlist (plate_number, reason, added_at) VALUES (?, ?, datetime('now'))", (new_wanted_plate, flag_reason if flag_reason else "Police Alert"))
            c_insert.commit()
            st.sidebar.success(f"Added {new_wanted_plate} to Watchlist!")
            st.rerun()
        except sqlite3.IntegrityError:
            st.sidebar.warning(f"{new_wanted_plate} is already in Watchlist.")
        finally:
            c_insert.close()

if not watchlist_df.empty:
    st.sidebar.markdown("**Registered Hotlist Plates:**")
    st.sidebar.dataframe(watchlist_df[["plate_number", "reason"]], width="stretch", height=130)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔍 Target Search Controls")
search_plate = st.sidebar.text_input("Search License Plate:", placeholder="e.g., 7EAL, WILDFILMS", value="").strip()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 System Database Logs")
if not df.empty:
    st.sidebar.dataframe(df[["timestamp", "camera_id", "plate_number"]].tail(10), width="stretch", height=260)

# =========================================================
# 🚑 ACCIDENT BANNERS (STATEFUL TOGGLE RESOLVE)
# =========================================================
crash_cam = None
if not accident_df.empty:
    latest_crash = accident_df.iloc[0]
    crash_cam = latest_crash["camera_id"]
    crash_loc = latest_crash["location"]
    crash_time = latest_crash["timestamp"]
    crash_id = int(latest_crash["id"])

    col_acc1, col_acc2 = st.columns([0.75, 0.25])
    with col_acc1:
        st.error(f"""
            ### 🚨 CRITICAL INCIDENT DETECTED: COLLISION REPORTED
            * **Camera Node:** `{crash_cam}` ({crash_loc})
            * **Timestamp:** `{crash_time}`
            * **Status:** Emergency Services Dispatched.
        """)
    with col_acc2:
        st.write("")
        st.write("")
        is_resolved = st.toggle("Mark Incident Resolved", key=f"toggle_acc_{crash_id}")
        if is_resolved:
            c_res = sqlite3.connect(DB_PATH)
            cur_res = c_res.cursor()
            cur_res.execute("UPDATE accident_alerts SET status = 'RESOLVED' WHERE id = ?", (crash_id,))
            c_res.commit()
            c_res.close()
            st.rerun()

# =========================================================
# 🚔 WATCHLIST BANNERS (UNIQUE PLATE GROUPING DISMISS)
# =========================================================
matched_watchlist = pd.DataFrame()
if not df.empty and not watchlist_df.empty:
    watchlist_plates = watchlist_df["plate_number"].tolist()
    # Group matches by plate number so each vehicle alerts ONCE regardless of log count
    matched_watchlist = (
        df[df["plate_number"].isin(watchlist_plates)]
        .drop_duplicates(subset=["plate_number"], keep="last")
    )

active_watchlist_matches = pd.DataFrame()
if not matched_watchlist.empty:
    active_watchlist_matches = matched_watchlist[
        ~matched_watchlist["plate_number"].isin(st.session_state["dismissed_watchlist_ids"])
    ]

if not active_watchlist_matches.empty:
    latest_w_match = active_watchlist_matches.iloc[-1]
    w_plate = latest_w_match["plate_number"]
    w_cam = latest_w_match["camera_id"]
    w_time = latest_w_match["timestamp"]

    col_w1, col_w2 = st.columns([0.75, 0.25])
    with col_w1:
        st.warning(f"""
            ### 🚨 HIGH PRIORITY ALERT: WATCHLIST MATCH
            * **Flagged Vehicle:** `{w_plate}`
            * **Detection Location:** `{w_cam}` ({CAMERA_NODES.get(w_cam, {}).get('location', 'Unknown')})
            * **Timestamp:** `{w_time}`
            * **Action Required:** Notify nearest patrol unit immediately.
        """)
    with col_w2:
        st.write("")
        st.write("")
        is_dismissed = st.toggle("Dismiss Watchlist Alert", key=f"toggle_w_{w_plate}")
        if is_dismissed:
            st.session_state["dismissed_watchlist_ids"].append(w_plate)
            st.rerun()

# 7. Search Metrics & Trajectory Mapping
matched_df = pd.DataFrame()
matched_times = {}

if search_plate and not df.empty:
    matched_df = df[df["plate_number"].astype(str).str.contains(search_plate, case=False, na=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Active Nodes", f"{len(CAMERA_NODES)} Units", "Operational")
m2.metric("Total System Hits", len(df) if not df.empty else 0, "Live SQLite Feed")
m3.metric("Target Search", search_plate.upper() if search_plate else "ALL VEHICLES")
m4.metric("Search Matches", len(matched_df) if search_plate else 0, "Target Found" if not matched_df.empty else "No Hits")

st.markdown("---")

# 🔄 Autorefresh Engine (5 seconds interval)
st_autorefresh(interval=5000, key="vista_db_refresh")

# 8. Main Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🗺️ Live Trajectory Map", "📊 Database Analysis", "📷 Camera Specifications", "🚨 Collision History", "🚔 Watchlist History"])

with tab1:
    m = folium.Map(location=[17.3890, 78.4910], zoom_start=14, tiles="OpenStreetMap")
    all_coords = [data["coords"] for data in CAMERA_NODES.values()]
    folium.PolyLine(locations=all_coords, color="#0055FF", weight=7, opacity=0.7).add_to(m)

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
            folium.PolyLine(locations=target_coords, color="#FF0000", weight=11, opacity=0.9).add_to(m)
            st.success(f"✅ Trajectory reconstructed for target: **{search_plate.upper()}**")

    for cam_id, data in CAMERA_NODES.items():
        loc_title = data["location"]
        if cam_id == crash_cam:
            icon = folium.Icon(color="darkred", icon="plus", prefix="fa")
        elif cam_id in matched_times:
            icon = folium.Icon(color="red", icon="warning-sign")
        elif not active_watchlist_matches.empty and cam_id == active_watchlist_matches.iloc[-1]["camera_id"]:
            icon = folium.Icon(color="orange", icon="warning-sign")
        else:
            icon = folium.Icon(color="blue", icon="camera")

        folium.Marker(location=data["coords"], tooltip=f"<b>{cam_id}</b><br>{loc_title}", icon=icon).add_to(m)

    st_folium(m, width=1200, height=520, returned_objects=[])

with tab2:
    st.markdown("### 📊 Database Analysis")
    if search_plate and not matched_df.empty:
        st.dataframe(matched_df, width="stretch")
    else:
        st.dataframe(df, width="stretch")

with tab3:
    st.markdown("### 📷 Registered Node Specifications")
    st.table(pd.DataFrame([{"ID": k, "Location": v["location"]} for k, v in CAMERA_NODES.items()]))

with tab4:
    st.markdown("### 🚨 All Incident & Collision History")
    st.dataframe(all_accidents_df if not all_accidents_df.empty else pd.DataFrame(), width="stretch")

with tab5:
    st.markdown("### 🚔 Watchlist & Hotlist History")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 📋 Registered Hotlist Plates")
        st.dataframe(watchlist_df if not watchlist_df.empty else pd.DataFrame(), width="stretch")
    with col2:
        st.markdown("#### 🚨 Hotlist Detection Log")
        st.dataframe(matched_watchlist[["timestamp", "camera_id", "plate_number"]] if not matched_watchlist.empty else pd.DataFrame(), width="stretch")