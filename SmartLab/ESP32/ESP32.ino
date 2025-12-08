#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#include "DHT.h"

// ================== WiFi & Server ==================
const char* WIFI_SSID = "sanctuary 2.4G";  // <-- ใส่ WiFi ของคุณ
const char* WIFI_PASSWORD = "11223344";    // <-- ใส่รหัส WiFi

// URL API ของ Next.js (รันบน Mac)
const char* SERVER_URL = "http://192.168.1.242:3000/api/sensor";  // ส่ง sensor
const char* CONTROL_URL = "http://192.168.1.242:3000/api/onoff";  // 👈 ดึงสถานะรีเลย์

bool lastBuzzerState = false;
bool lastFanState = false;

bool lastManualBuzzer = false;
bool lastManualFan = false;

// state จาก DB
bool manualBuzzer = false;
bool manualFan = false;

const char* DEVICE_ID = "esp32-lab-01";  // ชื่อบอร์ดใน DB

// ถ้า true = ส่งเฉพาะตอนเจอไฟไหม้
// ถ้า false = ส่งทุกครั้ง
const bool SEND_ONLY_ON_FLAME = false;

// ถ้าอยากใช้ PUT แทน POST ให้เปลี่ยนเป็น true
const bool USE_HTTP_PUT = false;


// ================== PIN CONFIG ==================
#define DHTPIN 4
#define DHTTYPE DHT11  // ถ้าใช้ DHT22 ให้เปลี่ยนเป็น DHT22

const int FLAME_PIN = 32;         // เซนเซอร์ไฟ
const int RELAY_BUZZER_PIN = 16;  // รีเลย์ต่อ Buzzer
const int RELAY_FAN_PIN = 17;     // รีเลย์ต่อพัดลม

// ================== OBJECTS ==================
DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);  // 0x27 หรือ 0x3F แล้วแต่โมดูล

// ================== WIFI ==================
void connectWiFi() {
  Serial.println();
  Serial.println("Connecting to WiFi...");
  Serial.print("SSID: ");
  Serial.println(WIFI_SSID);

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Connecting WiFi");
  lcd.setCursor(0, 1);
  lcd.print(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(500);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("WiFi Connected");
    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP().toString());
  } else {
    Serial.println();
    Serial.println("WiFi FAILED!");

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("WiFi FAILED");
  }
}

// ================== SEND TO SERVER ==================
void sendSensorToServer(float temperature, float humidity, bool flameDetected) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] WiFi not connected, skip sending");
    return;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // ใช้ ArduinoJson สร้าง JSON body
  StaticJsonDocument<256> doc;
  doc["device_id"] = DEVICE_ID;
  doc["temperature"] = temperature;
  doc["humidity"] = humidity;
  doc["flame_detected"] = flameDetected;

  String requestBody;
  serializeJson(doc, requestBody);

  Serial.println("====== HTTP REQUEST ======");
  Serial.println(requestBody);

  int httpCode;
  if (USE_HTTP_PUT) {
    httpCode = http.PUT(requestBody);  // ใช้ PUT
  } else {
    httpCode = http.POST(requestBody);  // ใช้ POST
  }

  if (httpCode > 0) {
    Serial.printf("[HTTP] Response code: %d\n", httpCode);
    String payload = http.getString();
    Serial.println("[HTTP] Response body:");
    Serial.println(payload);
  } else {
    Serial.printf("[HTTP] Error: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

void fetchManualControlFromServer() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[CTRL] WiFi not connected, skip control fetch");
    return;
  }

  HTTPClient http;
  http.begin(CONTROL_URL);

  Serial.println("[CTRL] GET manual control...");
  int httpCode = http.GET();

  if (httpCode > 0) {
    Serial.printf("[CTRL] HTTP code: %d\n", httpCode);
    String payload = http.getString();
    Serial.println("[CTRL] Response:");
    Serial.println(payload);

    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
      Serial.print("[CTRL] JSON parse error: ");
      Serial.println(err.c_str());
    } else {
      // คาดว่าได้ object เดียว เช่น { "type":"manual_control", "buzzer":true, "fan":false }
      const char* type = doc["type"] | "";
      if (strcmp(type, "manual_control") == 0) {

        bool newBuzzer = doc["buzzer"] | false;
        bool newFan = doc["fan"] | false;

        // ===== แสดง LCD เมื่อค่าใน DB เปลี่ยน =====
        if (newBuzzer != manualBuzzer) {
          showDBUpdate("BUZZER", newBuzzer);
        }

        if (newFan != manualFan) {
          showDBUpdate("FAN", newFan);
        }

        manualBuzzer = newBuzzer;
        manualFan = newFan;
      }
    }
  } else {
    Serial.printf("[CTRL] HTTP error: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

void showRelayWarning(const char* line1, const char* line2, int delayMs) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(line2);
  delay(delayMs);
}

void showDBUpdate(const char* device, bool state) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("DB CONTROL");
  lcd.setCursor(0, 1);
  lcd.print(device);
  lcd.print(state ? ": ON" : ": OFF");
  delay(1200);
}

