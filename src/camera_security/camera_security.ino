#include <Arduino_RouterBridge.h>

// Onboard indicator LEDs (or digital output pins connected to relays/LEDs)
#define ZONE_1_PIN 8  // Left Zone Output
#define ZONE_2_PIN 9  // Center Zone Output
#define ZONE_3_PIN 10 // Right Zone Output

void setup() {
  Serial.begin(115200);

  // Set pin modes
  pinMode(ZONE_1_PIN, OUTPUT);
  pinMode(ZONE_2_PIN, OUTPUT);
  pinMode(ZONE_3_PIN, OUTPUT);

  // Initialize all outputs to low (off)
  digitalWrite(ZONE_1_PIN, LOW);
  digitalWrite(ZONE_2_PIN, LOW);
  digitalWrite(ZONE_3_PIN, LOW);

  // Initialize RouterBridge to receive commands from the Linux system
  RouterBridge.begin();
  RouterBridge.onReceive(onZoneCommandReceived);

  Serial.println("MCU Zone Controller Initialized.");
}

void loop() {
  // Check for updates/RPC calls from the MPU
  RouterBridge.update();
  delay(10);
}

// Callback execution when Linux sends active zone
void onZoneCommandReceived(int activeZone) {
  // Turn off all zones first
  digitalWrite(ZONE_1_PIN, LOW);
  digitalWrite(ZONE_2_PIN, LOW);
  digitalWrite(ZONE_3_PIN, LOW);

  // Turn on the active zone
  if (activeZone == 1) {
    digitalWrite(ZONE_1_PIN, HIGH);
    Serial.println("[MCU] Lighting up Zone 1 (Left)");
  } else if (activeZone == 2) {
    digitalWrite(ZONE_2_PIN, HIGH);
    Serial.println("[MCU] Lighting up Zone 2 (Center)");
  } else if (activeZone == 3) {
    digitalWrite(ZONE_3_PIN, HIGH);
    Serial.println("[MCU] Lighting up Zone 3 (Right)");
  } else {
    Serial.println("[MCU] No target detected. All zones off.");
  }
}
