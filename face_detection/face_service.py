import threading
import time
import cv2
from flask import Flask, Response, jsonify, request
from flask_cors import CORS  # <--- เพิ่มตัวนี้

from face_recognizer import FaceRecognizer, CAM_WIDTH, CAM_HEIGHT

app = Flask(__name__)
# อนุญาตให้ทุกเว็บเรียก API นี้ได้ (แก้ปัญหา blocked by CORS)
CORS(app) 

recognizer = FaceRecognizer()

# Global variables
last_frame = None
last_faces = []
lock = threading.Lock()
safety_enabled = False

def open_camera():
    print("[INFO] Attempting to open camera...")
    cap = None
    # ลองเปิดกล้อง
    for backend in (cv2.CAP_AVFOUNDATION, cv2.CAP_ANY):
        for idx in range(3):
            tmp = cv2.VideoCapture(idx, backend)
            if tmp.isOpened():
                cap = tmp
                print(f"[SUCCESS] Connected to camera index {idx}")
                break
        if cap is not None: break
    
    if cap is None:
        print("[ERROR] Could not open any camera.")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    return cap

def gen_frames():
    global last_frame, last_faces
    cap = open_camera()
    
    if cap is None:
        # ส่งภาพ Error สีดำไปแทน ถ้าเปิดกล้องไม่ได้
        while True:
            time.sleep(1)
            yield (b'--frame\r\nContent-Type: text/plain\r\n\r\nError\r\n')

    while True:
        success, frame = cap.read()
        if not success:
            cap.release()
            cap = open_camera() # ลองต่อใหม่
            if cap is None: break
            continue

        try:
            frame, faces = recognizer.process_frame(frame)
        except:
            faces = []

        with lock:
            last_frame = frame.copy()
            last_faces = faces

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret: continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

# --- Routes ---

@app.route('/')
def index():
    return "Smart Lab Backend (Port 5001) is Running."

@app.route('/video_feed/cam1')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/safety', methods=['GET', 'POST'])
def api_safety():
    global safety_enabled
    if request.method == 'POST':
        data = request.json
        safety_enabled = data.get('enabled', False)
        print(f"Safety Mode: {safety_enabled}")
    return jsonify({"enabled": safety_enabled})

@app.route('/api/cameras')
def api_cameras():
    # ส่ง Full URL กลับไปเลย เพื่อให้ Frontend ใช้ง่ายๆ
    return jsonify([
        {
            "id": "cam1", 
            "name": "Main Lab Camera", 
            "streamUrl": "http://localhost:5001/video_feed/cam1" 
        }
    ])

if __name__ == "__main__":
    # รันที่ Port 5001
    print("--- Server Starting on Port 5001 ---")
    app.run(host="0.0.0.0", port=5001, debug=True)