import cv2
import numpy as np
import os
from numpy.linalg import norm
import inspireface as isf
from inspireface.modules.exception import ProcessingError

# ---------------- config ----------------
BASE_FACES_DIR = "facesIMG"        # โฟลเดอร์หลัก: facesIMG/ชื่อคน/*.jpg
SIMILARITY_THRESHOLD = 0.7         # มากกว่านี้ถือว่า "คนเดียวกัน"
DETECT_EVERY_N_FRAMES = 1          # ตรวจทุก ๆ N เฟรม
CAM_WIDTH, CAM_HEIGHT = 640, 480   # ขนาดภาพจากกล้อง
# ----------------------------------------


def normalize(v):
    return v / (norm(v) + 1e-6)


def cosine_similarity(a, b):
    return np.dot(a, b) / ((norm(a) * norm(b)) + 1e-6)


def build_opt_flags_for_recognition():
    """
    เปิด flag ที่เกี่ยวกับ face recognition ให้มากที่สุดเท่าที่เวอร์ชันนี้มี
    """
    base = getattr(isf, "HF_ENABLE_NONE", 0)

    candidates = [
        name for name in dir(isf)
        if "HF_ENABLE" in name and (
            "REC" in name.upper()
            or "RECOG" in name.upper()
            or "FEATURE" in name.upper()
        )
    ]

    if not candidates:
        print("[WARN] ไม่พบ HF_ENABLE_* ที่เกี่ยวกับ recognition; ใช้ HF_ENABLE_NONE ไปก่อน")
        return base

    print("[INFO] Enable options for recognition:", candidates)
    for name in candidates:
        try:
            val = getattr(isf, name)
            base |= val
        except Exception:
            pass

    return base


def get_embedding(session, image, face):
    """
    ดึง embedding จาก InspireFace
    รองรับหลายรูปแบบผลลัพธ์:
      - numpy array
      - list/tuple
      - object ที่มี field embedding/feature
    """
    try:
        feature = session.face_feature_extract(image, face)
    except ProcessingError as e:
        print("[WARN] Face feature extraction failed:", e)
        return None
    except Exception as e:
        print("[WARN] Face feature extraction error (unexpected):", e)
        return None

    if feature is None:
        print("[WARN] feature is None")
        return None

    emb = None

    # เป็น numpy array อยู่แล้ว
    if isinstance(feature, np.ndarray):
        emb = feature.astype(np.float32)

    # เป็น list/tuple
    elif isinstance(feature, (list, tuple)):
        emb = np.array(feature, dtype=np.float32)

    # เป็น object ที่มี field embedding/feature
    elif hasattr(feature, "embedding"):
        emb = np.array(feature.embedding, dtype=np.float32)
    elif hasattr(feature, "feature"):
        emb = np.array(feature.feature, dtype=np.float32)
    else:
        print(f"[WARN] Unknown feature type: {type(feature)} (ไม่มี field embedding/feature)")
        return None

    if emb.ndim > 1:
        emb = emb.flatten()

    return normalize(emb)


def load_reference_embeddings(session, base_dir):
    """
    อ่านรูปจาก BASE_FACES_DIR/ชื่อคน/*.jpg
    แล้วสร้าง dict: { "ชื่อคน": [emb1, emb2, ...], ... }
    """
    embeddings_by_name = {}

    if not os.path.isdir(base_dir):
        print(f"[ERROR] Base faces directory not found: {base_dir}")
        return embeddings_by_name

    for person_name in os.listdir(base_dir):
        person_dir = os.path.join(base_dir, person_name)
        if not os.path.isdir(person_dir):
            continue

        print(f"[INFO] Loading faces for: {person_name}")
        embeddings_by_name[person_name] = []

        for filename in os.listdir(person_dir):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            path = os.path.join(person_dir, filename)
            img = cv2.imread(path)
            if img is None:
                print(f"  [WARN] Cannot read image: {path}")
                continue

            faces = session.face_detection(img)
            if not faces:
                print(f"  [WARN] No face detected in: {filename}")
                continue

            emb = get_embedding(session, img, faces[0])
            if emb is None:
                print(f"  [WARN] Skip image (feature extract failed): {filename}")
                continue

            embeddings_by_name[person_name].append(emb)
            print(f"  [OK] Face added from: {filename}")

        if len(embeddings_by_name[person_name]) == 0:
            print(f"  [WARN] No valid embeddings for person: {person_name}")

    return embeddings_by_name


