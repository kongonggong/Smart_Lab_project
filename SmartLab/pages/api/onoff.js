// pages/api/onoff.js
import { getDb } from "../../lib/mongodb";

export default async function handler(req, res) {
    if (req.method !== "GET") {
        return res.status(405).json({ ok: false });
    }

    try {
        const db = await getDb("SmartLab");
        const col = db.collection("OnOffStatus");

        const doc = await col.findOne({ type: "manual_control" });

        return res.status(200).json({
            type: "manual_control",
            buzzer: !!doc?.buzzer,
            fan: !!doc?.fan,
        });
    } catch (err) {
        console.error(err);
        return res.status(500).json({ ok: false });
    }
}