// web_node/server.mjs
import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

const FACE_SERVICE = "http://localhost:5001";

// กล้อง (ชี้ไปที่ face_service)
const cameras = [
  {
    id: "cam1",
    name: "Lab Camera",
    streamUrl: `${FACE_SERVICE}/video_feed/cam1`,
  },
];

let safetyEnabled = false;

// หน้า main
app.get("/", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

// list กล้อง
app.get("/api/cameras", (_req, res) => {
  res.json(cameras);
});

// safety mode
app.get("/api/safety", (_req, res) => {
  res.json({ enabled: safetyEnabled });
});

app.post("/api/safety", (req, res) => {
  safetyEnabled = !!req.body.enabled;
  res.json({ enabled: safetyEnabled });
});

// proxy ไปหา Python /api/unknown_faces
app.get("/api/unknown_faces", async (_req, res) => {
  try {
    const r = await fetch(`${FACE_SERVICE}/api/unknown_faces`);
    const data = await r.json();
    res.json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "face service unreachable" });
  }
});

// proxy /api/add_face
app.post("/api/add_face", async (req, res) => {
  try {
    const r = await fetch(`${FACE_SERVICE}/api/add_face`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
    });
    const data = await r.json();
    res.status(r.status).json(data);
  } catch (err) {
    console.error(err);
    res.status(500).json({ ok: false, error: "face service unreachable" });
  }
});

const PORT = 3000;
app.listen(PORT, () => {
  console.log(`Dashboard running at http://localhost:${PORT}`);
});
