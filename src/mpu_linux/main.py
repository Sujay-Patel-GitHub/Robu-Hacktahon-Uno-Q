import cv2
import time
import numpy as np

# Simple simulation of Arduino_RouterBridge for demonstration/development
# Replace with the official bridge library when executing on the UNO Q board
class DummyBridge:
    def send_target(self, speed, steering):
        print(f"[BRIDGE] Sending speed={speed:.2f}, steering={steering:.2f} to MCU")

# Initialize bridge
bridge = DummyBridge()

def main():
    print("Starting SBR-Q Vision & Tracking Pipeline...")
    
    # Initialize the camera (using default index 0)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    # Load Haar Cascade face classifier
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    last_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Failed to capture frame.")
            break
            
        height, width, _ = frame.shape
        center_x, center_y = width // 2, height // 2
        
        # Convert to grayscale for detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        speed = 0.0
        steering = 0.0
        
        if len(faces) > 0:
            # Track the largest face found
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            x, y, w, h = largest_face
            
            # Draw bounding box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
            
            # Calculate offset from center of the frame
            face_center_x = x + w // 2
            face_center_y = y + h // 2
            
            # Horizontal error (for steering / rotation)
            error_x = face_center_x - center_x
            # Normalized horizontal error between -1.0 and 1.0
            steering = error_x / (width / 2)
            
            # Vertical size error (for distance / speed)
            # We target a specific bounding box height (e.g. 120 pixels)
            target_height = 120
            error_h = target_height - h
            # Normalized speed vector
            speed = error_h / 100.0
            speed = np.clip(speed, -1.0, 1.0)
            
            # Apply deadzone
            if abs(steering) < 0.1:
                steering = 0.0
            if abs(speed) < 0.15:
                speed = 0.0
                
            # Send movement commands to STM32 (real-time balancer)
            bridge.send_target(speed, steering)
            
            # Label overlay
            cv2.putText(frame, f"Tracking - Speed: {speed:.2f} Steer: {steering:.2f}", 
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            # No face detected: stop the robot
            bridge.send_target(0.0, 0.0)
            cv2.putText(frame, "Searching...", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
        # Draw frame center guide
        cv2.line(frame, (center_x, 0), (center_x, height), (255, 255, 255), 1)
        cv2.line(frame, (0, center_y), (width, center_y), (255, 255, 255), 1)
        
        # Display the output window (optional - omit in headless production)
        # cv2.imshow('SBR-Q Vision Interface', frame)
        
        # Simple loop pacing
        time.sleep(0.05)
        
        # Break loop with 'q'
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
