# face_recognizer.py
import cv2
import numpy as np
import os
from numpy.linalg import norm
import inspireface as isf
from inspireface.modules.exception import ProcessingError

# ---------------- config ----------------
BASE_FACES_DIR = os.path.join(os.path.dirname(__file__), "facesIMG")
SIMILARITY_THRESHOLD = 0.7
CAM_WIDTH, CAM_HEIGHT = 640, 480
# ----------------------------------------


def normalize(v):
    return v / (norm(v) + 1e-6)


def cosine_similarity(a, b):
    return np.dot(a, b) / ((norm(a) * norm(b)) + 1e-6)


def build_opt_flags_for_recognition():
    base = getattr(isf, "HF_ENABLE_NONE", 0)
    candidates = [
        name for name in dir(isf)
        if "HF_ENABLE" in name and (
            "REC" in name.upper()
            or "RECOG" in name.upper()
            or "FEATURE" in name.upper()
        )
    ]
    for name in candidates:
        try:
            val = getattr(isf, name)
            base |= val
        except Exception:
            pass
    return base


def get_embedding(session, image, face):
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

    if isinstance(feature, np.ndarray):
        emb = feature.astype(np.float32)
    elif isinstance(feature, (list, tuple)):
        emb = np.array(feature, dtype=np.float32)
    elif hasattr(feature, "embedding"):
        emb = np.array(feature.embedding, dtype=np.float32)
    elif hasattr(feature, "feature"):
        emb = np.array(feature.feature, dtype=np.float32)
    else:
        print(f"[WARN] Unknown feature type: {type(feature)}")
        return None

    if emb.ndim > 1:
        emb = emb.flatten()
    return normalize(emb)


def load_reference_embeddings(session, base_dir):
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


class FaceRecognizer:
    """
    ใช้คลาสนี้ใน service อื่น ๆ (เช่น Flask, FastAPI)
    """

    def __init__(self, base_faces_dir=BASE_FACES_DIR,
                 similarity_threshold=SIMILARITY_THRESHOLD):
        print("[INFO] Launch InspireFace...")
        try:
            if hasattr(isf, "launch"):
                isf.launch()
            elif hasattr(isf, "reload"):
                isf.reload()
        except Exception as e:
            print("[WARN] launch/reload error:", e)

        opt = build_opt_flags_for_recognition()
        detect_mode = getattr(isf, "HF_DETECT_MODE_ALWAYS_DETECT", 0)

        try:
            self.session = isf.InspireFaceSession(opt=opt, detect_mode=detect_mode)
        except TypeError:
            self.session = isf.InspireFaceSession(opt, detect_mode)

        if hasattr(self.session, "set_detection_confidence_threshold"):
            self.session.set_detection_confidence_threshold(0.5)

        self.base_faces_dir = base_faces_dir
        self.similarity_threshold = similarity_threshold
        self.embeddings_by_name = {}
        self.reload_database()

    def reload_database(self):
        print("[INFO] Reloading reference faces...")
        self.embeddings_by_name = load_reference_embeddings(
            self.session, self.base_faces_dir
        )
        print("[INFO] Loaded people:", list(self.embeddings_by_name.keys()))

    def process_frame(self, frame):
        """
        รับ frame (BGR) -> วาดกรอบ + label บน frame แล้วคืน
        return: frame, list[{name, score, bbox}]
        """
        faces = self.session.face_detection(frame)
        results = []

        for face in faces:
            emb = get_embedding(self.session, frame, face)
            if emb is None:
                continue

            label, similarity = best_match(
                self.embeddings_by_name, emb, self.similarity_threshold
            )

            x1, y1, x2, y2 = face.location
            color = (0, 255, 0) if label != "Unknown" else (0, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

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

            results.append(
                {
                    "name": label,
                    "score": float(similarity),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                }
            )

        return frame, results

    def add_face_image(self, person_name, frame, bbox):
        """
        เซฟภาพจาก bbox -> facesIMG/<person_name>/xxx.jpg แล้ว reload embeddings
        """
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        face_img = frame[y1:y2, x1:x2]
        if face_img.size == 0:
            return False

        person_dir = os.path.join(self.base_faces_dir, person_name)
        os.makedirs(person_dir, exist_ok=True)

        existing = [
            f for f in os.listdir(person_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
        idx = len(existing) + 1
        save_path = os.path.join(person_dir, f"{idx:03d}.jpg")
        cv2.imwrite(save_path, face_img)
        print(f"[INFO] Saved new face for {person_name} -> {save_path}")

        self.reload_database()
        return True
