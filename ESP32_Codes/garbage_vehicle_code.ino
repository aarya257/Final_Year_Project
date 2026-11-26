#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>

/* ================= WIFI ================= */
const char* ssid = "AryaB";
const char* password = "07012004";

/* ================= SERVER ================= */
String serverURL = "http://172.22.104.199:8000/api/pickup";

/* ================= RFID ================= */
#define SS_PIN 21
#define RST_PIN 22
#define SCK_PIN 18
#define MOSI_PIN 23
#define MISO_PIN 19

MFRC522 mfrc522(SS_PIN, RST_PIN);

/* ================= LCD ================= */
#define SDA_LCD 16   // RX2
#define SCL_LCD 17   // TX2

LiquidCrystal_I2C lcd(0x27, 16, 2);

/* ================= USER DATABASE ================= */
struct UserData {
  String rfid;
  String name;
  String address;
};

UserData users[] = {
  {"033BD5E4", "User 1", "A GreenView"},
  {"239ECEE4", "User 2", "A GreenView"},
  {"536EBFE4", "User 3", "A LakeSide"},
  {"C393CFE4", "User 4", "A LakeSide"},
  {"9352C7E4", "User 5", "B MetroHt"},
  {"63DED6E4", "User 6", "B MetroHt"},
  {"439A87E4", "User 7", "B GreenView"},
  {"B3E58FE4", "User 8", "B LakeSide"},
  {"738A86E4", "User 9", "C MetroHt"},
  {"B3FEC6E4", "User 10", "C MetroHt"},
  {"C3CCD811", "User 11", "C GreenView"},
  {"330FD2E4", "User 12", "C GreenView"},
  {"732BD7E4", "User 13", "A MetroHt"},
  {"63A8D8E4", "User 14", "B LakeSide"},
  {"6396D2E4", "User 15", "C LakeSide"}
};

const int userCount = sizeof(users) / sizeof(users[0]);

/* ================= LOOKUP FUNCTION ================= */
bool getUser(String rfid, String &name, String &address) {
  for (int i = 0; i < userCount; i++) {
    if (users[i].rfid == rfid) {
      name = users[i].name;
      address = users[i].address;
      return true;
    }
  }
  return false;
}

/* ================= SETUP ================= */
void setup() {

  Serial.begin(115200);

  /* LCD INIT */
  Wire.begin(SDA_LCD, SCL_LCD);
  lcd.init();
  lcd.backlight();

  lcd.setCursor(0,0);
  lcd.print("Smart Waste");
  lcd.setCursor(0,1);
  lcd.print("System");
  delay(2000);
  lcd.clear();

  /* RFID INIT */
  SPI.begin(SCK_PIN, MISO_PIN, MOSI_PIN, SS_PIN);
  mfrc522.PCD_Init();

  Serial.println("RFID Ready");

  /* WIFI INIT */
  WiFi.begin(ssid, password);

  lcd.print("Connecting WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    lcd.print(".");
  }

  lcd.clear();
  lcd.print("WiFi Connected");
  delay(1500);
  lcd.clear();

  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  lcd.print("Scan RFID Card");
}

/* ================= LOOP ================= */
void loop() {

  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  /* READ RFID UID */
  String rfidUID = "";

  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) rfidUID += "0";
    rfidUID += String(mfrc522.uid.uidByte[i], HEX);
  }

  rfidUID.toUpperCase();

  Serial.print("RFID: ");
  Serial.println(rfidUID);

  String name, address;

  lcd.clear();

  if (getUser(rfidUID, name, address)) {

    lcd.setCursor(0,0);
    lcd.print(name);

    lcd.setCursor(0,1);
    lcd.print(address);

  } 
  else {

    lcd.print("Unknown Card");

    delay(2000);
    lcd.clear();
    lcd.print("Scan RFID Card");

    return;
  }

  delay(2000);

  /* SEND TO SERVER */

  if (WiFi.status() == WL_CONNECTED) {

    WiFiClient client;
    HTTPClient http;

    http.begin(client, serverURL);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<200> doc;

    doc["rfid"] = rfidUID;

    String requestBody;

    serializeJson(doc, requestBody);

    int httpCode = http.POST(requestBody);

    String response = http.getString();

    Serial.print("HTTP Code: ");
    Serial.println(httpCode);

    Serial.print("Response: ");
    Serial.println(response);

    lcd.clear();

    if (httpCode == 200)
      lcd.print("Pickup Logged");
    else
      lcd.print("Server Error");

    http.end();
  }

  else {

    lcd.clear();
    lcd.print("WiFi Lost");
  }

  delay(3000);

  lcd.clear();
  lcd.print("Scan RFID Card");

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}