def best_match(embeddings_by_name, emb_to_check, threshold):
    """
    หา similarity สูงสุดกับทุกคนในฐานข้อมูล
    """
    best_name = None
    best_score = -1.0

    for name, refs in embeddings_by_name.items():
        if not refs:
            continue
        score = max(cosine_similarity(ref, emb_to_check) for ref in refs)
        if score > best_score:
            best_score = score
            best_name = name

    if best_name is None or best_score < threshold:
        return "Unknown", best_score
    return best_name, best_score


def open_camera():
    """
    เปิดกล้องแบบลองหลาย index + backend สำหรับ macOS
    """
    print("[INFO] Opening camera...")
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
        print("[ERROR] Cannot open camera.")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
    return cap


def main():
    print("[INFO] Launch InspireFace...")

    # launch / reload
    try:
        if hasattr(isf, "launch"):
            ok = isf.launch()
            print("[INFO] launch() ->", ok)
        elif hasattr(isf, "reload"):
            ok = isf.reload()
            print("[INFO] reload() ->", ok)
    except Exception as e:
        print("[WARN] launch/reload error:", e)

    # opt & detect_mode
    opt = build_opt_flags_for_recognition()
    detect_mode = getattr(isf, "HF_DETECT_MODE_ALWAYS_DETECT", 0)

    # สร้าง session (รองรับทั้ง keyword / positional)
    try:
        session = isf.InspireFaceSession(opt=opt, detect_mode=detect_mode)
    except TypeError:
        session = isf.InspireFaceSession(opt, detect_mode)

    if hasattr(session, "set_detection_confidence_threshold"):
        session.set_detection_confidence_threshold(0.5)

    # ---------- โหลดฐานข้อมูลใบหน้าจากโฟลเดอร์ ----------
    print("[INFO] Loading reference faces...")
    embeddings_by_name = load_reference_embeddings(session, BASE_FACES_DIR)

    if not embeddings_by_name or all(len(v) == 0 for v in embeddings_by_name.values()):
        print("[ERROR] No reference faces / embeddings. Exiting.")
        return

    print("[INFO] Loaded people:", list(embeddings_by_name.keys()))

    # ---------- เปิดกล้อง ----------
    cap = open_camera()
    if cap is None:
        return

    frame_count = 0
    print("[INFO] Press 'e' to exit.")

    consecutive_fail = 0
    MAX_FAIL = 10

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            consecutive_fail += 1
            print(f"[WARN] Failed to read frame (#{consecutive_fail}), retrying...")
            if consecutive_fail >= MAX_FAIL:
                print("[ERROR] Too many failed reads, exiting.")
                break
            if cv2.waitKey(10) & 0xFF == ord("e"):
                break
            continue

        consecutive_fail = 0
        frame_count += 1

        # ประหยัดแรงเครื่อง: ตรวจทุก ๆ N เฟรม
        if frame_count % DETECT_EVERY_N_FRAMES != 0:
            cv2.imshow("Face Recognition - InspireFace", frame)
        if frame_count % DETECT_EVERY_N_FRAMES != 0:
            cv2.imshow("Face Recognition - InspireFace", frame)
            if cv2.waitKey(1) & 0xFF == ord("e"):
                break
            continue


        faces = session.face_detection(frame)

        for face in faces:
            emb = get_embedding(session, frame, face)
            if emb is None:
                continue

            label, similarity = best_match(embeddings_by_name, emb, SIMILARITY_THRESHOLD)

            # bounding box
            x1, y1, x2, y2 = face.location
            color = (0, 255, 0) if label != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # label + similarity
            text = f"{label} ({similarity:.2f})"
            cv2.putText(
                frame,
                text,
                (x1, max(0, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

        cv2.imshow("Face Recognition - InspireFace", frame)
        if cv2.waitKey(1) & 0xFF == ord("e"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Exited cleanly.")


if __name__ == "__main__":
    main()
