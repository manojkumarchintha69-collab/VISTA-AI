import sqlite3
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

# 1. Page Configuration
st.set_page_config(
    page_title="VISTA AI - BEL ANPR Control Center",
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
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS e_challans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challan_no TEXT UNIQUE,
    plate_number TEXT,
    violation_type TEXT,
    fine_amount INTEGER,
    camera_id TEXT,
    timestamp TEXT,
    status TEXT
)
"""
)
conn.commit()
conn.close()

# 3. Fixed Camera Node Coordinates & Specs
CAMERA_NODES = {
    "Cam_1_MainGate": {
        "coords": [17.3910, 78.4890],
        "location": "Main Gate Junction (Koti)",
        "resolution": "1080p Full HD",
        "fps": "30 FPS",
        "model": "Hikvision DS-2CD2T87G2-L",
    },
    "Cam_2_Junction": {
        "coords": [17.3875, 78.4925],
        "location": "Central Circle Signal (Narayanguda)",
        "resolution": "4K Ultra HD",
        "fps": "60 FPS",
        "model": "Dahua IPC-HFW5842E-ZE",
    },
    "Cam_3_Canteen": {
        "coords": [17.3850, 78.4960],
        "location": "North Gate Signal (Barkatpura)",
        "resolution": "1080p Full HD",
        "fps": "30 FPS",
        "model": "Bosch DINION IP starlight 8000",
    },
}

# Fine Structure for All 6 Target Violations
FINE_AMOUNTS = {
    "Wrong-Route / One-Way Driving": 2000,
    "Red Light Signal Jumping": 1500,
    "Triple Riding": 1000,
    "No Helmet Riding": 500,
    "Stolen / Hotlist Vehicle": 2500,
    "Stop-Line Encroachment": 500,
}

# 4. Sidebar: Police Hotlist Portal & Active Registry
st.sidebar.title("🚨 Police Hotlist Portal")

with st.sidebar.form("watchlist_form", clear_on_submit=True):
    new_plate = st.text_input("Enter Flagged Plate No:").upper().strip()
    reason = st.text_input("Reason / Case Ref:")
    submit_btn = st.form_submit_button("Add to Watchlist")

    if submit_btn and new_plate:
        c_wl = get_db_connection()
        cur_wl = c_wl.cursor()
        try:
            import time

            cur_wl.execute(
                "INSERT INTO watchlist (plate_number, reason, added_at) VALUES (?, ?, ?)",
                (
                    new_plate,
                    reason if reason else "Flagged Vehicle",
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            c_wl.commit()
            st.sidebar.success(f"Registered `{new_plate}` to Watchlist!")
        except sqlite3.IntegrityError:
            st.sidebar.warning(f"Plate `{new_plate}` is already registered.")
        finally:
            c_wl.close()

# Load Real-Time Data
conn = get_db_connection()
df = pd.read_sql_query("SELECT * FROM vehicle_logs ORDER BY id DESC", conn)
accident_df = pd.read_sql_query(
    "SELECT * FROM accident_alerts WHERE status != 'RESOLVED' ORDER BY id DESC", conn
)
acc_history_df = pd.read_sql_query("SELECT * FROM accident_alerts ORDER BY id DESC", conn)
acc_resolved_df = pd.read_sql_query(
    "SELECT * FROM accident_alerts WHERE status = 'RESOLVED' ORDER BY id DESC", conn
)
watchlist_df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY id DESC", conn)
dismissed_df = pd.read_sql_query("SELECT log_id FROM dismissed_alerts", conn)

dismissed_ids = (
    set(dismissed_df["log_id"].astype(int).tolist()) if not dismissed_df.empty else set()
)

# Join logs with watchlist
watchlist_matches = pd.DataFrame()
if not watchlist_df.empty and not df.empty:
    df_temp = df.copy().rename(columns={"id": "log_id"})
    watchlist_matches = df_temp.merge(watchlist_df, on="plate_number", how="inner")

conn.close()

# Filter active vs dismissed watchlist matches
active_watchlist_alerts = pd.DataFrame()
dismissed_watchlist_matches = pd.DataFrame()

if not watchlist_matches.empty:
    active_watchlist_alerts = watchlist_matches[
        ~watchlist_matches["log_id"].astype(int).isin(dismissed_ids)
    ]
    dismissed_watchlist_matches = watchlist_matches[
        watchlist_matches["log_id"].astype(int).isin(dismissed_ids)
    ]

# Sidebar Active Hotlist Registry Table
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Active Hotlist Registry")
if not watchlist_df.empty:
    st.sidebar.dataframe(
        watchlist_df[["plate_number", "reason"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.sidebar.info("No active plates registered on the hotlist.")

# 5. Main Header
st.title("🚨 VISTA AI — City-Wide ANPR & Trajectory Engine")
st.markdown("##### Vision Intelligence For Smart Traffic Analytics")

# 🚑 ACCIDENT BANNERS
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

# 6. Metrics Row
m1, m2, m3, m4 = st.columns(4)
m1.metric("Active Nodes", f"{len(CAMERA_NODES)} Units", "↑ Operational")
m2.metric("Total System Hits", len(df), "↑ Live SQLite Feed")
m3.metric("Critical Collisions", len(accident_df), delta_color="inverse")
m4.metric("Hotlist Hits", len(watchlist_matches), "↑ Matches Logged")

# 7. Navigation Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "🗺️ Live Trajectory Map",
        "📊 Database Analysis",
        "📷 Camera Specifications",
        "🚨 Collision History",
        "⚠️ Watchlist History",
        "📜 E-Challan Generator",
    ]
)

# TAB 1: LIVE TRAJECTORY MAP
with tab1:
    st.subheader("Real-Time Camera Node Map & Trajectory Route Reconstruction")

    search_plate = (
        st.text_input(
            "🔎 Enter Plate Number to Track Dynamic Route (e.g., WILDFILMS):", key="map_search"
        )
        .upper()
        .strip()
    )

    m = folium.Map(location=[17.3890, 78.4910], zoom_start=14, tiles="OpenStreetMap")

    # Plot Camera Nodes
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

    # Dynamic Trajectory Line Logic
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

# TAB 2: DATABASE ANALYSIS
with tab2:
    st.subheader("📊 Comprehensive Vehicle Log Audit & Analytics")
    if not df.empty:
        col_db1, col_db2 = st.columns([0.6, 0.4])
        with col_db1:
            st.markdown("##### 📋 Complete Vehicle Log Table")
            st.dataframe(
                df[["id", "timestamp", "camera_id", "plate_number"]],
                use_container_width=True,
                hide_index=True,
            )
        with col_db2:
            st.markdown("##### 📈 Camera Detections Breakdown")
            cam_counts = df["camera_id"].value_counts().reset_index()
            cam_counts.columns = ["Camera Node", "Detections"]
            st.bar_chart(data=cam_counts.set_index("Camera Node"))
    else:
        st.info("No logs present in database.")

# TAB 3: CAMERA SPECIFICATIONS
with tab3:
    st.subheader("📷 Deployed Camera Hardware & Node Specifications")
    cam_spec_list = []
    for cid, spec in CAMERA_NODES.items():
        cam_spec_list.append(
            {
                "Camera ID": cid,
                "Location": spec["location"],
                "Hardware Model": spec["model"],
                "Video Stream Resolution": spec["resolution"],
                "Frame Rate": spec["fps"],
                "GPS Coordinates": f"{spec['coords'][0]}, {spec['coords'][1]}",
            }
        )
    st.dataframe(pd.DataFrame(cam_spec_list), use_container_width=True, hide_index=True)

# TAB 4: COLLISION HISTORY WITH ACTIVE / RESOLVED SUB-TABS
with tab4:
    st.subheader("🚨 Incident & Collision Audit History")
    acc_sub1, acc_sub2 = st.tabs(["🔴 Active Incidents", "✅ Completed / Resolved History"])

    with acc_sub1:
        if not accident_df.empty:
            st.dataframe(
                accident_df[["id", "timestamp", "camera_id", "location", "severity", "status"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No active unresolved collision incidents.")

    with acc_sub2:
        if not acc_resolved_df.empty:
            st.dataframe(
                acc_resolved_df[["id", "timestamp", "camera_id", "location", "severity", "status"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No resolved collision history found.")

# TAB 5: WATCHLIST HISTORY WITH ACTIVE / COMPLETED SUB-TABS
with tab5:
    st.subheader("⚠️ Watchlist Detections Audit Log")
    wl_sub1, wl_sub2 = st.tabs(["🟡 Active Watchlist Alerts", "✅ Completed / Dismissed History"])

    with wl_sub1:
        if not active_watchlist_alerts.empty:
            st.dataframe(
                active_watchlist_alerts[["log_id", "timestamp", "camera_id", "plate_number", "reason"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No active undismissed hotlist alerts.")

    with wl_sub2:
        if not dismissed_watchlist_matches.empty:
            st.dataframe(
                dismissed_watchlist_matches[["log_id", "timestamp", "camera_id", "plate_number", "reason"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No completed or dismissed watchlist history found.")

# TAB 6: 6-VIOLATION AUTOMATED E-CHALLAN GENERATOR
with tab6:
    st.subheader("📜 E-Challan System — Target Traffic Violation Portal")

    col_ch1, col_ch2 = st.columns([0.45, 0.55])

    with col_ch1:
        st.markdown("##### 📝 Issue Traffic Violation E-Challan")

        if not df.empty:
            available_plates = df["plate_number"].unique().tolist()
            selected_plate = st.selectbox("Select Target Vehicle Plate:", available_plates)

            # Fetch latest log entry for this vehicle
            plate_record = df[df["plate_number"] == selected_plate].iloc[0]

            # Auto-suggest Hotlist offense if the vehicle is on the Police Watchlist
            is_hotlist = not watchlist_matches.empty and selected_plate in watchlist_matches["plate_number"].values
            default_index = 4 if is_hotlist else 0

            selected_violation = st.selectbox(
                "Select Verified Violation Category:",
                [
                    "Wrong-Route / One-Way Driving",
                    "Red Light Signal Jumping",
                    "Triple Riding",
                    "No Helmet Riding",
                    "Stolen / Hotlist Vehicle",
                    "Stop-Line Encroachment",
                ],
                index=default_index
            )

            calculated_fine = FINE_AMOUNTS[selected_violation]
            
            if is_hotlist and selected_violation == "Stolen / Hotlist Vehicle":
                st.warning("⚠️ **POLICE WATCHLIST MATCH:** Vehicle flagged in Police Hotlist Registry.")
            
            st.error(f"💵 **Applicable Penalty Fine:** ₹{calculated_fine}")

            if st.button("🚨 Issue Official E-Challan Ticket", use_container_width=True):
                import random
                challan_num = f"TS-CHALLAN-{random.randint(100000, 999999)}"

                c_ch = get_db_connection()
                cur_ch = c_ch.cursor()
                try:
                    cur_ch.execute(
                        """
                        INSERT INTO e_challans (challan_no, plate_number, violation_type, fine_amount, camera_id, timestamp, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            challan_num,
                            selected_plate,
                            selected_violation,
                            calculated_fine,
                            plate_record["camera_id"],
                            plate_record["timestamp"],
                            "UNPAID",
                        ),
                    )
                    c_ch.commit()
                    st.success(f"✅ Issued E-Challan `{challan_num}` for Vehicle `{selected_plate}`!")
                except sqlite3.IntegrityError:
                    st.warning("A ticket with this reference ID already exists.")
                finally:
                    c_ch.close()
                st.rerun()
        else:
            st.info("No vehicle logs present in database to issue tickets.")

    with col_ch2:
        st.markdown("##### 📋 Issued E-Challans Registry")
        conn_ch = get_db_connection()
        challans_df = pd.read_sql_query("SELECT * FROM e_challans ORDER BY id DESC", conn_ch)
        conn_ch.close()

        if not challans_df.empty:
            st.dataframe(
                challans_df[
                    [
                        "challan_no",
                        "plate_number",
                        "violation_type",
                        "fine_amount",
                        "camera_id",
                        "status",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No e-challans issued yet.")