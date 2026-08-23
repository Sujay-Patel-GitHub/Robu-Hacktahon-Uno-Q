#include <Wire.h>
#include <Arduino_RouterBridge.h>

// PIN ASSIGNMENTS
#define LEFT_STEP_PIN  2
#define LEFT_DIR_PIN   3
#define RIGHT_STEP_PIN 4
#define RIGHT_DIR_PIN  5
#define MPU_INT_PIN    6

// PID CONSTANTS (Tuned for physical chassis)
float Kp = 22.0;
float Kd = 1.2;
float Ki = 0.8;

// STATE VARIABLES
float targetAngle = 0.0; // Dynamic target updated by Linux via RouterBridge
float currentAngle = 0.0;
float errorSum = 0.0;
float lastError = 0.0;

// Movement commands from Linux
float targetSpeed = 0.0;
float targetSteering = 0.0;

unsigned long lastTime = 0;

void setup() {
  Serial.begin(115200);
  
  // Set motor control pins as outputs
  pinMode(LEFT_STEP_PIN, OUTPUT);
  pinMode(LEFT_DIR_PIN, OUTPUT);
  pinMode(RIGHT_STEP_PIN, OUTPUT);
  pinMode(RIGHT_DIR_PIN, OUTPUT);

  // Initialize RouterBridge to listen for commands from the Qualcomm MPU
  RouterBridge.begin();
  
  // Register callback to receive speed and steering inputs
  RouterBridge.onReceive(onMovementCommandReceived);

  // MPU-6050 Initialization
  Wire.begin();
  delay(100);
  initializeMPU6050();
  
  lastTime = micros();
  Serial.println("MCU Balancing loop initialized.");
}

void loop() {
  // Update RPC Bridge communications
  RouterBridge.update();
  
  // 1. Read IMU Data & Calculate current angle
  currentAngle = readMPU6050Angle();
  
  // 2. Compute Loop Time Delta
  unsigned long now = micros();
  float dt = (now - lastTime) / 1000000.0; // convert to seconds
  lastTime = now;

  // 3. Update targetAngle dynamically based on movement inputs from Linux
  // Forward/backward speed alters the center of gravity target angle slightly
  float dynamicTarget = targetAngle + (targetSpeed * 3.0); 

  // 4. Calculate PID Output
  float error = dynamicTarget - currentAngle;
  errorSum += error * dt;
  // Anti-windup
  errorSum = constrain(errorSum, -400.0, 400.0);
  float errorRate = (error - lastError) / dt;
  lastError = error;

  float pidOutput = (Kp * error) + (Ki * errorSum) + (Kd * errorRate);

  // 5. Apply Steering Offset
  float leftMotorOutput = pidOutput + (targetSteering * 15.0);
  float rightMotorOutput = pidOutput - (targetSteering * 15.0);

  // 6. Drive Motors
  driveMotors(leftMotorOutput, rightMotorOutput);

  // Loop delay to match target execution frequency (~200Hz)
  delayMicroseconds(5000 - (micros() - now));
}

// Callback execution when Linux sends movement commands
void onMovementCommandReceived(float speed, float steering) {
  targetSpeed = constrain(speed, -1.0, 1.0);
  targetSteering = constrain(steering, -1.0, 1.0);
}

// MPU6050 Interface functions (Placeholder for actual registers)
void initializeMPU6050() {
  Wire.beginTransmission(0x68);
  Wire.write(0x6B); // Power Management 1 register
  Wire.write(0);    // Wake up MPU
  Wire.endTransmission(true);
}

float readMPU6050Angle() {
  // Replace with actual gyro/accelerometer fusion (e.g. complementary filter)
  // return filtered angle in degrees (0.0 = perfectly vertical)
  return 0.0; 
}

void driveMotors(float leftSpeed, float rightSpeed) {
  // Determine motor direction
  digitalWrite(LEFT_DIR_PIN, leftSpeed > 0 ? HIGH : LOW);
  digitalWrite(RIGHT_DIR_PIN, rightSpeed > 0 ? HIGH : LOW);

  // Generate step pulses proportional to speed
  // (In real implementation, use hardware timers/interrupts for step pulse generation)
}
