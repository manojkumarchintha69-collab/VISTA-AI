import os
import sqlite3
import time
import cv2
import easyocr
from ultralytics import YOLO

# 1. Setup Database and Table
conn = sqlite3.connect("traffic.db")
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
conn.commit()

# 2. Initialize Models
print("🚀 Initializing YOLOv8 and EasyOCR...")
model = YOLO("yolov8n.pt")
reader = easyocr.Reader(["en"], gpu=False)

# 3. List of split camera feeds
camera_files = [
    ("Cam_1_MainGate", "cam1.mp4"),
    ("Cam_2_Junction", "cam2.mp4"),
    ("Cam_3_Canteen", "cam3.mp4"),
]

for cam_id, video_file in camera_files:
    if not os.path.exists(video_file):
        print(
            f"⚠️ Skipping {video_file} - File not found! Make sure video clips are in this folder."
        )
        continue

    print(f"\n🎥 Processing Stream: {cam_id} ({video_file})...")
    cap = cv2.VideoCapture(video_file)
    frame_nmr = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_nmr += 1
        # Process 1 frame out of 5 for speed
        if frame_nmr % 5 != 0:
            continue

        results = model(frame, verbose=False)

        for r in results:
            for box in r.boxes:
                # Class 2 = Car, 3 = Motorcycle, 7 = Truck
                if int(box.cls[0]) in [2, 3, 7]:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    crop = frame[y1:y2, x1:x2]

                    try:
                        ocr_res = reader.readtext(crop, detail=0)
                        if ocr_res:
                            plate_text = "".join(
                                e for e in ocr_res[0] if e.isalnum()
                            ).upper()

                            if len(plate_text) >= 4:
                                current_time = time.strftime("%H:%M:%S")

                                # Insert into SQLite Database
                                cursor.execute(
                                    "INSERT INTO vehicle_logs (timestamp, camera_id, plate_number) VALUES (?, ?, ?)",
                                    (current_time, cam_id, plate_text),
                                )
                                conn.commit()
                                print(
                                    f"  [LOGGED] {cam_id} @ {current_time} ➔ Vehicle: {plate_text}"
                                )
                    except Exception:
                        pass

    cap.release()

conn.close()
print("\n✅ Detections successfully saved to 'traffic.db'!")