// pages/api/testdb.js
import clientPromise from "../../lib/mongodb";

export default async function handler(req, res) {
    try {
        const client = await clientPromise;
        const db = client.db(process.env.MONGODB_DB || "SmartLab");

        const result = await db.collection("test").insertOne({
            msg: "hello from /api/testdb",
            at: new Date()
        });

        res.status(200).json({ ok: true, insertedId: result.insertedId });
    } catch (err) {
        console.error(err);
        res.status(500).json({ ok: false, error: err.message });
    }
}
