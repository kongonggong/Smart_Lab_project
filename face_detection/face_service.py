# face_service.py
import threading
import time   
import cv2
from flask import Flask, Response, jsonify, request

from face_recognizer import FaceRecognizer, CAM_WIDTH, CAM_HEIGHT

app = Flask(__name__)
recognizer = FaceRecognizer()

# state ที่ใช้แชร์ระหว่าง thread
last_frame = None
last_faces = []
lock = threading.Lock()


def open_camera():
    """
    ใช้ logic เดิมของคุณ: ลองหลาย backend + index สำหรับ macOS
    """
    print("[INFO] Opening camera for stream...")
    cap = None
    for backend in (cv2.CAP_AVFOUNDATION, cv2.CAP_ANY):
        for idx in (0, 1, 2):
            tmp = cv2.VideoCapture(idx, backend)
            if tmp.isOpened():
                cap = tmp
                print(f"[INFO] Camera opened on index={idx}, backend={backend}")
                break
        if cap is not None:
            break

    if cap is None or not cap.isOpened():
        print("[ERROR] Cannot open camera for stream.")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    return cap


def gen_frames():
    """
    generator สำหรับ MJPEG stream
    """
    global last_frame, last_faces

    cap = open_camera()
    if cap is None:
        # ถ้าเปิดไม่ได้ ให้ raise error จะได้เห็นใน terminal ชัด ๆ
        raise RuntimeError("Cannot open camera for video_feed")

    consecutive_fail = 0
    MAX_FAIL = 20

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            consecutive_fail += 1
            print(f"[WARN] Failed to read frame (#{consecutive_fail})")
            if consecutive_fail >= MAX_FAIL:
                print("[ERROR] Too many failed reads, stop streaming")
                break
            continue

        consecutive_fail = 0

        # ให้ recognizer วาดกรอบ + แปะชื่อ
        frame, faces = recognizer.process_frame(frame)

        with lock:
            last_frame = frame.copy()
            last_faces = faces

        ret, buffer = cv2.imencode(".jpg", frame)
        if not ret:
            print("[WARN] imencode failed, skip frame")
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )

    cap.release()
    print("[INFO] gen_frames stopped")


@app.route("/video_feed/cam1")
def video_feed_cam1():
    print("[INFO] /video_feed/cam1 requested")
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )



@app.route("/api/unknown_faces", methods=["GET"])
def api_unknown_faces():
    with lock:
        unknowns = [f for f in last_faces if f["name"] == "Unknown"]
    return jsonify(unknowns)


@app.route("/api/add_face", methods=["POST"])
@app.route("/api/add_face", methods=["POST"])
def api_add_face():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    bbox = data.get("bbox")

    # จำนวนเฟรมและช่วงเวลาระหว่างเฟรม (สามารถส่งมาจาก front-end ได้ภายหลัง)
    num_frames = int(data.get("num_frames", 8))   # เก็บ 8 เฟรม
    interval = float(data.get("interval", 0.25))  # ทุก 0.25 วินาที ~ 2 วินาทีรวม

    if not name or not bbox:
        return jsonify({"ok": False, "error": "missing name or bbox"}), 400

    saved = 0
    for i in range(num_frames):
        with lock:
            frame = None if last_frame is None else last_frame.copy()

        if frame is None:
            print("[WARN] api_add_face: no frame at iteration", i)
            break

        ok = recognizer.add_face_image(name, frame, bbox, reload=False)
        if ok:
            saved += 1

        time.sleep(interval)

    # reload database ทีเดียวหลังเก็บครบ
    if saved > 0:
        recognizer.reload_database()

    return jsonify({"ok": saved > 0, "saved": saved})

    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    bbox = data.get("bbox")

    if not name or not bbox:
        return jsonify({"ok": False, "error": "missing name or bbox"}), 400

    with lock:
        frame = None if last_frame is None else last_frame.copy()

    if frame is None:
        return jsonify({"ok": False, "error": "no frame available"}), 400

    ok = recognizer.add_face_image(name, frame, bbox)
    return jsonify({"ok": ok})


if __name__ == "__main__":
    # Python service อยู่ที่ port 5001
    app.run(host="0.0.0.0", port=5001, debug=True)