// ================== SETUP ==================
void setup() {
  Serial.begin(115200);
  delay(1000);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Smart Lab ESP32");

  // DHT
  dht.begin();

  // Pin modes
  pinMode(FLAME_PIN, INPUT);
  pinMode(RELAY_BUZZER_PIN, OUTPUT);
  pinMode(RELAY_FAN_PIN, OUTPUT);

  digitalWrite(RELAY_BUZZER_PIN, LOW);  // เริ่มต้นปิดรีเลย์
  digitalWrite(RELAY_FAN_PIN, LOW);

  // WiFi
  Serial.println(WiFi.localIP());
  connectWiFi();
}

// ================== LOOP ==================
void loop() {
  // อ่านค่าเซนเซอร์
  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  int flameValue = digitalRead(FLAME_PIN);
  bool flameDetected = (flameValue == HIGH);  // ถ้าใช้โมดูลที่ active LOW

  // เช็คค่า DHT ว่าผิดปกติไหม
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("[DHT] Failed to read from DHT sensor!");
  }

  // ========== แสดงบน Serial Monitor ==========
  Serial.print("T: ");
  Serial.print(temperature);
  Serial.print("C | H: ");
  Serial.print(humidity);
  Serial.println("%");

  if (flameDetected) {
    Serial.println("!!! FIRE DETECTED !!!");
  }

  // ========== แสดงบน LCD ==========
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("T:");
  lcd.print(temperature, 1);
  lcd.print("C H:");
  lcd.print(humidity, 0);
  lcd.print("%");

  lcd.setCursor(0, 1);
  if (flameDetected) {
    lcd.print("FIRE !!!");
  } else {
    lcd.print("FIRE: SAFE");
  }

  // ========== ดึงสถานะ manual control จาก DB ==========
  fetchManualControlFromServer();  // เรียกทุกรอบ loop (ตอนนี้ดีเลย์ 5 วินาทีอยู่แล้ว)

  // ========== ตัดสินใจสถานะรีเลย์ ==========
  bool buzzerState = LOW;
  bool fanState = LOW;
  Serial.println("===== CONTROL DECISION =====");

  if (flameDetected) {
    Serial.println("MODE : FIRE EMERGENCY 🚨");
    buzzerState = HIGH;
    fanState = HIGH;
  } else {
    Serial.println("MODE : MANUAL CONTROL 🧠");
    buzzerState = manualBuzzer ? HIGH : LOW;
    fanState = manualFan ? HIGH : LOW;
  }

  Serial.print("Final BUZZER state : ");
  Serial.println(buzzerState ? "ON" : "OFF");
  Serial.print("Final FAN state    : ");
  Serial.println(fanState ? "ON" : "OFF");

  Serial.println("============================");

  if (flameDetected) {
    // ถ้าเจอไฟ -> บังคับให้เปิดทั้งสองอัน (โหมด safety)
    buzzerState = HIGH;
    fanState = HIGH;
  } else {
    // ถ้าไม่เจอไฟ -> ใช้ค่าจาก DB
    buzzerState = manualBuzzer ? HIGH : LOW;
    fanState = manualFan ? HIGH : LOW;
  }
  // ========== แสดงข้อความก่อนเปิดรีเลย์ ==========
  if (!lastBuzzerState && buzzerState) {
    showRelayWarning("BUZZER ALERT!", "Activating...", 1200);
  }

  if (!lastFanState && fanState) {
    showRelayWarning("FAN TURN ON", "Ventilating...", 1200);
  }

  // สั่งรีเลย์จริง
  digitalWrite(RELAY_BUZZER_PIN, buzzerState);
  digitalWrite(RELAY_FAN_PIN, fanState);

  // อัปเดตสถานะเดิม
  lastBuzzerState = buzzerState;
  lastFanState = fanState;

  // ========== ส่งข้อมูลเข้า DB ผ่าน Next.js ==========
  bool shouldSend = true;
  if (SEND_ONLY_ON_FLAME && !flameDetected) {
    shouldSend = false;
  }

  if (shouldSend) {
    sendSensorToServer(temperature, humidity, flameDetected);
  } else {
    Serial.println("[HTTP] Skip sending (no fire and SEND_ONLY_ON_FLAME = true)");
  }

  delay(1000);  // อ่านทุก 5 วินาที (ปรับได้)
}
