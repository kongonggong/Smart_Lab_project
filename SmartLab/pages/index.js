import { useEffect, useState } from "react";

export default function Home() {
    const [sensorData, setSensorData] = useState([]);
    const [yoloEvents, setYoloEvents] = useState([]);

    useEffect(() => {
        async function fetchData() {
            try {
                const sensorRes = await fetch("../api/sensor");
                const sensorJson = await sensorRes.json();
                if (sensorJson.ok) setSensorData(sensorJson.readings);

                // const yoloRes = await fetch("../api/yolo");
                // const yoloJson = await yoloRes.json();
                // if (yoloJson.ok) setYoloEvents(yoloJson.events);
            } catch (err) {
                console.error(err);
            }
        }

        fetchData();
        const interval = setInterval(fetchData, 5000); // รีเฟรชทุก 5 วิ
        return () => clearInterval(interval);
    }, []);

    return (
        <div style={{ padding: 20, fontFamily: "system-ui, sans-serif" }}>
            <h1>Lab Safety Dashboard</h1>

            <h2>Sensor Readings (ล่าสุด)</h2>
            <table border="1" cellPadding="4" style={{ borderCollapse: "collapse" }}>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Device</th>
                        <th>Temp (°C)</th>
                        <th>Humidity (%)</th>
                        <th>Flame</th>
                    </tr>
                </thead>
                <tbody>
                    {sensorData.map((s, idx) => (
                        <tr key={idx}>
                            <td>
                                {s.created_at
                                    ? new Date(s.created_at).toLocaleString()
                                    : "-"}
                            </td>
                            <td>{s.device_id || "-"}</td>
                            <td>{s.temperature ?? "-"}</td>
                            <td>{s.humidity ?? "-"}</td>
                            <td>{s.flame_detected ? "🔥" : "OK"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {/* <h2 style={{ marginTop: 40 }}>YOLO Events</h2>
            <table border="1" cellPadding="4" style={{ borderCollapse: "collapse" }}>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Device</th>
                        <th>Label</th>
                        <th>Conf.</th>
                        <th>Frame ID</th>
                    </tr>
                </thead>
                <tbody>
                    {yoloEvents.map((e, idx) => (
                        <tr key={idx}>
                            <td>
                                {e.created_at
                                    ? new Date(e.created_at).toLocaleString()
                                    : "-"}
                            </td>
                            <td>{e.device_id || "-"}</td>
                            <td>{e.label}</td>
                            <td>
                                {e.confidence !== undefined
                                    ? (e.confidence * 100).toFixed(1) + "%"
                                    : "-"}
                            </td>
                            <td>{e.frame_id ?? "-"}</td>
                        </tr>
                    ))}
                </tbody>
            </table> */}
        </div>
    );
}