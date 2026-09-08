import sqlite3
import time
import random
from pathlib import Path
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_folium import st_folium

# 1. Page Configuration - Completely Remove Sidebar
st.set_page_config(
    page_title="VISTA AI - BEL ANPR Control Center",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Initialize Session States
if "splash_done" not in st.session_state:
    st.session_state["splash_done"] = False

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "user_name" not in st.session_state:
    st.session_state["user_name"] = ""

if "user_role" not in st.session_state:
    st.session_state["user_role"] = ""

if "confirm_logout" not in st.session_state:
    st.session_state["confirm_logout"] = False

if "active_gateway" not in st.session_state:
    st.session_state["active_gateway"] = None

# Authorized 6 User Credentials Registry
USER_CREDENTIALS = {
    "admin": {"password": "vista@2026", "name": "Chief Officer (HQ-01)", "role": "Super Admin"},
    "inspector_a": {"password": "cam1@junction", "name": "Inspector Rajesh (TR-101)", "role": "Traffic Inspector"},
    "inspector_b": {"password": "cam2@junction", "name": "Inspector Priya (TR-102)", "role": "Traffic Inspector"},
    "officer_main": {"password": "gate1@vista", "name": "Officer Vikram (FO-201)", "role": "Field Officer"},
    "officer_canteen": {"password": "gate2@vista", "name": "Officer Sneha (FO-202)", "role": "Field Officer"},
    "auditor_hq": {"password": "audit#990", "name": "Lead Auditor (AU-301)", "role": "System Auditor"},
}

# Custom CSS: Hide Sidebar Entirely & Style Headers
st.markdown("""
<style>
    /* Hide Streamlit Sidebar & Sidebar Collapse Controls */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    .main .block-container {
        padding-top: 1.5rem !important;
        max-width: 95% !important;
    }
    
    /* Centered Header Title Styling */
    .centered-header {
        text-align: center;
        margin-bottom: 25px;
    }
    .centered-header h1 {
        font-size: 56px !important;
        font-weight: 900;
        letter-spacing: 3px;
        color: #1E88E5;
        margin-bottom: 0px;
    }
    .centered-header p {
        font-size: 18px !important;
        font-weight: 500;
        color: #B0BEC5;
    }

    /* Splash Screen Styling */
    .splash-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        height: 70vh;
        text-align: center;
    }
    .splash-title {
        font-size: 80px !important;
        font-weight: 900;
        letter-spacing: 6px;
        color: #1E88E5;
        margin-bottom: 10px;
    }
    .splash-subtitle {
        font-size: 24px !important;
        font-weight: 600;
        color: #E0E0E0;
        animation: fadeIn 1.5s ease-in-out;
    }

    /* Login Portal Styling */
    .login-header {
        text-align: center;
        font-size: 48px;
        font-weight: 900;
        color: #1E88E5;
        margin-bottom: 5px;
        letter-spacing: 2px;
    }
    .login-subtitle {
        text-align: center;
        font-size: 18px;
        font-weight: 500;
        color: #B0BEC5;
        margin-bottom: 25px;
    }
    @keyframes fadeIn {
        0% { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }
</style>
""", unsafe_allow_html=True)

# Enable Auto-Refresh (Every 3 seconds after login)
if st.session_state["authenticated"]:
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
cursor.execute("""
CREATE TABLE IF NOT EXISTS vehicle_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    plate_number TEXT
)""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS accident_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    location TEXT,
    severity TEXT,
    status TEXT
)""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE,
    reason TEXT,
    added_at TEXT
)""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS dismissed_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id INTEGER UNIQUE
)""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS auto_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    plate_number TEXT,
    violation_type TEXT,
    fine_amount INTEGER,
    reason TEXT
)""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS e_challans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challan_no TEXT UNIQUE,
    plate_number TEXT,
    violation_type TEXT,
    fine_amount INTEGER,
    camera_id TEXT,
    timestamp TEXT,
    status TEXT
)""")
conn.commit()
conn.close()


# =========================================================
# STAGE 1 & 2: VISTA AI FULL-SCREEN SPLASH SCREEN
# =========================================================
if not st.session_state["splash_done"]:
    splash_placeholder = st.empty()

    with splash_placeholder.container():
        st.markdown(
            """
        <div class="splash-container">
            <div class="splash-title">VISTA AI</div>
            <div class="splash-subtitle">Visual Intelligent System for Traffic Analysis & Automation</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    time.sleep(3.5)
    st.session_state["splash_done"] = True
    st.rerun()

# =========================================================
# STAGE 3: MULTI-USER LOGIN PORTAL
# =========================================================
elif not st.session_state["authenticated"]:
    st.markdown('<div class="login-header">VISTA AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="login-subtitle">Visual Intelligent System for Traffic Analysis & Automation</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([0.25, 0.5, 0.25])

    with col2:
        with st.form("login_form"):
            st.subheader("Portal Login")
            username = st.text_input("Username", placeholder="Enter official ID")
            password = st.text_input(
                "Password", type="password", placeholder="Enter authorization key"
            )

            submit_button = st.form_submit_button(
                "Authenticate & Enter Portal", use_container_width=True
            )

            if submit_button:
                if (
                    username in USER_CREDENTIALS
                    and USER_CREDENTIALS[username]["password"] == password
                ):
                    user_info = USER_CREDENTIALS[username]
                    st.session_state["authenticated"] = True
                    st.session_state["user_name"] = user_info["name"]
                    st.session_state["user_role"] = user_info["role"]
                    st.session_state["confirm_logout"] = False
                    st.session_state["active_gateway"] = None

                    st.success(
                        f"✅ Authenticated as {user_info['name']} ({user_info['role']}). Loading VISTA AI Portal..."
                    )
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Authorization Key")

# =========================================================
# PROTECTED VISTA AI DASHBOARD (GATEWAY ROUTER)
# =========================================================
else:
    # Double-Verification Logout Modal Dialog
    if st.session_state["confirm_logout"]:
        @st.dialog("Confirm Logout")
        def logout_dialog():
            st.warning("⚠️ Are you sure you want to logout?")
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                if st.button("Logout", use_container_width=True, type="primary"):
                    st.session_state["authenticated"] = False
                    st.session_state["confirm_logout"] = False
                    st.session_state["active_gateway"] = None
                    st.rerun()
            with col_l2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state["confirm_logout"] = False
                    st.rerun()

        logout_dialog()

    # Fixed Camera Specs Data
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

    FINE_AMOUNTS = {
        "Wrong-Route / One-Way Driving": 2000,
        "Red Light Signal Jumping": 1500,
        "Triple Riding": 1000,
        "No Helmet Riding": 500,
        "Stolen / Hotlist Vehicle": 2500,
        "Stop-Line Encroachment": 500,
    }

    # Fetch Shared Data from SQLite
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM vehicle_logs ORDER BY id DESC", conn)
    accident_df = pd.read_sql_query("SELECT * FROM accident_alerts WHERE status != 'RESOLVED' ORDER BY id DESC", conn)
    acc_resolved_df = pd.read_sql_query("SELECT * FROM accident_alerts WHERE status = 'RESOLVED' ORDER BY id DESC", conn)
    watchlist_df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY id DESC", conn)
    dismissed_df = pd.read_sql_query("SELECT log_id FROM dismissed_alerts", conn)

    dismissed_ids = set(dismissed_df["log_id"].astype(int).tolist()) if not dismissed_df.empty else set()
    watchlist_matches = pd.DataFrame()
    if not watchlist_df.empty and not df.empty:
        df_temp = df.copy().rename(columns={"id": "log_id"})
        watchlist_matches = df_temp.merge(watchlist_df, on="plate_number", how="inner")

    conn.close()

    active_watchlist_alerts = pd.DataFrame()
    dismissed_watchlist_matches = pd.DataFrame()

    if not watchlist_matches.empty:
        active_watchlist_alerts = watchlist_matches[~watchlist_matches["log_id"].astype(int).isin(dismissed_ids)]
        dismissed_watchlist_matches = watchlist_matches[watchlist_matches["log_id"].astype(int).isin(dismissed_ids)]

    # Centered Header Title at the Top Middle
    st.markdown("""
    <div class="centered-header">
        <h1>VISTA AI</h1>
        <p>Visual Intelligent System for Traffic Analysis & Automation</p>
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # MAIN GATEWAY SELECTION MENU
    # ---------------------------------------------------------
    if st.session_state["active_gateway"] is None:
        # Top-Left Profile Controls & Logout Button
        top_col1, top_col2 = st.columns([0.4, 0.6])
        with top_col1:
            st.markdown(f"👤 **{st.session_state['user_name']}** ({st.session_state['user_role']})")
            if st.button("🚪 Logout", key="top_left_logout_btn"):
                st.session_state["confirm_logout"] = True
                st.rerun()

        st.markdown("---")
        st.markdown("### 🌐 Select Command Gateway")

        # Row 1: Gateways 1, 2, 3 (3 Columns)
        col_g1, col_g2, col_g3 = st.columns(3)

        with col_g1:
            st.info("### 🗺️ Gateway 1")
            st.markdown("**Live Mapping & Database Analysis**\n\nReal-time trajectory map & vehicle registration logs.")
            if st.button("Open Live Mapping ➔", use_container_width=True):
                st.session_state["active_gateway"] = "live_mapping"
                st.rerun()

        with col_g2:
            st.info("### 📷 Gateway 2")
            st.markdown("**Camera Specifications**\n\nHardware specifications, GPS coordinates & FPS metadata.")
            if st.button("Open Camera Specs ➔", use_container_width=True):
                st.session_state["active_gateway"] = "camera_specs"
                st.rerun()

        with col_g3:
            st.info("### 🚨 Gateway 3")
            st.markdown("**Collision History**\n\nCritical accident alerts & emergency dispatch logs.")
            if st.button("Open Collision History ➔", use_container_width=True):
                st.session_state["active_gateway"] = "collision_history"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Row 2: Gateways 4 & 5 (2 Equal-Width Columns for Balanced Grid Spacing)
        col_g4, col_g5 = st.columns(2)

        with col_g4:
            st.info("### ⚠️ Gateway 4")
            st.markdown("**Watchlist History & Police Hotlist**\n\nRegister hotlist plates, view alerts & dismissed logs.")
            if st.button("Open Watchlist Portal ➔", use_container_width=True):
                st.session_state["active_gateway"] = "watchlist_history"
                st.rerun()

        with col_g5:
            st.info("### 📜 Gateway 5")
            st.markdown("**E-Challan Portal**\n\nAI automated ticket issuance & unpaid registry.")
            if st.button("Open E-Challan Portal ➔", use_container_width=True):
                st.session_state["active_gateway"] = "echallan_portal"
                st.rerun()

    # ---------------------------------------------------------
    # GATEWAY 1: LIVE MAPPING & DATABASE ANALYSIS
    # ---------------------------------------------------------
    elif st.session_state["active_gateway"] == "live_mapping":
        if st.button("⬅️ Back to Gateways"):
            st.session_state["active_gateway"] = None
            st.rerun()

        st.subheader("🗺️ Live Trajectory Map & Route Reconstruction")

        search_plate = st.text_input("🔎 Enter Plate Number to Track Dynamic Route (e.g., WILDFILMS):", key="map_search").upper().strip()
        m = folium.Map(location=[17.3890, 78.4910], zoom_start=14, tiles="OpenStreetMap")

        # Plot Markers
        crash_cams = [r["camera_id"] for _, r in accident_df.iterrows()] if not accident_df.empty else []
        for cam_id, data in CAMERA_NODES.items():
            loc_title = data["location"]
            if cam_id in crash_cams:
                icon = folium.Icon(color="red", icon="plus", prefix="fa")
            elif not active_watchlist_alerts.empty and cam_id == active_watchlist_alerts.iloc[0]["camera_id"]:
                icon = folium.Icon(color="orange", icon="warning-sign")
            else:
                icon = folium.Icon(color="blue", icon="camera")
            folium.Marker(location=data["coords"], tooltip=f"<b>{cam_id}</b><br>{loc_title}", icon=icon).add_to(m)

        # Draw Trajectory Line
        target_plate = search_plate if search_plate else (active_watchlist_alerts.iloc[0]["plate_number"] if not active_watchlist_alerts.empty else "")
        if target_plate and not df.empty:
            target_hits = df[df["plate_number"].astype(str).str.contains(target_plate, case=False, na=False)].sort_values(by="id", ascending=True)
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
                    folium.PolyLine(locations=dynamic_coords, color="#FF0000", weight=8, opacity=0.9).add_to(m)
                    st.success(f"📌 **Dynamic Trajectory Active:** `{target_plate}` tracked across sequence: " + " ➔ ".join(route_summary))

        st_folium(m, width=1200, height=480, returned_objects=[])

        st.markdown("---")
        st.subheader("📊 Comprehensive Vehicle Log Audit & Analytics")
        if not df.empty:
            col_db1, col_db2 = st.columns([0.6, 0.4])
            with col_db1:
                st.markdown("##### 📋 Complete Vehicle Log Table")
                st.dataframe(df[["id", "timestamp", "camera_id", "plate_number"]], use_container_width=True, hide_index=True)
            with col_db2:
                st.markdown("##### 📈 Camera Detections Breakdown")
                cam_counts = df["camera_id"].value_counts().reset_index()
                cam_counts.columns = ["Camera Node", "Detections"]
                st.bar_chart(data=cam_counts.set_index("Camera Node"))

    # ---------------------------------------------------------
    # GATEWAY 2: CAMERA SPECIFICATIONS
    # ---------------------------------------------------------
    elif st.session_state["active_gateway"] == "camera_specs":
        if st.button("⬅️ Back to Gateways"):
            st.session_state["active_gateway"] = None
            st.rerun()

        st.subheader("📷 Deployed Camera Hardware & Node Specifications")
        cam_spec_list = [
            {
                "Camera ID": cid,
                "Location": spec["location"],
                "Hardware Model": spec["model"],
                "Video Stream Resolution": spec["resolution"],
                "Frame Rate": spec["fps"],
                "GPS Coordinates": f"{spec['coords'][0]}, {spec['coords'][1]}",
            }
            for cid, spec in CAMERA_NODES.items()
        ]
        st.dataframe(pd.DataFrame(cam_spec_list), use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # GATEWAY 3: COLLISION HISTORY
    # ---------------------------------------------------------
    elif st.session_state["active_gateway"] == "collision_history":
        if st.button("⬅️ Back to Gateways"):
            st.session_state["active_gateway"] = None
            st.rerun()

        st.subheader("🚨 Incident & Collision Audit History")
        acc_sub1, acc_sub2 = st.tabs(["🔴 Active Incidents", "✅ Completed / Resolved History"])
        with acc_sub1:
            if not accident_df.empty:
                st.dataframe(accident_df[["id", "timestamp", "camera_id", "location", "severity", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("No active unresolved collision incidents.")
        with acc_sub2:
            if not acc_resolved_df.empty:
                st.dataframe(acc_resolved_df[["id", "timestamp", "camera_id", "location", "severity", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("No resolved collision history found.")

    # ---------------------------------------------------------
    # GATEWAY 4: WATCHLIST HISTORY & POLICE HOTLIST PORTAL
    # ---------------------------------------------------------
    elif st.session_state["active_gateway"] == "watchlist_history":
        if st.button("⬅️ Back to Gateways"):
            st.session_state["active_gateway"] = None
            st.rerun()

        st.subheader("⚠️ Watchlist Portal & Hotlist Detections")

        col_wl1, col_wl2 = st.columns([0.4, 0.6])

        with col_wl1:
            st.markdown("##### 🚨 Register Flagged Vehicle to Hotlist")
            with st.form("watchlist_form_internal", clear_on_submit=True):
                new_plate = st.text_input("Enter Flagged Plate No:").upper().strip()
                reason = st.text_input("Reason / Case Ref:")
                submit_btn = st.form_submit_button("Add to Watchlist", use_container_width=True)

                if submit_btn and new_plate:
                    c_wl = get_db_connection()
                    cur_wl = c_wl.cursor()
                    try:
                        cur_wl.execute(
                            "INSERT INTO watchlist (plate_number, reason, added_at) VALUES (?, ?, ?)",
                            (
                                new_plate,
                                reason if reason else "Flagged Vehicle",
                                time.strftime("%Y-%m-%d %H:%M:%S"),
                            ),
                        )
                        c_wl.commit()
                        st.success(f"Registered `{new_plate}` to Watchlist!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.warning(f"Plate `{new_plate}` is already registered.")
                    finally:
                        c_wl.close()

            st.markdown("##### 📋 Active Hotlist Registry")
            if not watchlist_df.empty:
                st.dataframe(watchlist_df[["plate_number", "reason"]], use_container_width=True, hide_index=True)
            else:
                st.info("No active plates registered on the hotlist.")

        with col_wl2:
            st.markdown("##### 📈 Hotlist Detection Hits Audit Log")
            wl_sub1, wl_sub2 = st.tabs(["🟡 Active Watchlist Alerts", "✅ Completed / Dismissed History"])
            with wl_sub1:
                if not active_watchlist_alerts.empty:
                    st.dataframe(active_watchlist_alerts[["log_id", "timestamp", "camera_id", "plate_number", "reason"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No active undismissed hotlist alerts.")
            with wl_sub2:
                if not dismissed_watchlist_matches.empty:
                    st.dataframe(dismissed_watchlist_matches[["log_id", "timestamp", "camera_id", "plate_number", "reason"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No completed or dismissed watchlist history found.")

    # ---------------------------------------------------------
    # GATEWAY 5: E-CHALLAN PORTAL
    # ---------------------------------------------------------
    elif st.session_state["active_gateway"] == "echallan_portal":
        if st.button("⬅️ Back to Gateways"):
            st.session_state["active_gateway"] = None
            st.rerun()

        st.subheader("📜 AI Automated E-Challan Generation Engine")

        conn_v = get_db_connection()
        try:
            cv_violations_df = pd.read_sql_query("SELECT * FROM auto_violations ORDER BY id DESC", conn_v)
        except Exception:
            cv_violations_df = pd.DataFrame()
        conn_v.close()

        col_auto1, col_auto2 = st.columns([0.5, 0.5])
        with col_auto1:
            st.markdown("##### ⚡ Auto-Detected Traffic Violations Feed")
            if not cv_violations_df.empty:
                st.dataframe(cv_violations_df[["plate_number", "violation_type", "fine_amount", "camera_id", "reason"]], use_container_width=True, hide_index=True)
                if st.button("⚡ Auto-Generate & Issue All Pending Challans", use_container_width=True):
                    c_auto = get_db_connection()
                    cur_auto = c_auto.cursor()
                    issued_count = 0
                    for _, v_item in cv_violations_df.iterrows():
                        c_num = f"TS-CHALLAN-{random.randint(100000, 999999)}"
                        try:
                            cur_auto.execute(
                                """
                                INSERT INTO e_challans (challan_no, plate_number, violation_type, fine_amount, camera_id, timestamp, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (c_num, v_item["plate_number"], v_item["violation_type"], int(v_item["fine_amount"]), v_item["camera_id"], v_item["timestamp"], "UNPAID")
                            )
                            issued_count += 1
                        except sqlite3.IntegrityError:
                            pass
                    c_auto.commit()
                    c_auto.close()
                    st.success(f"✅ Successfully issued {issued_count} automated E-Challans!")
                    st.rerun()
            else:
                st.info("No active automated violations detected in current database feed.")

        with col_auto2:
            st.markdown("##### 📋 Official Issued E-Challans Registry")
            conn_ch = get_db_connection()
            challans_df = pd.read_sql_query("SELECT * FROM e_challans ORDER BY id DESC", conn_ch)
            conn_ch.close()
            if not challans_df.empty:
                st.dataframe(challans_df[["challan_no", "plate_number", "violation_type", "fine_amount", "camera_id", "status"]], use_container_width=True, hide_index=True)
            else:
                st.info("No automated e-challans issued yet.")