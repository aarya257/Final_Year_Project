/****************************************************
 SMART WASTE MANAGEMENT – FINAL STABLE VALUE VERSION
****************************************************/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <HX711_ADC.h>

/* ================= WIFI ================= */
const char* ssid = "AryaB";
const char* password = "07012004";

/* ================= SERVER ================= */
String serverURL = "http://172.22.104.199:8000/api/sector-waste";

/* ================= RFID ================= */
#define SS_PIN   4
#define RST_PIN  27
MFRC522 rfid(SS_PIN, RST_PIN);

/* ================= LCD ================= */
#define LCD_ADDR 0x27
#define I2C_SDA 25
#define I2C_SCL 26
LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

/* ================= HX711 ================= */
#define HX_DT  32
#define HX_SCK 33
HX711_ADC LoadCell(HX_DT, HX_SCK);

float calibrationValue = 555.01;

/* ================= VARIABLES ================= */
String scannedUID;
String sector;

int W1_total = 0;
int W2_afterDry = 0;
int W3_empty = 0;

int dry_waste = 0;
int wet_waste = 0;

/* ================= RFID MAP ================= */
struct SectorMap {
  String rfid;
  String sector;
};

SectorMap sectorTable[] = {
  {"139181E4", "A"},
  {"F39F1CE5", "A"},
  {"53A6C3E4", "B"},
  {"DA8EFB03", "B"},
  {"639A37E4", "C"}
};

const int sectorCount = sizeof(sectorTable) / sizeof(sectorTable[0]);

String getSectorFromRFID(String uid) {
  for (int i = 0; i < sectorCount; i++) {
    if (sectorTable[i].rfid == uid) return sectorTable[i].sector;
  }
  return "UNKNOWN";
}

/* ================= SETUP ================= */
void setup() {

  Serial.begin(115200);
  delay(1000);

  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init();
  lcd.backlight();

  lcd.print("Smart Waste");
  lcd.setCursor(0,1);
  lcd.print("Starting...");
  delay(2000);

  WiFi.begin(ssid, password);

  lcd.clear();
  lcd.print("Connecting WiFi");

  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    lcd.print(".");
  }

  Serial.println("\nWiFi Connected!");

  IPAddress ip = WiFi.localIP();
  Serial.println(ip);

  lcd.clear();
  lcd.print("WiFi Connected");
  lcd.setCursor(0,1);
  lcd.print(ip);

  delay(3000);

  SPI.begin(18, 19, 23, SS_PIN);
  rfid.PCD_Init();

  LoadCell.begin();
  LoadCell.start(2000, true);

  if (LoadCell.getTareTimeoutFlag()) {
    Serial.println("HX711 ERROR");
    lcd.clear();
    lcd.print("HX711 ERROR");
    while (1);
  }

  LoadCell.setCalFactor(calibrationValue);
  Serial.println("HX711 Ready");

  lcd.clear();
  lcd.print("Scan RFID Card");
}

/* ================= LOOP ================= */
void loop() {

  if (!rfid.PICC_IsNewCardPresent()) {
    delay(5);
    return;
  }

  if (!rfid.PICC_ReadCardSerial()) {
    delay(5);
    return;
  }

  scannedUID = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) scannedUID += "0";
    scannedUID += String(rfid.uid.uidByte[i], HEX);
  }
  scannedUID.toUpperCase();

  Serial.println("\n==============================");
  Serial.println("RFID: " + scannedUID);

  sector = getSectorFromRFID(scannedUID);

  if (sector == "UNKNOWN") {
    lcd.clear();
    lcd.print("Unauthorized");
    delay(2000);
    lcd.clear();
    lcd.print("Scan RFID Card");
    return;
  }

  lcd.clear();
  lcd.print("Sector: ");
  lcd.print(sector);
  delay(1500);

  /* ===== STAGE 1 ===== */
  lcd.clear();
  lcd.print("Full Vehicle");
  delay(5000);
  W1_total = readWeight("STAGE 1");

  /* ===== STAGE 2 ===== */
  lcd.clear();
  lcd.print("Unload DRY");
  delay(10000);
  W2_afterDry = readWeight("STAGE 2");

  /* ===== STAGE 3 ===== */
  lcd.clear();
  lcd.print("Unload WET");
  delay(10000);
  W3_empty = readWeight("STAGE 3");

  dry_waste = W1_total - W2_afterDry;
  wet_waste = W2_afterDry - W3_empty;

  if (dry_waste < 0) dry_waste = 0;
  if (wet_waste < 0) wet_waste = 0;

  Serial.println("----- FINAL RESULT -----");
  Serial.print("Dry Waste : ");
  Serial.println(dry_waste);
  Serial.print("Wet Waste : ");
  Serial.println(wet_waste);

  sendToServer();

  lcd.clear();
  lcd.print("Dry:");
  lcd.print(dry_waste);
  lcd.setCursor(0,1);
  lcd.print("Wet:");
  lcd.print(wet_waste);

  delay(5000);

  lcd.clear();
  lcd.print("Scan RFID Card");

  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();
}

/* ================= READ WEIGHT (STABLE LOGIC) ================= */
int readWeight(const char* stageName) {

  Serial.println("--------------------------------");
  Serial.println(stageName);

  lcd.clear();
  lcd.print(stageName);

  int stableCount = 0;
  float lastWeight = 0;
  float currentWeight = 0;

  const float tolerance = 0.5;

  while (stableCount < 10) {

    if (LoadCell.update()) {

      currentWeight = LoadCell.getData();
      if (currentWeight < 0) currentWeight = 0;

      Serial.print("Weight: ");
      Serial.print(currentWeight);
      Serial.print(" | Stable: ");
      Serial.println(stableCount);

      lcd.setCursor(0,1);
      lcd.print("W:");
      lcd.print(currentWeight,1);
      lcd.print(" S:");
      lcd.print(stableCount);
      lcd.print("   ");

      if (abs(currentWeight - lastWeight) < tolerance) {
        stableCount++;
      } else {
        stableCount = 0;
      }

      lastWeight = currentWeight;
    }

    delay(1);
  }

  int finalWeight = round(currentWeight);

  Serial.print("FINAL STABLE: ");
  Serial.println(finalWeight);

  lcd.clear();
  lcd.print("Final:");
  lcd.setCursor(0,1);
  lcd.print(finalWeight);

  delay(2000);

  return finalWeight;
}

/* ================= SEND ================= */
void sendToServer() {

  if (WiFi.status() != WL_CONNECTED) return;

  WiFiClient client;
  HTTPClient http;

  http.begin(client, serverURL);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<128> doc;
  doc["sector"] = sector;
  doc["wet"] = wet_waste;
  doc["dry"] = dry_waste;

  String payload;
  serializeJson(doc, payload);

  yield();

  int httpCode = http.POST(payload);

  yield();

  String response = http.getString();

  yield();

  Serial.println("Payload:");
  Serial.println(payload);
  Serial.println(httpCode);
  Serial.println(response);

  http.end();
}