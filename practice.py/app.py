import sqlite3
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

# 1. Page Configuration
st.set_page_config(
    page_title="VISTA AI - ANPR Control Center",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Enable Auto-Refresh (Every 3 seconds)
st_autorefresh(interval=3000, key="datarefresh")

# 2. Database Connection Handling
DB_PATH = Path(__file__).parent / "traffic.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Ensure tables exist
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS vehicle_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    plate_number TEXT
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS accident_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    location TEXT,
    severity TEXT,
    status TEXT
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE,
    reason TEXT,
    added_at TEXT
)
"""
)
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS dismissed_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER UNIQUE
)
"""
)
conn.commit()
conn.close()

# 3. Fixed Camera Node Coordinates
CAMERA_NODES = {
    "Cam_1_MainGate": {
        "coords": [17.3910, 78.4890],
        "location": "Main Gate Junction (Koti)",
    },
    "Cam_2_Junction": {
        "coords": [17.3875, 78.4925],
        "location": "Central Circle Signal (Narayanguda)",
    },
    "Cam_3_Canteen": {
        "coords": [17.3850, 78.4960],
        "location": "North Gate Signal (Barkatpura)",
    },
}

# 4. Sidebar: Police Hotlist Portal
st.sidebar.title("🚨 Police Hotlist Portal")
st.sidebar.markdown(
    "Register high-priority or stolen vehicle license plates for real-time surveillance alerts."
)

with st.sidebar.form("watchlist_form", clear_on_submit=True):
    new_plate = st.text_input("Vehicle Plate Number (e.g., TS09AB1234)").upper().strip()
    reason = st.selectbox(
        "Flag Reason",
        ["Stolen Vehicle", "Traffic Offender", "Criminal Suspect", "Expired Registration"],
    )
    submit_btn = st.form_submit_button("Add to Hotlist")

    if submit_btn and new_plate:
        c_wl = get_db_connection()
        cur_wl = c_wl.cursor()
        try:
            import time

            cur_wl.execute(
                "INSERT INTO watchlist (plate_number, reason, added_at) VALUES (?, ?, ?)",
                (new_plate, reason, time.strftime("%Y-%m-%d %H:%M:%S")),
            )
            c_wl.commit()
            st.sidebar.success(f"Registered `{new_plate}` to Police Hotlist!")
        except sqlite3.IntegrityError:
            st.sidebar.warning(f"Plate `{new_plate}` is already on the Hotlist.")
        finally:
            c_wl.close()

# Display active hotlist
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Active Hotlist Registry")
c_wl_read = get_db_connection()
watchlist_df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY id DESC", c_wl_read)
c_wl_read.close()

