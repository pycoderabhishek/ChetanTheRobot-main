#ifndef SERVO_CONFIG_H
#define SERVO_CONFIG_H

/*
 * SERVO_CONFIG.H
 *
 * AMHR-PD Project – Professional Servo Controller
 * ESP32-S3 | ESP32Servo Library | MG996R
 */

#include <stdint.h>

/* =======================================================================
   GPIO PIN MAPPING (servo index → GPIO pin)
   
   WARNING: ESP32-S3 has restricted GPIOs!
   - GPIO 0, 3, 45, 46 = Strapping pins (avoid)
   - GPIO 6-11 = SPI Flash (DO NOT USE!)
   - GPIO 26-32 = PSRAM (if present)
   
   Safe GPIOs for servo PWM: 1, 2, 4, 5, 12-21, 35-42, 47, 48
   ======================================================================= */

static const int SERVO_PINS[10] = {
  4,   // CH0 - L_SHOULDER
  5,   // CH1 - L_ELBOW_1
  12,  // CH2 - L_ELBOW_2    (was 6 - INVALID!)
  13,  // CH3 - L_GRIPPER    (was 7 - INVALID!)
  15,  // CH4 - R_SHOULDER
  16,  // CH5 - R_ELBOW_1
  17,  // CH6 - R_ELBOW_2
  18,  // CH7 - R_GRIPPER
  19,  // CH8 - NECK_UPDOWN  (was 8 - INVALID!)
  20   // CH9 - NECK_LEFTRIGHT (was 9 - INVALID!)
};

/* =======================================================================
   SERVO ROLE DEFINITIONS
   ======================================================================= */

// LEFT ARM
#define L_SHOULDER      0
#define L_ELBOW_1       1
#define L_ELBOW_2       2
#define L_GRIPPER       3

// RIGHT ARM
#define R_SHOULDER      4
#define R_ELBOW_1       5
#define R_ELBOW_2       6
#define R_GRIPPER       7

// NECK
#define NECK_UPDOWN     8
#define NECK_LEFTRIGHT  9

/* =======================================================================
   SERVO CONSTANTS (MG996R)
   ======================================================================= */

#define NUM_SERVOS           10
#define SERVO_MIN_PULSE_US   500   // MG996R min pulse
#define SERVO_MAX_PULSE_US   2500  // MG996R max pulse
#define SERVO_MIN_ANGLE      0
#define SERVO_MAX_ANGLE      180
#define SERVO_HOME_ANGLE     90

#endif // SERVO_CONFIG_H
  