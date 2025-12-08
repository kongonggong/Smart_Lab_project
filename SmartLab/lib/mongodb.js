// lib/mongodb.js
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;
const options = {};

if (!uri) {
    throw new Error("Please define the MONGODB_URI environment variable");
}

let client;
let clientPromise;

if (process.env.NODE_ENV === "development") {
    // ใช้ global เพื่อไม่ให้สร้าง client ใหม่ทุกครั้งเวลา hot reload
    if (!global._mongoClientPromise) {
        client = new MongoClient(uri, options);
        global._mongoClientPromise = client.connect();
    }
    clientPromise = global._mongoClientPromise;
} else {
    client = new MongoClient(uri, options);
    clientPromise = client.connect();
}

/**
 * ✅ helper function สำหรับ API routes
 * ใช้แบบ: const db = await getDb("SmartLab")
 */
export async function getDb(dbName) {
    const client = await clientPromise;
    return client.db(dbName);
}

// ✅ export เดิม (เผื่อใช้ที่อื่น)
export default clientPromise;