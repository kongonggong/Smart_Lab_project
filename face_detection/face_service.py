import threading
import time
import cv2
import datetime
import base64
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient

# Import FaceRecognizer
from face_recognizer import FaceRecognizer, CAM_WIDTH, CAM_HEIGHT

# --- CONFIGURATION ---
MONGO_URI = "mongodb+srv://phachara5501_db_user:TFTQRvSGudsB8H9U@smartlabcluster.fma0ab6.mongodb.net/?appName=SmartLabCluster"

# ⚠️ ย้ายกลับมาใช้ Database "SmartLab" ตามที่คุณต้องการ
DB_NAME = "SmartLab" 

# ชื่อ Collection สำหรับปุ่มกด (ถ้าใน SmartLab ชื่ออื่น ให้แก้ตรงนี้)
CONTROL_COLLECTION_NAME = "OnOffStatus"

app = Flask(__name__)
CORS(app)

# --- MongoDB Setup ---
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    client.admin.command('ping')
    print(f"\n✅ [SUCCESS] เชื่อมต่อ Database หลัก: {DB_NAME}")
    
    # เช็ก Collection ให้ดูด้วย
    cols = db.list_collection_names()
    print(f"📂 Collection ที่มีใน {DB_NAME}: {cols}")
    
    # เช็กว่ามี sensor_data หรือยัง
    if 'sensor_data' in cols:
        print("   -> เจอ 'sensor_data' แล้ว (พร้อมดึง Temp/Humid)")
    else:
        print("   ⚠️ ไม่เจอ 'sensor_data' (ค่า Temp อาจไม่ขึ้น)")

except Exception as e:
    print(f"[ERROR] MongoDB Connection Failed: {e}")
    db = None

recognizer = FaceRecognizer()
last_frame = None
last_faces = []
lock = threading.Lock()
last_save_time = 0

# --- Helper: Save to Mongo ---
def save_detection(faces, frame):
    global last_save_time
    if db is None: return
    if time.time() - last_save_time < 5: return
    try:
        person_name = faces[0]["name"]
        _, buffer = cv2.imencode('.jpg', frame)
        binary_data = buffer.tobytes()
        event_doc = {
            "timestamp": datetime.datetime.utcnow(),
            "person": person_name,
            "image_jpeg": binary_data,
            "type": "detection"
        }
        db['face_events'].insert_one(event_doc)
        print(f"[LOG] Saved detection for {person_name}")
        last_save_time = time.time()
    except Exception as e:
        print(f"[ERROR] Save failed: {e}")

# --- Camera Logic ---
def open_camera():
    ip_url = "http://172.20.10.2:5000/video_raw"
    cap = cv2.VideoCapture(ip_url)
    if not cap.isOpened():
        print("[WARN] IP Camera failed, trying USB...")
        cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    return cap

def gen_frames():
    global last_frame, last_faces
    cap = open_camera()
    if cap is None:
        while True: time.sleep(1); yield (b'--frame\r\n\r\n')
    while True:
        success, frame = cap.read()
        if not success:
            cap.release(); time.sleep(1); cap = open_camera(); continue
        try:
            frame, faces = recognizer.process_frame(frame)
            if len(faces) > 0: save_detection(faces, frame)
        except: faces = []
        with lock: last_frame = frame.copy(); last_faces = faces
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret: continue
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# --- API ROUTES ---

@app.route('/')
def index(): return "Backend Running @ SmartLab DB"

@app.route('/video_feed/cam1')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/dashboard_data')
def api_dashboard_data():
    if db is None: return jsonify({"error": "No DB"}), 500
    
    # 1. ดึง Sensor จาก 'sensor_data' (ใน DB: SmartLab)
    latest_sensor = db['sensor_data'].find_one(sort=[('timestamp', -1)])
    
    temp = 0; humid = 0; flame = False
    if latest_sensor:
        temp = (latest_sensor.get('temperature') or latest_sensor.get('temp') or latest_sensor.get('t') or 0)
        humid = (latest_sensor.get('humidity') or latest_sensor.get('humid') or latest_sensor.get('h') or 0)
        flame = (latest_sensor.get('flame_detected') or latest_sensor.get('flame') or latest_sensor.get('f') or False)

    # 2. Face List
    cursor = db['face_events'].find().sort('timestamp', -1).limit(5)
    recent_faces = []
    for doc in cursor:
        img_base64 = None
        if 'image_jpeg' in doc:
            try:
                raw = doc['image_jpeg']
                img_base64 = base64.b64encode(raw).decode('utf-8') if isinstance(raw, bytes) else str(raw)
            except: pass
        recent_faces.append({
            "person": doc.get('person', "Unknown"),
            "time": str(doc.get('timestamp', "-")).split('.')[0],
            "image": img_base64
        })

    return jsonify({
        "temperature": temp, "humidity": humid, "flame": flame, "recent_faces": recent_faces
    })

@app.route('/api/control', methods=['GET', 'POST'])
def api_control():
    if db is None: return jsonify({"error": "No DB"}), 500
    
    collection = db[CONTROL_COLLECTION_NAME]
    query = {"type": "manual_control"}
    
    if request.method == 'POST':
        data = request.json
        print(f"[DEBUG] กดปุ่ม: {data} -> ลง DB: {DB_NAME}.{CONTROL_COLLECTION_NAME}")
        
        update = {
            "type": "manual_control", 
            "fan": data.get('fan', False), 
            "buzzer": data.get('buzzer', False),
            "updated_at": datetime.datetime.utcnow()
        }
        collection.update_one(query, {"$set": update}, upsert=True)
        return jsonify({"success": True})
    else:
        st = collection.find_one(query) or {}
        return jsonify({"fan": st.get('fan', False), "buzzer": st.get('buzzer', False)})

if __name__ == "__main__":
    print("--- Starting Server on Port 5001 (SmartLab DB) ---")
    app.run(host="0.0.0.0", port=5001, debug=True)