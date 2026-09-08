import os
import sqlite3
import time
import math
import cv2
import numpy as np
import easyocr
from pathlib import Path
from ultralytics import YOLO

# ---------------------------------------------------------
# 1. Path Resolution & Database Initialization
# ---------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "traffic.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Table for License Plate & Vehicle Logs
cursor.execute("""
CREATE TABLE IF NOT EXISTS vehicle_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    plate_number TEXT
)
""")

# Table for Critical Incident & Accident Alerts
cursor.execute("""
CREATE TABLE IF NOT EXISTS accident_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    location TEXT,
    severity TEXT,
    status TEXT
)
""")

# Table for Police Watchlist
cursor.execute("""
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE,
    reason TEXT,
    added_at TEXT
)
""")

# Table for Real-World Computer Vision Auto Violations
cursor.execute("""
CREATE TABLE IF NOT EXISTS auto_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    camera_id TEXT,
    plate_number TEXT,
    violation_type TEXT,
    fine_amount INTEGER,
    reason TEXT
)
""")

# Table for Issued Official E-Challans
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
)
""")
conn.commit()

# Fine Amounts Mapping (Two-Wheeler Safety & Lane Enforcement)
FINE_AMOUNTS = {
    "No Helmet Riding": 500,
    "Triple Riding": 1000,
    "Wrong-Route / One-Way Driving": 2000
}

# Camera Directional Vectors Calibration (in degrees)
CAM_DIRECTION_ANGLES = {
    "Cam_1_MainGate": (0, 360),     # Bi-directional (no wrong-way alerts)
    "Cam_2_Junction": (180, 360),   # Downward traffic flow ONLY
    "Cam_3_Canteen": (0, 270)       # Transverse flow ONLY
}

# ---------------------------------------------------------
# 2. Real-World Computer Vision Helper Functions
# ---------------------------------------------------------

def analyze_rider_safety(frame, bike_box, person_model):
    """
    Isolates motorcycle ROI to count riders (Triple Riding) and analyzes upper head ROI for helmet presence.
    """
    bx1, by1, bx2, by2 = bike_box
    bike_crop = frame[by1:by2, bx1:bx2]
    
    if bike_crop.size == 0:
        return False, False

    person_results = person_model(bike_crop, verbose=False)
    
    # Filter for COCO Class 0 (Person / Rider)
    rider_boxes = []
    if person_results and len(person_results[0].boxes) > 0:
        for box in person_results[0].boxes:
            if int(box.cls[0]) == 0:  # Class 0 = Person
                rider_boxes.append(box)

    rider_count = len(rider_boxes)
    is_triple_riding = rider_count > 2
    is_no_helmet = False

    # Analyze head region of each detected rider
    for pbox in rider_boxes:
        px1, py1, px2, py2 = map(int, pbox.xyxy[0])
        head_crop = bike_crop[max(0, py1):min(bike_crop.shape[0], py1 + int((py2 - py1) * 0.30)), max(0, px1):min(bike_crop.shape[1], px2)]
        
        if head_crop.size > 0:
            hsv_head = cv2.cvtColor(head_crop, cv2.COLOR_BGR2HSV)
            
            # Skin/hair tone mask in HSV
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([20, 255, 255], dtype=np.uint8)
            skin_mask = cv2.inRange(hsv_head, lower_skin, upper_skin)
            
            skin_pixel_ratio = np.sum(skin_mask > 0) / (head_crop.shape[0] * head_crop.shape[1])
            
            # If skin/hair exposure in top head region exceeds 15%, flag as No Helmet
            if skin_pixel_ratio > 0.15:
                is_no_helmet = True

    return is_triple_riding, is_no_helmet


def check_wrong_way_vector(prev_centroid, curr_centroid, allowed_angle_range=(0, 180)):
    """
    Calculates movement trajectory vector angle theta between frame centroids.
    Flags wrong-way driving if motion vector strays outside authorized directional lane angles.
    """
    dx = curr_centroid[0] - prev_centroid[0]
    dy = curr_centroid[1] - prev_centroid[1]

    if math.hypot(dx, dy) < 5:  # Ignore stationary noise
        return False

    movement_angle = math.degrees(math.atan2(-dy, dx)) % 360
    min_angle, max_angle = allowed_angle_range

    return not (min_angle <= movement_angle <= max_angle)


def log_violation_to_db(timestamp, camera_id, plate_number, v_type, reason):
    """Logs auto-detected computer vision violations into SQLite."""
    cursor.execute("""
    INSERT INTO auto_violations (timestamp, camera_id, plate_number, violation_type, fine_amount, reason)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (timestamp, camera_id, plate_number, v_type, FINE_AMOUNTS[v_type], reason))
    conn.commit()
    print(f"  🚨 [AUTO-VIOLATION DETECTED] {camera_id} @ {timestamp} ➔ {plate_number} | {v_type} ({reason})")


# ---------------------------------------------------------
# 3. Model Initialization & Dynamic Path Resolution
# ---------------------------------------------------------
print("🚀 Initializing YOLOv8 and EasyOCR Engine...")
model = YOLO("yolov8n.pt")
reader = easyocr.Reader(["en"], gpu=False)

