// pages/api/sensor.js
import clientPromise from "../../lib/mongodb";

export default async function handler(req, res) {
    if (req.method !== "POST") {
        return res.status(405).json({ ok: false, error: "Method Not Allowed" });
    }

    try {
        const { device_id, temperature, humidity, flame_detected } = req.body;

        if (!device_id) {
            return res.status(400).json({ ok: false, error: "device_id is required" });
        }

        const client = await clientPromise;
        const db = client.db("SmartLab");          // <<< DB name
        const collection = db.collection("sensor_data"); // <<< collection name

        const now = new Date();

        const updateDoc = {
            $set: {
                device_id,
                temperature,
                humidity,
                flame_detected,
                updated_at: now,
            },
            $setOnInsert: {
                created_at: now,
            },
        };

        // upsert: ถ้ามี device_id นี้แล้ว -> update, ถ้ายังไม่มี -> insert ใหม่
        const result = await collection.updateOne(
            { device_id },    // filter
            updateDoc,        // update
            { upsert: true }  // options
        );

        return res.status(200).json({
            ok: true,
            matchedCount: result.matchedCount,
            modifiedCount: result.modifiedCount,
            upsertedId: result.upsertedId ?? null,
        });
    } catch (err) {
        console.error("API /sensor error:", err);
        return res
            .status(500)
            .json({ ok: false, error: "Internal Server Error", detail: String(err) });
    }
}