if not watchlist_df.empty:
    st.sidebar.dataframe(
        watchlist_df[["plate_number", "reason"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.sidebar.info("No active plates on the hotlist.")

# 5. Load Real-Time Data
conn = get_db_connection()
df = pd.read_sql_query("SELECT * FROM vehicle_logs ORDER BY id DESC", conn)
accident_df = pd.read_sql_query(
    "SELECT * FROM accident_alerts WHERE status != 'RESOLVED' ORDER BY id DESC", conn
)
acc_history_df = pd.read_sql_query("SELECT * FROM accident_alerts ORDER BY id DESC", conn)
dismissed_df = pd.read_sql_query("SELECT * FROM dismissed_alerts", conn)

# Join logs with watchlist to identify hotlist detections
# Join logs with watchlist to identify hotlist detections
watchlist_matches = pd.DataFrame()
if not watchlist_df.empty and not df.empty:
    # Retain the vehicle_logs ID as log_id explicitly
    df_temp = df.copy().rename(columns={"id": "log_id"})
    watchlist_matches = df_temp.merge(watchlist_df, on="plate_number", how="inner")

conn.close()

# Filter out dismissed hotlist alerts
active_watchlist_alerts = pd.DataFrame()
if not watchlist_matches.empty:
    if not dismissed_df.empty:
        active_watchlist_alerts = watchlist_matches[
            ~watchlist_matches["id"].isin(dismissed_df["log_id"])
        ]
    else:
        active_watchlist_alerts = watchlist_matches.copy()

# 6. Header Dashboard
st.title("🛡️ VISTA AI: Traffic Surveillance & Emergency Control Center")
st.markdown(
    "Real-time Automated License Plate Recognition (ANPR), Collision Alert System, and Dynamic Vehicle Trajectory Tracking."
)

# 🚑 ACCIDENT BANNERS FOR ALL ACTIVE CAMERA NODES
crash_cams = []
if not accident_df.empty:
    for idx, crash_row in accident_df.iterrows():
        c_cam = crash_row["camera_id"]
        c_loc = crash_row["location"]
        c_time = crash_row["timestamp"]
        c_id = int(crash_row["id"])
        crash_cams.append(c_cam)

        col_acc1, col_acc2 = st.columns([0.75, 0.25])
        with col_acc1:
            st.error(f"""
                ### 🚨 CRITICAL INCIDENT DETECTED: COLLISION REPORTED
                * **Camera Node:** `{c_cam}` ({c_loc})
                * **Timestamp:** `{c_time}`
                * **Status:** Emergency Services Dispatched.
            """)
        with col_acc2:
            st.write("")
            st.write("")
            if st.toggle("Mark Incident Resolved", key=f"toggle_acc_{c_id}"):
                c_res = get_db_connection()
                cur_res = c_res.cursor()
                cur_res.execute(
                    "UPDATE accident_alerts SET status = 'RESOLVED' WHERE id = ?", (c_id,)
                )
                c_res.commit()
                c_res.close()
                st.rerun()

# ⚠️ POLICE HOTLIST ALERT BANNERS
if not active_watchlist_alerts.empty:
    for idx, w_row in active_watchlist_alerts.head(3).iterrows():
        col_w1, col_w2 = st.columns([0.75, 0.25])
        log_id = int(w_row["log_id"])
        with col_w1:
            st.warning(f"""
                ### ⚠️ POLICE HOTLIST VEHICLE DETECTED
                * **Target Vehicle Plate:** `{w_row['plate_number']}`
                * **Offense / Flag Reason:** {w_row['reason']}
                * **Spotted at Node:** `{w_row['camera_id']}` at `{w_row['timestamp']}`
            """)
        with col_w2:
            st.write("")
            st.write("")
            if st.toggle("Dismiss Watchlist Alert", key=f"toggle_wl_{log_id}"):
                c_dis = get_db_connection()
                cur_dis = c_dis.cursor()
                cur_dis.execute(
                    "INSERT OR IGNORE INTO dismissed_alerts (log_id) VALUES (?)", (log_id,)
                )
                c_dis.commit()
                c_dis.close()
                st.rerun()

st.markdown("---")

# 7. Metrics Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Vehicles Logged", len(df))
m2.metric("Active Camera Feeds", f"{len(CAMERA_NODES)} Live")
m3.metric("Critical Collisions", len(accident_df), delta_color="inverse")
m4.metric("Hotlist Hits", len(watchlist_matches))

# 8. Navigation Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🗺️ Live Trajectory Map",
        "📋 Live Vehicle Feed",
        "🔍 Target Vehicle Search",
        "🚨 Collision History",
        "⚠️ Watchlist History",
    ]
)

# TAB 1: LIVE MAP WITH DYNAMIC ROUTE RECONSTRUCTION
with tab1:
    st.subheader("Real-Time Camera Node Map & Trajectory Route Reconstruction")

    search_plate = st.text_input(
        "🔎 Enter Plate Number to Track Dynamic Route (e.g., WILDFILMS):", key="map_search"
    ).upper().strip()

    m = folium.Map(location=[17.3890, 78.4910], zoom_start=14, tiles="OpenStreetMap")

    # 1. Plot Camera Nodes
    for cam_id, data in CAMERA_NODES.items():
        loc_title = data["location"]
        if cam_id in crash_cams:
            icon = folium.Icon(color="red", icon="plus", prefix="fa")
        elif (
            not active_watchlist_alerts.empty
            and cam_id == active_watchlist_alerts.iloc[0]["camera_id"]
        ):
            icon = folium.Icon(color="orange", icon="warning-sign")
        else:
            icon = folium.Icon(color="blue", icon="camera")

        folium.Marker(
            location=data["coords"],
            tooltip=f"<b>{cam_id}</b><br>{loc_title}",
            icon=icon,
        ).add_to(m)

    # 2. DYNAMIC TRAJECTORY ROUTE GENERATION
    target_plate_to_track = search_plate if search_plate else ""

    if not target_plate_to_track and not active_watchlist_alerts.empty:
        target_plate_to_track = active_watchlist_alerts.iloc[0]["plate_number"]

    if target_plate_to_track and not df.empty:
        target_hits = df[
            df["plate_number"]
            .astype(str)
            .str.contains(target_plate_to_track, case=False, na=False)
        ].sort_values(by="id", ascending=True)

        if not target_hits.empty:
            dynamic_coords = []
            route_summary = []

            for _, row in target_hits.iterrows():
                cid = row["camera_id"]
                t_stamp = row.get("timestamp", "N/A")
                if cid in CAMERA_NODES:
                    coord = CAMERA_NODES[cid]["coords"]
                    if not dynamic_coords or dynamic_coords[-1] != coord:
                        dynamic_coords.append(coord)
                        route_summary.append(f"{cid} ({t_stamp})")

            if len(dynamic_coords) > 1:
                folium.PolyLine(
                    locations=dynamic_coords,
                    color="#FF0000",
                    weight=8,
                    opacity=0.9,
                    tooltip=f"Live Route: {target_plate_to_track}",
                ).add_to(m)
                st.success(
                    f"📌 **Dynamic Trajectory Active:** Target `{target_plate_to_track}` tracked across sequence: "
                    + " ➔ ".join(route_summary)
                )
            elif len(dynamic_coords) == 1:
                st.info(
                    f"📍 **Target Stationed:** Target `{target_plate_to_track}` detected at node `{target_hits.iloc[0]['camera_id']}`"
                )
    else:
        base_coords = [data["coords"] for data in CAMERA_NODES.values()]
        folium.PolyLine(
            locations=base_coords,
            color="#6E7681",
            weight=3,
            opacity=0.5,
            dash_array="5, 10",
        ).add_to(m)

    st_folium(m, width=1200, height=520, returned_objects=[])

# TAB 2: LIVE VEHICLE FEED
with tab2:
    st.subheader("Real-Time Vehicle Recognition Logs")
    if not df.empty:
        st.dataframe(
            df[["id", "timestamp", "camera_id", "plate_number"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No vehicles logged in `traffic.db` yet.")

# TAB 3: TARGET VEHICLE SEARCH ENGINE
with tab3:
    st.subheader("🔍 Target Vehicle Audit Trail Search Engine")
    query_plate = st.text_input(
        "Enter full or partial license plate number (e.g., TS09, WILDFILMS):", key="search_engine_input"
    ).upper().strip()

    if query_plate and not df.empty:
        search_results = df[
            df["plate_number"].astype(str).str.contains(query_plate, case=False, na=False)
        ]
        if not search_results.empty:
            st.success(f"Found {len(search_results)} detection record(s) matching '{query_plate}'.")
            st.dataframe(
                search_results[["id", "timestamp", "camera_id", "plate_number"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(f"No records in database matching '{query_plate}'.")
    elif df.empty:
        st.info("Vehicle log database is currently empty.")
    else:
        st.info("Enter a plate number above to query the complete database audit trail.")

# TAB 4: COLLISION HISTORY
with tab4:
    st.subheader("Incident & Collision Audit History")
    if not acc_history_df.empty:
        st.dataframe(
            acc_history_df[["id", "timestamp", "camera_id", "location", "severity", "status"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No recorded collision incidents.")

# TAB 5: WATCHLIST HISTORY
with tab5:
    st.subheader("Watchlist Detections Log")
    if not watchlist_matches.empty:
        st.dataframe(
            watchlist_matches[["timestamp", "camera_id", "plate_number", "reason"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No hotlist vehicles detected.")