/*
 * AMHR-PD Professional Servo Controller
 * ESP32-S3 | ESP32Servo Library | 10x MG996R
 * 
 * REQUIRED LIBRARY: ESP32Servo by Kevin Harrington
 * Install via: Arduino IDE -> Library Manager -> Search "ESP32Servo"
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include "servo_config.h"

// ============================== SERVO OBJECTS ==============================

Servo servos[NUM_SERVOS];
float current_angles[NUM_SERVOS];

WebSocketsClient webSocket;

// ============================== CONFIG ==============================

const char WIFI_SSID[] = "YOUR_SSID";  // TODO: Replace with your WiFi name
const char WIFI_PASSWORD[] = "YOUR_PASSWORD";  // TODO: Replace with your WiFi password

const char BACKEND_HOST[] = "10.83.60.93";  // Updated to current server IP
const uint16_t BACKEND_PORT = 8000;

const char DEVICE_ID[] = "servoscontroller";
const char DEVICE_TYPE[] = "esp32s3";
const char FIRMWARE_VERSION[] = "2.0.0";

// ============================== STATE ==============================

enum SystemState {
  WIFI_CONNECTING,
  WIFI_CONNECTED,
  WS_CONNECTING,
  WS_CONNECTED
};

SystemState system_state = WIFI_CONNECTING;

unsigned long last_heartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 5000;

// ============================== SERVO FUNCTIONS ==============================

void setup_servos() {
  // Allow allocation of all timers for servo library
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  Serial.println("[INIT] Attaching servos...");
  
  for (int i = 0; i < NUM_SERVOS; i++) {
    servos[i].setPeriodHertz(50);  // Standard 50Hz servo
    
    // Attach with pulse range for MG996R
    int attached = servos[i].attach(SERVO_PINS[i], SERVO_MIN_PULSE_US, SERVO_MAX_PULSE_US);
    
    if (attached) {
      servos[i].write(SERVO_HOME_ANGLE);
      current_angles[i] = SERVO_HOME_ANGLE;
      Serial.printf("[INIT] Servo %d -> GPIO %d (OK)\n", i, SERVO_PINS[i]);
    } else {
      Serial.printf("[ERROR] Servo %d -> GPIO %d FAILED TO ATTACH!\n", i, SERVO_PINS[i]);
    }
    
    yield();  // Allow background tasks instead of blocking delay
  }

  Serial.println("[INIT] All servos initialized at home position (90 deg)");
}

// Quick test: sweep servo 0 to verify hardware works
// NOTE: Uses yield() instead of delay() to prevent blocking
void test_servo_sweep(int channel) {
  Serial.printf("[TEST] Testing servo %d...\n", channel);
  
  Serial.println("[TEST] Moving to 0 deg");
  servos[channel].write(0);
  non_blocking_delay(300);
  
  Serial.println("[TEST] Moving to 90 deg");
  servos[channel].write(90);
  non_blocking_delay(300);
  
  Serial.println("[TEST] Moving to 180 deg");
  servos[channel].write(180);
  non_blocking_delay(300);
  
  Serial.println("[TEST] Back to 90 deg");
  servos[channel].write(90);
  
  Serial.println("[TEST] Complete!");
}

// Non-blocking delay that keeps system responsive
void non_blocking_delay(unsigned long ms) {
  unsigned long start = millis();
  while (millis() - start < ms) {
    yield();  // Allow background tasks to run
  }
}

void move_servo(int channel, float angle) {
  if (channel < 0 || channel >= NUM_SERVOS) {
    Serial.printf("[ERROR] Invalid channel: %d\n", channel);
    return;
  }

  // Clamp angle to valid range
  if (angle < SERVO_MIN_ANGLE) angle = SERVO_MIN_ANGLE;
  if (angle > SERVO_MAX_ANGLE) angle = SERVO_MAX_ANGLE;

  // Move servo using ESP32Servo library
  servos[channel].write((int)angle);
  current_angles[channel] = angle;

  Serial.printf("[SERVO] CH%d (GPIO%d) -> %.1f deg\n", 
                channel, SERVO_PINS[channel], angle);
}

// ============================== WIFI ==============================

void setup_wifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  system_state = WIFI_CONNECTING;
  Serial.println("[WIFI] Connecting...");
}

// ============================== WEBSOCKET ==============================

void setup_websocket() {
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/servoscontroller");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);
  system_state = WS_CONNECTING;
  Serial.println("[WS] Connecting to backend...");
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      system_state = WS_CONNECTED;
      send_registration();
      Serial.println("[WS] Connected and registered");
      break;

    case WStype_TEXT:
      handle_ws_message((char*)payload, length);
      break;

    case WStype_DISCONNECTED:
      system_state = WIFI_CONNECTED;
      Serial.println("[WS] Disconnected");
      break;

    case WStype_ERROR:
      Serial.println("[WS] Error occurred");
      break;

    default:
      break;
  }
}

void send_registration() {
  StaticJsonDocument<256> reg;
  reg["message_type"] = "registration";
  reg["device_type"] = DEVICE_TYPE;

  JsonObject meta = reg.createNestedObject("metadata");
  meta["device_id"] = DEVICE_ID;
  meta["firmware_version"] = FIRMWARE_VERSION;
  meta["servo_count"] = NUM_SERVOS;

  String out;
  serializeJson(reg, out);
  webSocket.sendTXT(out);
}

void send_heartbeat() {
  StaticJsonDocument<64> hb;
  hb["message_type"] = "heartbeat";
  hb["device_type"] = DEVICE_TYPE;
  
  String out;
  serializeJson(hb, out);
  webSocket.sendTXT(out);
}

// ============================== MESSAGE HANDLER ==============================

void handle_ws_message(char* payload, size_t len) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, payload, len);

  if (err) {
    Serial.printf("[WS] JSON parse failed: %s\n", err.c_str());
    return;
  }

  const char* message_type = doc["message_type"];
  if (!message_type) {
    Serial.println("[WS] Missing message_type");
    return;
  }

  // ===== COMMAND =====
  if (strcmp(message_type, "command") == 0) {
    Serial.println("[WS] Command received");

    // POSE COMMAND
    if (doc.containsKey("command_name")) {
      const char* cmd = doc["command_name"];
      Serial.printf("[WS] Pose command: %s\n", cmd);

      if (strcmp(cmd, "resetposition") == 0) pose_reset();
      else if (strcmp(cmd, "handsup") == 0) pose_handsup();
      else if (strcmp(cmd, "headup") == 0) pose_headup();
      else if (strcmp(cmd, "headleft") == 0) pose_headleft();
      else Serial.printf("[WS] Unknown pose: %s\n", cmd);
    }

    // SERVO COMMAND (channel + angle)
    if (doc.containsKey("payload")) {
      JsonObject p = doc["payload"];
      if (p.containsKey("channel") && p.containsKey("angle")) {
        int ch = p["channel"];
        float ang = p["angle"];
        move_servo(ch, ang);
      }
    }

    // SEND ACK
    send_command_ack(doc["command_id"]);
  }
}

void send_command_ack(const char* command_id) {
  StaticJsonDocument<128> ack;
  ack["message_type"] = "command_ack";
  ack["device_type"] = DEVICE_TYPE;
  ack["command_id"] = command_id;
  ack["status"] = "success";

  String out;
  serializeJson(ack, out);
  webSocket.sendTXT(out);
}

// ============================== POSES ==============================

void pose_reset() {
  Serial.println("[POSE] Reset - Default positions");
  
  // NECK
  move_servo(NECK_UPDOWN, 80);      // Up-Down: 80 deg
  move_servo(NECK_LEFTRIGHT,90);    // Left-Right: 0 deg
  
  // LEFT ARM
  move_servo(L_SHOULDER, 0);        // Shoulder: 0 deg
  move_servo(L_ELBOW_1, 90);        // Elbow1: 90 deg
  move_servo(L_ELBOW_2, 90);        // Elbow2: 90 deg
  move_servo(L_GRIPPER, 0);         // Gripper: 0 deg
  
  // RIGHT ARM
  move_servo(R_SHOULDER, 0);        // Shoulder: 0 deg
  move_servo(R_ELBOW_1, 90);        // Elbow1: 90 deg
  move_servo(R_ELBOW_2, 90);        // Elbow2: 90 deg
  move_servo(R_GRIPPER, 0);         // Gripper: 0 deg
}

void pose_handsup() {
  Serial.println("[POSE] Hands Up");
  
  // Left arm
  move_servo(L_SHOULDER, 160);
  move_servo(L_ELBOW_1, 90);
  move_servo(L_ELBOW_2, 90);
  move_servo(L_GRIPPER, 90);

  // Right arm
  move_servo(R_SHOULDER, 20);
  move_servo(R_ELBOW_1, 90);
  move_servo(R_ELBOW_2, 90);
  move_servo(R_GRIPPER, 90);
}

void pose_headleft() {
  Serial.println("[POSE] Head Left");
  move_servo(NECK_LEFTRIGHT, 20);
}

void pose_headup() {
  Serial.println("[POSE] Head Up");
  move_servo(NECK_UPDOWN, 30);
}


// ============================== SETUP ==============================

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================");
  Serial.println("  AMHR-PD Servo Controller v2.0");
  Serial.println("  ESP32Servo Library Edition");
  Serial.println("========================================\n");

  setup_servos();
  setup_wifi();
}

// ============================== LOOP ==============================

void loop() {
  // WiFi connection check
  if (WiFi.status() == WL_CONNECTED && system_state == WIFI_CONNECTING) {
    Serial.printf("[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
    system_state = WIFI_CONNECTED;
    setup_websocket();
  }

  // Handle WebSocket
  webSocket.loop();

  // Send heartbeat
  if (system_state == WS_CONNECTED && millis() - last_heartbeat > HEARTBEAT_INTERVAL) {
    send_heartbeat();
    last_heartbeat = millis();
  }
}
