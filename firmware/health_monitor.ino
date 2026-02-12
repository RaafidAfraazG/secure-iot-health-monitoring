#include <ESP8266WiFi.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <ESP8266HTTPClient.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <ArduinoJson.h>
#include <base64.h>
#include <AESLib.h>
#include "MAX30100_PulseOximeter.h"

// ================== WiFi Credentials ==================
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";


// ================== Server Details ==================
const char* serverIP = "YOUR_SERVER_IP";
const int serverPort = 5000;

// ================== Pin Definitions ==================
#define BUZZER D5    // your buzzer wiring
#define SDA_PIN D2   // I2C SDA
#define SCL_PIN D1   // I2C SCL

// ================== Sensors ==================
Adafruit_ADXL345_Unified accel = Adafruit_ADXL345_Unified(12345);
PulseOximeter pox;

// ================== AES Setup ==================
AESLib aesLib;
byte aesKey[] = { 'm','y','s','e','c','r','e','t','k','e','y','1','2','3','4','5','6' };
char encryptedText[128];

// ================== Twilio ==================
const char* twilio_account_sid = "YOUR_TWILIO_SID";
const char* twilio_auth_token = "YOUR_TWILIO_TOKEN";
const char* twilio_from_number = "YOUR_TWILIO_NUMBER";
const char* emergency_contact = "EMERGENCY_CONTACT";

// ================== Globals ==================
WiFiClientSecure client;
int heart_rate = 0;
bool fallDetected = false;
float fallThreshold = 3.5;
float xBase = 0, yBase = 0, zBase = 0;
unsigned long lastCallTime = 0;

// ================== Setup ==================
void setup() {
  Serial.begin(115200);
  pinMode(BUZZER, OUTPUT);

  // WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  // I2C
  Wire.begin(SDA_PIN, SCL_PIN);

  // ADXL345
  if (!accel.begin()) {
    Serial.println("⚠ ADXL345 not detected!");
    while (1) { delay(1000); }
  }
  accel.setRange(ADXL345_RANGE_16_G);
  calibrateAccelerometer();

  // MAX30100
  if (!pox.begin()) {
    Serial.println("⚠ MAX30100 not detected!");
    while (1) { delay(1000); }
  }
  Serial.println("✅ MAX30100 Ready");

  // Allow SSL without cert
  client.setInsecure(); 
  Serial.println("System Ready...");
}

// ================== Accelerometer Calibration ==================
void calibrateAccelerometer() {
  sensors_event_t event;
  int sampleCount = 50;
  float xSum=0,ySum=0,zSum=0;
  for (int i=0;i<sampleCount;i++) {
    accel.getEvent(&event);
    xSum += event.acceleration.x;
    ySum += event.acceleration.y;
    zSum += event.acceleration.z;
    delay(10);
  }
  xBase = xSum / sampleCount;
  yBase = ySum / sampleCount;
  zBase = zSum / sampleCount;
  Serial.println("✅ Accelerometer calibrated.");
}

// ================== Fall Detection ==================
bool detectFall() {
  sensors_event_t event;
  accel.getEvent(&event);
  float xDev = event.acceleration.x - xBase;
  float yDev = event.acceleration.y - yBase;
  float zDev = event.acceleration.z - zBase;
  float magnitude = sqrt(xDev*xDev + yDev*yDev + zDev*zDev);
  Serial.print("Fall Magnitude: ");
  Serial.println(magnitude);
  return magnitude > fallThreshold;
}

// ================== Heart Rate ==================
int readHeartRate() {
  pox.update();
  int bpm = pox.getHeartRate();
  if (bpm < 40 || bpm > 180) {
    bpm = 75; // fallback safe value
  }
  return bpm;
}

// ================== AES Encryption + Base64 ==================
String encryptData(String msg) {
  int msgLen = msg.length() + 1;
  char msgArray[msgLen];
  msg.toCharArray(msgArray, msgLen);

  int cipherLength = aesLib.encrypt((byte*)msgArray, msgLen, (byte*)encryptedText, aesKey, 128);
  String encoded = base64::encode((uint8_t*)encryptedText, cipherLength);
  return encoded;
}

// ================== Send Data to Flask ==================
void sendDataToServer() {
  if (!client.connect(serverIP, serverPort)) {
    Serial.println("❌ Server connection failed");
    return;
  }

  // Create JSON
  StaticJsonDocument<256> doc;
  doc["heart_rate"] = heart_rate;
  doc["fall"] = fallDetected ? 1 : 0;
  String json;
  serializeJson(doc, json);

  // Encrypt JSON
  String encrypted = encryptData(json);

  // Basic Auth
  String username = "iotuser";
  String password = "iotpass";
  String auth = username + ":" + password;
  String encodedAuth = base64::encode(auth);

  // Send POST
  client.print("POST /update HTTP/1.1\r\n"
               "Host: " + String(serverIP) + "\r\n"
               "Authorization: Basic " + encodedAuth + "\r\n"
               "Content-Type: text/plain\r\n"
               "Content-Length: " + String(encrypted.length()) + "\r\n\r\n" +
               encrypted);

  Serial.print("📤 Encrypted Data Sent: ");
  Serial.println(encrypted);
  client.stop();
}

// ================== Main Loop ==================
void loop() {
  heart_rate = readHeartRate();
  fallDetected = detectFall();

  sendDataToServer();

  if (fallDetected && heart_rate > 100) {
    digitalWrite(BUZZER, HIGH);
    if (millis() - lastCallTime > 120000 || lastCallTime == 0) {
      Serial.println("⚠ ALERT: Fall + High HR detected!");
      // Twilio call logic here
      lastCallTime = millis();
    }
  } else {
    digitalWrite(BUZZER, LOW);
  }
  delay(5000);
}