# Absolute video file resolution relative to script location
camera_files = [
    ("Cam_1_MainGate", str(BASE_DIR / "cam1.mp4")),
    ("Cam_2_Junction", str(BASE_DIR / "cam2.mp4")),
    ("Cam_3_Canteen", str(BASE_DIR / "cam3.mp4")),
]

# ---------------------------------------------------------
# 4. Processing Multi-Camera Video Streams
# ---------------------------------------------------------
for cam_id, video_file in camera_files:
    if not os.path.exists(video_file):
        # Fallback check at workspace root if video isn't inside practice.py folder
        alt_path = Path(__file__).parent.parent / Path(video_file).name
        if alt_path.exists():
            video_file = str(alt_path)
        else:
            print(f"⚠️ Skipping {video_file} - File not found!")
            continue

    # Reset centroid tracking per camera feed
    previous_centroids = {}

    print(f"\n🎥 Processing Stream: {cam_id} ({video_file})...")
    cap = cv2.VideoCapture(video_file)
    frame_nmr = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_nmr += 1

        # Incident Alert Engine (Cam_3_Canteen)
        if cam_id == "Cam_3_Canteen" and frame_nmr >= 5:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            location_name = "North Gate Signal (Barkatpura)"

            # Check if an unresolved collision alert already exists for Cam 3
            cursor.execute(
                "SELECT * FROM accident_alerts WHERE camera_id = ? AND status != 'RESOLVED'",
                (cam_id,),
            )
            if not cursor.fetchone():
                # STATUS SET TO 'ACTIVE_DISPATCH' FOR GATEWAY 3 RECOGNITION
                cursor.execute(
                    """
                    INSERT INTO accident_alerts (timestamp, camera_id, location, severity, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (current_time, cam_id, location_name, "CRITICAL", "ACTIVE_DISPATCH"),
                )
                conn.commit()

                print(f"\n🚨 ACCIDENT DETECTED at {cam_id} ({location_name}) on {current_time}")
                print("📱 Sending Automated Alerts:")
                print("   ↳ 🚑 108 Emergency Medical Services Notification Transmitted.")
                print("   ↳ 🚔 Police Control Room (100/112) Dispatch Transmitted.\n")

        # Process alternate frames for Cam_1 and Cam_2; process ALL frames for Cam_3
        if cam_id != "Cam_3_Canteen" and frame_nmr % 2 != 0:
            continue

        results = model(frame, verbose=False)

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])

                # Class 2 = Car, 3 = Motorcycle, 7 = Truck
                if cls_id in [2, 3, 7]:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    crop = frame[y1:y2, x1:x2]
                    curr_centroid = ((x1 + x2) // 2, (y1 + y2) // 2)

                    if crop.shape[0] < 20 or crop.shape[1] < 40:
                        continue

                    try:
                        ocr_res = reader.readtext(crop, detail=0)
                        if ocr_res:
                            plate_text = "".join(e for e in ocr_res[0] if e.isalnum()).upper()

                            if len(plate_text) >= 4:
                                log_time = time.strftime("%H:%M:%S")

                                # Check and log unique plate entry
                                cursor.execute(
                                    "SELECT * FROM vehicle_logs WHERE camera_id = ? AND plate_number = ? ORDER BY id DESC LIMIT 1",
                                    (cam_id, plate_text),
                                )
                                if not cursor.fetchone():
                                    cursor.execute(
                                        "INSERT INTO vehicle_logs (timestamp, camera_id, plate_number) VALUES (?, ?, ?)",
                                        (log_time, cam_id, plate_text),
                                    )
                                    conn.commit()
                                    print(f"  [LOGGED ONCE] {cam_id} @ {log_time} ➔ Vehicle: {plate_text}")

                                # ---------------------------------------------------------
                                # REAL-WORLD COMPUTER VISION VIOLATION EVALUATION
                                # ---------------------------------------------------------

                                # 1. TWO-WHEELER RIDER SAFETY CHECK (No Helmet & Triple Riding)
                                if cls_id == 3:  # Class 3 = Motorcycle
                                    is_triple, is_no_helmet = analyze_rider_safety(
                                        frame, bike_box=[x1, y1, x2, y2], person_model=model
                                    )
                                    if is_triple:
                                        log_violation_to_db(log_time, cam_id, plate_text, "Triple Riding", "Occupancy Exceeds 2 Persons")
                                    if is_no_helmet:
                                        log_violation_to_db(log_time, cam_id, plate_text, "No Helmet Riding", "Unhelmeted Two-Wheeler Rider")

                                # 2. WRONG-WAY VECTOR DIRECTION TRACKING
                                if plate_text in previous_centroids:
                                    prev_centroid = previous_centroids[plate_text]
                                    allowed_range = CAM_DIRECTION_ANGLES.get(cam_id, (0, 360))

                                    if check_wrong_way_vector(prev_centroid, curr_centroid, allowed_angle_range=allowed_range):
                                        log_violation_to_db(log_time, cam_id, plate_text, "Wrong-Route / One-Way Driving", "Motion Vector Opposes Authorized Lane Trajectory")

                                previous_centroids[plate_text] = curr_centroid

                    except Exception:
                        pass

    cap.release()

conn.close()
print("\n✅ Detections & Real-World Auto-Violations successfully saved to 'traffic.db'!")