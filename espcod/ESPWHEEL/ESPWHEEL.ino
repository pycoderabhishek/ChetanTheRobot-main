/*
 * AMHR-PD Wheel Controller - Smart Navigation Edition
 * ESP32 Dev Module | TB6612FNG | HC-SR04 | IR Sensors
 * 
 * Features:
 * - Dual-Core Operation (Nav Logic + Comms)
 * - Smart Obstacle Avoidance (Sonar + IR)
 * - Servo Interlock (Locks movement when servos are active)
 * - Precise Speed Control
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <NewPing.h>

// ============================== HARDWARE CONFIG ==============================

// --- MOTORS (TB6612FNG) ---
// Left Motor (Channel A)
#define LEFT_PWM    14
#define LEFT_IN1    27
#define LEFT_IN2    26

// Right Motor (Channel B)
#define RIGHT_PWM   32
#define RIGHT_IN1   25
#define RIGHT_IN2   33

// Master Standby (TB6612FNG specific)
#define MOTOR_STBY  23

// --- ULTRASONIC SENSORS (HC-SR04) ---
#define SONAR_L_TRIG 13
#define SONAR_L_ECHO 12
#define SONAR_R_TRIG 4
#define SONAR_R_ECHO 15
#define MAX_DISTANCE 200 // cm

// --- IR SENSORS (Active Low: LOW = Obstacle) ---
#define IR_LEFT     34  // Input Only pin
#define IR_RIGHT    35  // Input Only pin

// --- PWM SETTINGS ---
#define PWM_FREQ        5000
#define PWM_RES         8
#define PWM_CH_L        0
#define PWM_CH_R        1

// ============================== NETWORK CONFIG ==============================

const char WIFI_SSID[] = "YOUR_SSID";      // TODO: Configure
const char WIFI_PASSWORD[] = "YOUR_PASSWORD"; 
const char BACKEND_HOST[] = "10.83.60.93"; // Server IP
const uint16_t BACKEND_PORT = 8000;

const char DEVICE_ID[] = "wheelcontroller";
const char DEVICE_TYPE[] = "esp32";
const char FIRMWARE_VERSION[] = "2.0.0-SMART";

// ============================== STATE MACHINE ==============================

enum RobotState {
  STATE_IDLE,       // Motors off, waiting
  STATE_LOCKED,     // Servo interlock active (Movement forbidden)
  STATE_MOVING,     // Executing command (with safety checks)
  STATE_AVOIDING,   // Autonomous avoidance maneuver
  STATE_HALTED      // Emergency stop (IR trigger)
};

volatile RobotState current_state = STATE_IDLE;
volatile bool safety_override = false;

// Motor State
int target_speed_l = 0;
int target_speed_r = 0;
String last_command = "stop";

// Sensor Data
volatile int dist_l = 0;
volatile int dist_r = 0;
volatile bool ir_l_blocked = false;
volatile bool ir_r_blocked = false;

// Objects
WebSocketsClient webSocket;
NewPing sonar_left(SONAR_L_TRIG, SONAR_L_ECHO, MAX_DISTANCE);
NewPing sonar_right(SONAR_R_TRIG, SONAR_R_ECHO, MAX_DISTANCE);

// ============================== TASKS ==============================

void TaskNavigation(void *pvParameters);
void TaskSensors(void *pvParameters);

// ============================== MOTOR DRIVER ==============================

void setup_motors() {
  pinMode(LEFT_IN1, OUTPUT);
  pinMode(LEFT_IN2, OUTPUT);
  pinMode(RIGHT_IN1, OUTPUT);
  pinMode(RIGHT_IN2, OUTPUT);
  pinMode(MOTOR_STBY, OUTPUT);

  ledcSetup(PWM_CH_L, PWM_FREQ, PWM_RES);
  ledcSetup(PWM_CH_R, PWM_FREQ, PWM_RES);
  ledcAttachPin(LEFT_PWM, PWM_CH_L);
  ledcAttachPin(RIGHT_PWM, PWM_CH_R);

  digitalWrite(MOTOR_STBY, HIGH); // Enable Driver
  stop_motors();
}

void set_speed(int l, int r) {
  // Constrain
  l = constrain(l, -255, 255);
  r = constrain(r, -255, 255);

  // Left
  if (l >= 0) {
    digitalWrite(LEFT_IN1, HIGH);
    digitalWrite(LEFT_IN2, LOW);
  } else {
    digitalWrite(LEFT_IN1, LOW);
    digitalWrite(LEFT_IN2, HIGH);
    l = -l;
  }
  ledcWrite(PWM_CH_L, l);

  // Right
  if (r >= 0) {
    digitalWrite(RIGHT_IN1, HIGH);
    digitalWrite(RIGHT_IN2, LOW);
  } else {
    digitalWrite(RIGHT_IN1, LOW);
    digitalWrite(RIGHT_IN2, HIGH);
    r = -r;
  }
  ledcWrite(PWM_CH_R, r);
}

void stop_motors() {
  set_speed(0, 0);
  if (current_state == STATE_MOVING) current_state = STATE_IDLE;
}

// ============================== SENSOR LOGIC ==============================

void read_sensors() {
  // IR (Active LOW = Obstacle)
  ir_l_blocked = (digitalRead(IR_LEFT) == LOW);
  ir_r_blocked = (digitalRead(IR_RIGHT) == LOW);

  // Sonar (Ping in cm)
  dist_l = sonar_left.ping_cm();
  if (dist_l == 0) dist_l = MAX_DISTANCE; // 0 means out of range
  
  delay(15); // Wait between pings to avoid crosstalk
  
  dist_r = sonar_right.ping_cm();
  if (dist_r == 0) dist_r = MAX_DISTANCE;
}

// ============================== WEBSOCKET HANDLER ==============================

void send_alert(String type, String msg) {
  StaticJsonDocument<200> doc;
  doc["message_type"] = "alert";
  doc["device_id"] = DEVICE_ID;
  doc["alert_type"] = type;
  doc["message"] = msg;
  String out;
  serializeJson(doc, out);
  webSocket.sendTXT(out);
}

void handle_message(char* payload) {
  StaticJsonDocument<512> doc;
  deserializeJson(doc, payload);
  
  const char* type = doc["message_type"];
  if (!type) return;

  // --- COMMAND HANDLING ---
  if (strcmp(type, "command") == 0) {
    const char* cmd = doc["command_name"];
    
    // INTERLOCK COMMANDS
    if (strcmp(cmd, "lock") == 0) {
      current_state = STATE_LOCKED;
      stop_motors();
      Serial.println("[LOCK] Servos active - Movement Locked");
      return;
    }
    if (strcmp(cmd, "unlock") == 0) {
      current_state = STATE_IDLE;
      Serial.println("[LOCK] Unlocked");
      return;
    }

    // MOVEMENT COMMANDS
    if (current_state == STATE_LOCKED) {
      Serial.println("[REJECT] Movement rejected - System Locked");
      send_alert("warning", "Movement rejected: Servo tasks active");
      return;
    }

    int speed = doc["payload"]["speed"] | 200;
    
    // Accept both simple and COMMAND_CONSTANTS styles
    if (strcmp(cmd, "forward") == 0 || strcmp(cmd, "MOVE_FORWARD") == 0) {
      target_speed_l = speed;
      target_speed_r = speed;
      current_state = STATE_MOVING;
      last_command = "forward";
    }
    else if (strcmp(cmd, "backward") == 0 || strcmp(cmd, "MOVE_BACKWARD") == 0) {
      target_speed_l = -speed;
      target_speed_r = -speed;
      current_state = STATE_MOVING;
      last_command = "backward";
    }
    else if (strcmp(cmd, "left") == 0 || strcmp(cmd, "TURN_LEFT") == 0) {
      target_speed_l = -speed;
      target_speed_r = speed;
      current_state = STATE_MOVING;
      last_command = "left";
    }
    else if (strcmp(cmd, "right") == 0 || strcmp(cmd, "TURN_RIGHT") == 0) {
      target_speed_l = speed;
      target_speed_r = -speed;
      current_state = STATE_MOVING;
      last_command = "right";
    }
    else if (strcmp(cmd, "stop") == 0 || strcmp(cmd, "STOP") == 0) {
      stop_motors();
      current_state = STATE_IDLE;
    }
  }
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_TEXT) handle_message((char*)payload);
  else if (type == WStype_CONNECTED) {
    // Register
    StaticJsonDocument<200> doc;
    doc["message_type"] = "registration";
    doc["device_type"] = DEVICE_TYPE;
    doc["metadata"]["device_id"] = DEVICE_ID;
    String out;
    serializeJson(doc, out);
    webSocket.sendTXT(out);
  }
}

// ============================== TASKS ==============================

// CORE 1: Navigation & Safety Loop (High Priority)
void TaskNavigation(void *pvParameters) {
  TickType_t xLastWakeTime;
  const TickType_t xFrequency = pdMS_TO_TICKS(30); // 33Hz
  xLastWakeTime = xTaskGetTickCount();

  for(;;) {
    // 1. READ SENSORS
    read_sensors();

    // 2. SAFETY CHECKS
    bool danger_close = (ir_l_blocked || ir_r_blocked);
    bool obstacle_near = (dist_l < 30 || dist_r < 30);
    bool obstacle_far = (dist_l < 60 || dist_r < 60);

    // CRITICAL STOP (IR)
    if (danger_close && current_state == STATE_MOVING && last_command == "forward") {
      stop_motors();
      current_state = STATE_HALTED;
      send_alert("collision", "IR Sensor Triggered - Hard Stop");
    }
    // OBSTACLE AVOIDANCE (Sonar)
    else if (obstacle_near && current_state == STATE_MOVING && last_command == "forward") {
      // Smart Stop
      stop_motors();
      current_state = STATE_AVOIDING;
      send_alert("obstacle", "Obstacle detected < 30cm");
      
      // Simple avoid logic: back up a bit
      set_speed(-150, -150);
      vTaskDelay(pdMS_TO_TICKS(500));
      stop_motors();
      current_state = STATE_IDLE; // Wait for new command
    }
    // SPEED MODULATION
    else if (obstacle_far && current_state == STATE_MOVING && last_command == "forward") {
      // Slow down
      int safe_speed = 100; // Cap speed
      if (target_speed_l > safe_speed) set_speed(safe_speed, safe_speed);
      else set_speed(target_speed_l, target_speed_r);
    }
    // NORMAL OPERATION
    else if (current_state == STATE_MOVING) {
      set_speed(target_speed_l, target_speed_r);
    }
    else if (current_state == STATE_IDLE || current_state == STATE_LOCKED) {
      stop_motors();
    }

    vTaskDelayUntil(&xLastWakeTime, xFrequency);
  }
}

// CORE 0: Comms Loop
void TaskComms(void *pvParameters) {
  for(;;) {
    webSocket.loop();
    vTaskDelay(10);
  }
}

// ============================== MAIN ==============================

void setup() {
  Serial.begin(115200);
  
  // Hardware Init
  setup_motors();
  pinMode(IR_LEFT, INPUT);
  pinMode(IR_RIGHT, INPUT);
  
  // WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  // WebSocket
  webSocket.begin(BACKEND_HOST, BACKEND_PORT, "/ws/wheelcontroller");
  webSocket.onEvent(webSocketEvent);

  // RTOS Tasks
  xTaskCreatePinnedToCore(TaskNavigation, "Nav", 4096, NULL, 1, NULL, 1);
  xTaskCreatePinnedToCore(TaskComms, "Comms", 4096, NULL, 0, NULL, 0);
  
  Serial.println("\n[READY] Smart Navigation System Online");
}

void loop() {
  // Empty - tasks handle everything
  vTaskDelay(1000);
}
